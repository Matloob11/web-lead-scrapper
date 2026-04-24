"""Google fallback search helpers for locating likely Facebook business pages."""

import csv
import random
import re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.browser_helpers import get_anchor_candidates, goto_with_retry
from scraper.config import (
    BUSINESS_NAME_STOPWORDS,
    DEFAULT_SEARCH_COUNTRY,
    GOOGLE_FALLBACK_STATUS_FILE,
    GOOGLE_FALLBACK_STATUS_HEADERS,
    GOOGLE_RESULT_LIMIT,
    GOOGLE_TIMEOUT_MS,
)
from scraper.control import responsive_sleep
from scraper.sources.facebook_scraper import normalize_facebook_candidate_url
from scraper.storage.csv_storage import ensure_parent_dir, log_failure
from scraper.utils import compact_whitespace, normalize_external_url

GOOGLE_CAPTCHA_HINTS = (
    "our systems have detected unusual traffic",
    "unusual traffic from your computer network",
    "automated queries",
    "to continue, please type the characters",
    "not a robot",
    "verify you're not a robot",
    "verify you are not a robot",
    "verify you are a human",
    "recaptcha",
    "captcha",
)


def build_google_facebook_query(name, location, country):
    """Build the Google query used to discover Facebook business pages."""
    clean_name = compact_whitespace(name)
    clean_loc = compact_whitespace(location)
    clean_country = compact_whitespace(country) or DEFAULT_SEARCH_COUNTRY

    query = f'site:facebook.com "{clean_name}"'
    if clean_loc:
        query += f' "{clean_loc}"'
    query += f" fb in {clean_country}"
    return query


def is_google_verification_page(page_url, body_text):
    """Return True when Google is showing a captcha or human verification page."""
    normalized_url = (page_url or "").lower()
    normalized_text = compact_whitespace(body_text).lower()
    return (
        "/sorry/" in normalized_url
        or "sorry/index" in normalized_url
        or "captcha" in normalized_url
        or any(hint in normalized_text for hint in GOOGLE_CAPTCHA_HINTS)
    )


