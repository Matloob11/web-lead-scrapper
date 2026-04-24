"""Facebook page helpers used to extract visible business emails."""

import random
import re
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.browser_helpers import extract_page_emails, goto_with_retry
from scraper.config import FACEBOOK_REJECT_FIRST_SEGMENTS, FACEBOOK_TIMEOUT_MS
from scraper.control import responsive_sleep
from scraper.storage.csv_storage import log_failure
from scraper.utils import normalize_external_url


def normalize_facebook_candidate_url(url):
    """Normalize a Facebook URL and reject generic or unsupported paths."""
    normalized_url = normalize_external_url(url)
    if not normalized_url:
        return ""

    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").lower()
    if not (hostname == "facebook.com" or hostname.endswith(".facebook.com")):
        return ""
    if hostname.startswith(("l.", "lm.")):
        return ""

    path = parsed.path or "/"
    clean_path = re.sub(r"/+", "/", path).rstrip("/")
    if not clean_path:
        clean_path = "/"
    if clean_path == "/":
        return ""

    first_segment = clean_path.strip("/").split("/", 1)[0].lower()
    if first_segment in FACEBOOK_REJECT_FIRST_SEGMENTS:
        return ""

    if clean_path.lower() == "/profile.php":
        profile_id = (parse_qs(parsed.query).get("id") or [""])[0]
        if not profile_id:
            return ""
        return f"https://www.facebook.com/profile.php?id={profile_id}"

    return f"https://www.facebook.com{clean_path}"


def build_facebook_about_url(facebook_url):
    """Return the Facebook About page URL for a normalized profile URL."""
    parsed = urlparse(facebook_url)
    if "/about" in (parsed.path or "").lower():
        return facebook_url
    if (parsed.path or "").rstrip("/").lower() == "/profile.php":
        return facebook_url
    return facebook_url.rstrip("/") + "/about"


async def get_facebook_emails(context, url, profile_url="", facebook_cache=None, logger=None):
    """Visit a Facebook page/about page and pull visible emails."""

    def log(msg):
        if logger:
            logger(msg)
        else:
            print(msg)

    normalized_url = normalize_facebook_candidate_url(url)
    if not normalized_url:
        return set(), False

    emails = set()
    had_error = False
    about_url = build_facebook_about_url(normalized_url)
    cache_key = about_url.rstrip("/").lower()
    if facebook_cache is not None and cache_key in facebook_cache:
        cached_emails, cached_error = facebook_cache[cache_key]
        return set(cached_emails), cached_error

    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        log(f"  [~] Checking Facebook: {about_url}")
        try:
            await goto_with_retry(
                page,
                about_url,
                "facebook_about",
                timeout_ms=FACEBOOK_TIMEOUT_MS,
                logger=logger,
            )
        except PlaywrightError as exc:
            had_error = True
            log_failure("facebook_about", about_url, exc, profile_url)
            log(f"  [!] FB scraping error ({about_url}): {exc}")
            return emails, had_error

        await responsive_sleep(random.uniform(0.8, 1.3))
        page_emails, page_error = await extract_page_emails(
            page,
            about_url,
            "facebook_about",
            profile_url,
            logger=logger,
        )
        emails.update(page_emails)
        had_error = had_error or page_error
    finally:
        await page.close()

    if facebook_cache is not None:
        facebook_cache[cache_key] = (set(emails), had_error)
    return emails, had_error
