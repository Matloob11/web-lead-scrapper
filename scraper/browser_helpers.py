"""Async browser helpers shared across scraper sources."""

import random
from contextlib import suppress
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.config import REDIRECT_TIMEOUT_MS, RETRY_ATTEMPTS
from scraper.control import responsive_sleep
from scraper.filters.email_filters import extract_mailto_emails, find_emails
from scraper.storage.csv_storage import log_failure
from scraper.utils import decode_houzz_trk_link, normalize_external_url


def _log(logger, message):
    """Send a message to the configured logger or stdout fallback."""
    if logger:
        logger(message)
    else:
        print(message)


async def goto_with_retry(page, url, step, timeout_ms, retries=RETRY_ATTEMPTS, logger=None):
    """Navigate to a page with retry support for transient Playwright failures."""
    last_error = None
    total_attempts = retries + 1

    for attempt in range(1, total_attempts + 1):
        try:
            return await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except PlaywrightError as exc:
            last_error = exc
            if attempt >= total_attempts:
                raise
            _log(logger, f"  [retry] {step} attempt {attempt}/{total_attempts} failed: {exc}")
            await responsive_sleep(random.uniform(0.5, 1.0))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{step} failed before navigation started.")


async def get_anchor_candidates(page, step, target_url, profile_url="", logger=None):
    """Collect anchor candidates from a page, retrying around context resets."""
    # Try up to 3 times if we hit "Execution context was destroyed"
    for attempt in range(3):
        try:
            # Short wait for page stabilization
            await responsive_sleep(0.2 if attempt == 0 else 0.6)

            # Wait for network to be somewhat idle if possible
            with suppress(PlaywrightError):
                await page.wait_for_load_state("networkidle", timeout=1000)

            links = await page.eval_on_selector_all(
                "a[href]",
                """elements => elements.map(el => ({
                    href: el.getAttribute('href') || '',
                    text: (el.innerText || el.textContent || '').trim(),
                    aria: el.getAttribute('aria-label') || ''
                }))""",
            )
            return links, False
        except PlaywrightError as exc:
            exc_str = str(exc)
            if "Execution context was destroyed" in exc_str and attempt < 2:
                _log(
                    logger,
                    (
                        f"  [retry] Context destroyed during link extraction for "
                        f"{step}, retrying after delay ({attempt + 1}/3)..."
                    ),
                )
                await responsive_sleep(0.4)
                continue

            if "Execution context was destroyed" not in exc_str:
                log_failure(f"{step}_links", target_url, exc, profile_url)

            return [], True
    return [], True


async def extract_page_emails(page, page_url, step, profile_url="", logger=None):
    """Extract visible and mailto-based emails from the current page."""
    emails = set()
    had_error = False

    # Try up to 3 times if we hit "Execution context was destroyed"
    for attempt in range(3):
        try:
            # Give the page a moment to stabilize if it just finished loading
            # Increased delay for better stability
            await responsive_sleep(0.35 if attempt == 0 else 0.8)

            # Wait for network to be somewhat idle if possible
            with suppress(PlaywrightError):
                await page.wait_for_load_state("networkidle", timeout=1000)

            visible_text = await page.evaluate(
                """() => {
                    try {
                        const bodyText = document.body ? (document.body.innerText || "") : "";
                        const linkText = Array.from(document.querySelectorAll("a[href]"))
                            .map(
                                el => `${el.getAttribute("href") || ""} ${
                                    (el.innerText || el.textContent || "").trim()
                                }`
                            )
                            .join("\\n");
                        return `${bodyText}\\n${linkText}`;
                    } catch (e) {
                        return "";
                    }
                }"""
            )
            if visible_text:
                emails.update(find_emails(visible_text))

            # mailto link extraction also inside the retry loop
            hrefs = await page.eval_on_selector_all(
                'a[href^="mailto:"]',
                "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
            )
            for href in hrefs:
                emails.update(extract_mailto_emails(href))

            # If we got here, evaluate succeeded, break retry loop
            break
        except PlaywrightError as exc:
            exc_str = str(exc)
            if "Execution context was destroyed" in exc_str and attempt < 2:
                _log(
                    logger,
                    (
                        f"  [retry] Context destroyed during extraction for "
                        f"{step}, retrying after delay ({attempt + 1}/3)..."
                    ),
                )
                await responsive_sleep(0.6)
                continue

            if "Execution context was destroyed" not in exc_str:
                had_error = True
                log_failure(f"{step}_text", page_url, exc, profile_url)
            break

    return emails, had_error


async def handle_redirect_url(context, url, profile_url="", step="redirect", logger=None):
    """Follow Houzz redirect links and return final target URL."""
    normalized_url = normalize_external_url(url)
    if not normalized_url:
        return "", False

    url_lower = normalized_url.lower()
    needs_redirect = (
        normalized_url.startswith("/") or "/trk/" in url_lower or "houzz.com" in url_lower
    )
    if not needs_redirect:
        return normalized_url, False

    full_url = (
        normalized_url
        if normalized_url.startswith("http")
        else urljoin("https://www.houzz.com", normalized_url)
    )
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        await goto_with_retry(page, full_url, step, timeout_ms=REDIRECT_TIMEOUT_MS, logger=logger)
        return normalize_external_url(page.url), False
    except PlaywrightError as exc:
        # Fallback: Try decoding the URL directly from the tracking link
        decoded_url = decode_houzz_trk_link(full_url)
        if decoded_url:
            _log(logger, f"  [~] Redirect failed, but decoded target URL: {decoded_url}")
            return normalize_external_url(decoded_url), False

        log_failure(step, full_url, exc, profile_url)
        _log(logger, f"  [!] Redirect failed for {url}: {exc}")
        return normalized_url, True
    finally:
        await page.close()
