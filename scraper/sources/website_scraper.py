"""Website crawling helpers for extracting visible business contact emails."""

import random
from urllib.parse import urljoin, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.browser_helpers import (
    extract_page_emails,
    get_anchor_candidates,
    goto_with_retry,
)
from scraper.config import (
    CONTACT_TIMEOUT_MS,
    FOLLOWUP_PAGE_LIMIT,
    FOLLOWUP_PATHS,
    SITE_TIMEOUT_MS,
)
from scraper.control import responsive_sleep
from scraper.storage.csv_storage import log_failure
from scraper.utils import normalize_external_url


def get_domain_cache_key(url):
    """Return a normalized cache key for the site's hostname."""
    normalized_url = normalize_external_url(url)
    if not normalized_url or normalized_url.startswith("/"):
        return ""

    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or parsed.netloc or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def build_site_followup_urls(candidates, base_url):
    """Build and rank likely contact/about follow-up URLs for a site."""
    normalized_base = normalize_external_url(base_url)
    if not normalized_base or normalized_base.startswith("/"):
        return []

    parsed_base = urlparse(normalized_base)
    base_host = (parsed_base.hostname or "").lower()
    if not base_host:
        return []

    root_url = f"{parsed_base.scheme}://{parsed_base.netloc}/"
    ranked = []

    for link in candidates:
        href = (link.get("href") or "").strip()
        if not href or href.lower().startswith("mailto:"):
            continue

        absolute_url = normalize_external_url(urljoin(normalized_base, href))
        if not absolute_url.startswith("http"):
            continue

        parsed_target = urlparse(absolute_url)
        target_host = (parsed_target.hostname or "").lower()
        if target_host != base_host:
            continue

        label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
        href_lower = href.lower()
        absolute_lower = absolute_url.lower()
        score = 0

        if "contact" in label or "contact" in href_lower:
            score += 10
        if "about" in label or "/about" in absolute_lower:
            score += 7
        if (
            "get in touch" in label
            or "get-in-touch" in absolute_lower
            or "getintouch" in absolute_lower
        ):
            score += 6
        if "support" in label or "/support" in absolute_lower:
            score += 5

        if score > 0:
            ranked.append((score, absolute_url))

    for index, path in enumerate(FOLLOWUP_PATHS):
        ranked.append((4 - min(index, 3), normalize_external_url(urljoin(root_url, path))))

    ranked.sort(key=lambda item: item[0], reverse=True)
    deduped_urls = []
    seen = set()

    for _, candidate_url in ranked:
        normalized_candidate = candidate_url.rstrip("/")
        if normalized_candidate == normalized_base.rstrip("/"):
            continue
        if normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        deduped_urls.append(candidate_url)
        if len(deduped_urls) >= FOLLOWUP_PAGE_LIMIT:
            break

    return deduped_urls


async def get_site_emails(context, url, profile_url="", site_cache=None, logger=None):
    """Browse the external site home page and contact/about follow-up pages."""

    def log(message):
        if logger:
            logger(message)
        else:
            print(message)

    normalized_url = normalize_external_url(url)
    if (
        not normalized_url
        or not normalized_url.startswith(("http://", "https://"))
        or "houzz.com" in normalized_url.lower()
        or normalized_url.startswith("/")
    ):
        return set(), False

    cache_key = get_domain_cache_key(normalized_url)
    if site_cache is not None and cache_key and cache_key in site_cache:
        cached_emails, cached_error = site_cache[cache_key]
        return set(cached_emails), cached_error

    emails = set()
    had_error = False
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        log(f"  [~] Visiting Site: {normalized_url}")
        try:
            await goto_with_retry(
                page,
                normalized_url,
                "site_home",
                timeout_ms=SITE_TIMEOUT_MS,
                logger=logger,
            )
        except PlaywrightError as exc:
            had_error = True
            log_failure("site_home", normalized_url, exc, profile_url)
            log(f"  [!] Site home error ({normalized_url}): {exc}")
            return emails, had_error

        await responsive_sleep(random.uniform(0.4, 0.9))
        page_emails, page_error = await extract_page_emails(
            page,
            normalized_url,
            "site_home",
            profile_url,
            logger=logger,
        )
        emails.update(page_emails)
        had_error = had_error or page_error

        contact_candidates, link_error = await get_anchor_candidates(
            page,
            "site_home",
            normalized_url,
            profile_url,
            logger=logger,
        )
        had_error = had_error or link_error
        followup_urls = build_site_followup_urls(contact_candidates, normalized_url)
        visited_urls = {normalized_url.rstrip("/"), page.url.rstrip("/")}

        for followup_url in followup_urls:
            if followup_url.rstrip("/") in visited_urls:
                continue

            try:
                await goto_with_retry(
                    page,
                    followup_url,
                    "site_contact",
                    timeout_ms=CONTACT_TIMEOUT_MS,
                    logger=logger,
                )
                await responsive_sleep(random.uniform(0.3, 0.7))
            except PlaywrightError as exc:
                had_error = True
                log_failure("site_contact", followup_url, exc, profile_url)
                log(f"  [!] Contact page error ({followup_url}): {exc}")
                continue

            visited_urls.add(page.url.rstrip("/"))
            contact_emails, contact_error = await extract_page_emails(
                page,
                followup_url,
                "site_contact",
                profile_url,
                logger=logger,
            )
            emails.update(contact_emails)
            had_error = had_error or contact_error
    finally:
        await page.close()

    if site_cache is not None and cache_key:
        site_cache[cache_key] = (set(emails), had_error)
    return emails, had_error