def record_google_fallback_status(
    profile_url,
    name,
    location,
    country,
    query,
    status,
    candidate_count=0,
    first_candidate="",
    detail="",
    status_file=GOOGLE_FALLBACK_STATUS_FILE,
):
    """Upsert the latest Google fallback status for one profile/query pair."""
    ensure_parent_dir(status_file)
    updated_at = datetime.now().isoformat(timespec="seconds")
    key = ((profile_url or "").strip(), (query or "").strip().lower())
    latest_row = {
        "profile_url": profile_url,
        "name": name,
        "location": location,
        "country": country,
        "query": query,
        "status": status,
        "candidate_count": str(candidate_count),
        "first_candidate": first_candidate,
        "detail": detail,
        "updated_at": updated_at,
    }
    rows = []
    replaced = False

    try:
        with open(status_file, encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                row_key = (
                    (row.get("profile_url") or "").strip(),
                    (row.get("query") or "").strip().lower(),
                )
                if row_key == key:
                    if not replaced:
                        rows.append(latest_row)
                        replaced = True
                    continue

                rows.append(
                    {header: row.get(header, "") for header in GOOGLE_FALLBACK_STATUS_HEADERS}
                )
    except (csv.Error, OSError):
        rows = []

    if not replaced:
        rows.append(latest_row)

    with open(status_file, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=GOOGLE_FALLBACK_STATUS_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def extract_google_target_url(href):
    """Unwrap Google redirect URLs into their final target link."""
    if not href:
        return ""

    normalized_url = normalize_external_url(href)
    full_url = (
        normalized_url
        if normalized_url.startswith("http")
        else urljoin("https://www.google.com", normalized_url)
    )
    parsed = urlparse(full_url)
    hostname = (parsed.hostname or "").lower()

    if "google." in hostname and parsed.path.startswith("/url"):
        query_values = parse_qs(parsed.query)
        target_url = (query_values.get("q") or query_values.get("url") or [""])[0]
        return normalize_external_url(unquote(target_url))

    return full_url


def tokenize_business_name(name):
    """Tokenize a business name for search-result scoring."""
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [token for token in tokens if len(token) >= 2 and token not in BUSINESS_NAME_STOPWORDS]


def score_google_facebook_candidate(url, link, name, country):
    """Score how likely a Google result is to be the right Facebook page."""
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    haystack = f"{url} {label}".lower()
    tokens = tokenize_business_name(name)
    token_hits = sum(1 for token in tokens if token in haystack)

    if tokens and token_hits == 0:
        return -1

    score = 8 + (token_hits * 4)
    if "facebook" in haystack:
        score += 4
    if "fb" in haystack:
        score += 2
    if compact_whitespace(country).lower() in haystack:
        score += 2
    if any(part in url.lower() for part in ("/posts/", "/photos/", "/videos/", "/reel/")):
        score -= 3
    return score


def extract_google_facebook_candidates(links, name, country):
    """Rank and return the strongest Facebook candidates from Google results."""
    ranked = []
    seen = set()

    for link in links:
        target_url = extract_google_target_url(link.get("href", ""))
        facebook_url = normalize_facebook_candidate_url(target_url)
        if not facebook_url or facebook_url in seen:
            continue

        score = score_google_facebook_candidate(facebook_url, link, name, country)
        if score <= 0:
            continue

        seen.add(facebook_url)
        ranked.append((score, facebook_url))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in ranked[:GOOGLE_RESULT_LIMIT]]


async def get_google_facebook_candidates(
    context,
    name,
    location,
    country,
    profile_url="",
    google_cache=None,
    logger=None,
):
    """Use Google as a fallback to discover likely Facebook pages for a pro name."""

    def log(msg):
        if logger:
            logger(msg)
        else:
            print(msg)

    clean_name = compact_whitespace(name)
    clean_loc = compact_whitespace(location)
    clean_country = compact_whitespace(country) or DEFAULT_SEARCH_COUNTRY
    if not clean_name:
        return [], False

    query = build_google_facebook_query(clean_name, clean_loc, clean_country)
    cache_key = query.lower()

    def record(status, candidate_count=0, first_candidate="", detail=""):
        record_google_fallback_status(
            profile_url,
            clean_name,
            clean_loc,
            clean_country,
            query,
            status,
            candidate_count,
            first_candidate,
            detail,
        )

    if google_cache is not None and cache_key in google_cache:
        cached_candidates, cached_error = google_cache[cache_key]
        cached_status = "cache_result_found" if cached_candidates else "cache_no_result"
        if cached_error:
            cached_status = "cache_error"
        record(
            cached_status,
            len(cached_candidates),
            cached_candidates[0] if cached_candidates else "",
            "served_from_runtime_cache",
        )
        return list(cached_candidates), cached_error

    candidates = []
    had_error = False
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        log(f"  [~] Google FB search: {query}")
        try:
            await goto_with_retry(
                page,
                search_url,
                "google_facebook_search",
                timeout_ms=GOOGLE_TIMEOUT_MS,
                logger=logger,
            )
        except PlaywrightError as exc:
            had_error = True
            log_failure("google_facebook_search", search_url, exc, profile_url)
            log(f"  [!] Google FB search error ({clean_name}): {exc}")
            record("error", detail=str(exc))
            if google_cache is not None:
                google_cache[cache_key] = (list(candidates), had_error)
            return candidates, had_error

        try:
            body_text = await page.locator("body").inner_text(timeout=3000)
        except PlaywrightError:
            body_text = ""

        if is_google_verification_page(page.url, body_text):
            log(f"  [!] Google verification/captcha shown. Skipping Google fallback: {clean_name}")
            record("captcha", detail="google_verification_page")
            if google_cache is not None:
                google_cache[cache_key] = (list(candidates), False)
            return candidates, False

        await responsive_sleep(random.uniform(0.5, 1.0))
        links, link_error = await get_anchor_candidates(
            page,
            "google_facebook_search",
            search_url,
            profile_url,
            logger=logger,
        )
        had_error = had_error or link_error
        candidates = extract_google_facebook_candidates(links, clean_name, clean_country)
        if candidates:
            log(f"  [~] Google FB candidate found: {candidates[0]}")
            record("result_found", len(candidates), candidates[0])
        else:
            detail = "link_read_error" if link_error else ""
            record("no_result", detail=detail)
    finally:
        await page.close()

    if google_cache is not None:
        google_cache[cache_key] = (list(candidates), had_error)
    return candidates, had_error
