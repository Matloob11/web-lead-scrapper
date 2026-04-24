"""Houzz profile scraper for extracting emails from Houzz professional pages."""

import csv
import random

from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.browser_helpers import (
    extract_page_emails,
    get_anchor_candidates,
    goto_with_retry,
    handle_redirect_url,
)
from scraper.config import DEFAULT_SEARCH_COUNTRY, PROFILE_TIMEOUT_MS
from scraper.control import responsive_sleep, stop_requested
from scraper.filters.business_filters import is_target_business_text
from scraper.filters.email_filters import (
    extract_mailto_emails,
    is_valid_email_candidate,
)
from scraper.search.google_facebook_search import get_google_facebook_candidates
from scraper.sources.facebook_scraper import (
    get_facebook_emails,
    normalize_facebook_candidate_url,
)
from scraper.sources.website_scraper import get_site_emails
from scraper.storage.csv_storage import (
    log_failure,
    record_status,
    write_detail_rows,
    write_master_rows,
)
from scraper.utils import merge_email_sources, unique_preserve_order

PROFILE_PROCESSING_ERRORS = (csv.Error, OSError, PlaywrightError, RuntimeError, ValueError)


def score_website_candidate(link):
    """Return a numeric score for how likely *link* points to the pro's own website."""
    href = (link.get("href") or "").strip()
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    href_lower = href.lower()

    if not href or href_lower.startswith("mailto:"):
        return -1
    if any(
        domain in href_lower
        for domain in ("facebook", "instagram", "twitter", "linkedin", "pinterest")
    ):
        return -1

    score = 0
    if "website" in label or "visit website" in label or "visit my website" in label:
        score += 7
    if "/trk/" in href_lower:
        score += 6
    if href_lower.startswith("http") and "houzz.com" not in href_lower:
        score += 4
    if href.startswith("/") and "/trk/" in href_lower:
        score += 4
    if "houzz.com" in href_lower and "/trk/" not in href_lower:
        score -= 3
    return score


def score_facebook_candidate(link):
    """Return a numeric score for how likely *link* points to the pro's Facebook page."""
    href = (link.get("href") or "").strip()
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    href_lower = href.lower()

    if not href or href_lower.startswith("mailto:"):
        return -1
    if "facebook.com" in href_lower and not normalize_facebook_candidate_url(href):
        return -1

    score = 0
    if "facebook" in label:
        score += 7
    if "facebook.com" in href_lower:
        score += 7
    if "/trk/" in href_lower and "facebook" in label:
        score += 4
    return score


def pick_best_link(candidates, scorer):
    """Return the href with the highest scorer() score, or empty string if none qualify."""
    ranked = []
    for link in candidates:
        score = scorer(link)
        if score > 0:
            ranked.append((score, (link.get("href") or "").strip()))

    if not ranked:
        return ""

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def extract_profile_links(candidates):
    """Extract website URL, Facebook URL, and mailto emails from anchor candidates."""
    mailto_emails = set()
    for link in candidates:
        mailto_emails.update(extract_mailto_emails(link.get("href", "")))

    website_url = pick_best_link(candidates, score_website_candidate)
    facebook_url = pick_best_link(candidates, score_facebook_candidate)
    return website_url, facebook_url, mailto_emails


async def process_profile(
    context,
    pro_link,
    master_writer,
    master_file,
    detail_writer,
    detail_file,
    unique_emails_all,
    detail_keys,
    status_map,
    site_cache,
    facebook_cache,
    google_cache,
    allow_facebook=True,
    allow_google_fallback=True,
    country=DEFAULT_SEARCH_COUNTRY,
    logger=None,
    runtime=None,
    stop_event=None,
):
    """Scrape a single Houzz professional profile for emails via website, Facebook, and Google."""

    def log(msg):
        if logger:
            logger(msg)
        else:
            print(msg)

    log(f"\n[+] Professional: {pro_link}")
    pro_page = await context.new_page()
    await Stealth().apply_stealth_async(pro_page)

    try:
        if runtime:
            await runtime.wait_if_paused()
        if stop_requested(runtime, stop_event):
            return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
        response = await goto_with_retry(
            pro_page,
            pro_link,
            "profile_page",
            timeout_ms=PROFILE_TIMEOUT_MS,
            logger=logger,
        )
        if response and response.status == 404:
            log(f"    [!] Profile not found (404): {pro_link}")
            record_status(status_map, pro_link, "no_email", "profile_404")
            return {"status": "no_email", "master_saved": 0, "detail_saved": 0}

        if await responsive_sleep(random.uniform(0.7, 1.2), runtime, stop_event):
            return {"status": "stopped", "master_saved": 0, "detail_saved": 0}

        name = ""
        try:
            name_el = await pro_page.query_selector("h1")
            if name_el:
                name = (await name_el.inner_text()).strip()
        except PlaywrightError as exc:
            log_failure("profile_name", pro_link, exc, pro_link)

        profile_errors = []
        email_sources = {}

        location = ""
        try:
            # Enhanced location extraction with multiple selector candidates
            loc_selectors = [
                ".profile-about__city-state",
                "[itemprop='addressLocality']",
                ".profile-about__info-item span",
                "span.hz-pro-search-result__location",
            ]
            for selector in loc_selectors:
                loc_el = await pro_page.query_selector(selector)
                if loc_el:
                    location = (await loc_el.inner_text()).strip()
                    if location:
                        break
        except PlaywrightError:
            pass

        try:
            profile_text_sample = (await pro_page.locator("body").inner_text(timeout=5000))[:1500]
        except PlaywrightError:
            profile_text_sample = ""

        if not is_target_business_text(pro_link, name, profile_text_sample):
            log(f"    [skip] Not contractor/real-estate related: {name}")
            record_status(
                status_map,
                pro_link,
                "no_email",
                "source=houzz; skipped_non_target_business",
            )
            return {"status": "no_email", "master_saved": 0, "detail_saved": 0}

        profile_candidates, candidate_error = await get_anchor_candidates(
            pro_page,
            "profile_page",
            pro_link,
            pro_link,
            logger=logger,
        )
        if candidate_error:
            profile_errors.append("profile_links")

        direct_emails, direct_email_error = await extract_page_emails(
            pro_page,
            pro_link,
            "profile_page",
            pro_link,
            logger=logger,
        )
        if direct_email_error:
            profile_errors.append("profile_emails")
        merge_email_sources(email_sources, direct_emails, "profile")

        website_raw, facebook_raw, mailto_emails = extract_profile_links(profile_candidates)
        merge_email_sources(email_sources, mailto_emails, "mailto")

        website_final = ""
        if website_raw:
            website_final, website_redirect_error = await handle_redirect_url(
                context,
                website_raw,
                profile_url=pro_link,
                step="website_redirect",
                logger=logger,
            )
            if website_redirect_error:
                profile_errors.append("website_redirect")

        facebook_final = ""
        if facebook_raw:
            facebook_final, facebook_redirect_error = await handle_redirect_url(
                context,
                facebook_raw,
                profile_url=pro_link,
                step="facebook_redirect",
                logger=logger,
            )
            if facebook_redirect_error:
                profile_errors.append("facebook_redirect")

        if facebook_final:
            cleaned_facebook_url = normalize_facebook_candidate_url(facebook_final)
            if cleaned_facebook_url:
                facebook_final = cleaned_facebook_url
            else:
                log(f"    [~] Ignoring generic/non-profile Facebook link: {facebook_final}")
                facebook_final = ""

        log(f"    Name: {name}")
        if location:
            log(f"    Location: {location}")
        log(f"    Website: {website_final}")
        log(f"    Facebook: {facebook_final}")
        facebook_checked = False
        google_facebook_checked = False
        google_facebook_candidates = []

        if website_final:
            if runtime:
                await runtime.wait_if_paused()
            if stop_requested(runtime, stop_event):
                return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
            log(f"    [~] Checking Website: {website_final}")
            site_emails, site_error = await get_site_emails(
                context,
                website_final,
                pro_link,
                site_cache,
                logger=logger,
            )
            merge_email_sources(email_sources, site_emails, "website")
            if site_error:
                profile_errors.append("website_lookup")

        valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}

        # 1. Try the Facebook link found directly on the profile
        if allow_facebook and not valid_emails and facebook_final:
            if runtime:
                await runtime.wait_if_paused()
            if stop_requested(runtime, stop_event):
                return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
            log(f"    [~] Checking Profile Facebook: {facebook_final}")
            fb_emails, fb_error = await get_facebook_emails(
                context,
                facebook_final,
                pro_link,
                facebook_cache,
                logger=logger,
            )
            merge_email_sources(email_sources, fb_emails, "facebook")
            if fb_error:
                profile_errors.append("facebook_lookup")
            valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}

        # 2. If still no emails, try Google Fallback
        if allow_facebook and allow_google_fallback and name and not valid_emails:
            if runtime:
                await runtime.wait_if_paused()
            if stop_requested(runtime, stop_event):
                return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
            google_facebook_checked = True
            log(
                "    [!] No email found yet. Searching Google for "
                "location-based Facebook profiles..."
            )
            google_facebook_candidates, google_error = await get_google_facebook_candidates(
                context,
                name,
                location,
                country,
                profile_url=pro_link,
                google_cache=google_cache,
                logger=logger,
            )
            if google_error:
                profile_errors.append("google_facebook_search")

            if google_facebook_candidates:
                log(
                    f"    [+] Google found {len(google_facebook_candidates)} "
                    "candidate(s). Checking them..."
                )
                for facebook_url in unique_preserve_order(google_facebook_candidates):
                    if runtime:
                        await runtime.wait_if_paused()
                    if stop_requested(runtime, stop_event):
                        return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
                    if valid_emails:
                        break
                    facebook_checked = True
                    fb_emails, fb_error = await get_facebook_emails(
                        context,
                        facebook_url,
                        pro_link,
                        facebook_cache,
                        logger=logger,
                    )
                    merge_email_sources(email_sources, fb_emails, "facebook_fallback")
                    if fb_error:
                        profile_errors.append("facebook_fallback_lookup")
                    # Update facebook_final to reflect the source of the email
                    facebook_final = facebook_url
                    valid_emails = {
                        email for email in email_sources if is_valid_email_candidate(email)
                    }
            else:
                log("    [-] Google search yielded no relevant Facebook candidates.")

        valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}
        detail_rows_added = 0
        master_rows_added = 0

        if valid_emails:
            master_rows_added, new_master_emails = write_master_rows(
                master_writer,
                master_file,
                unique_emails_all,
                valid_emails,
                logger=logger,
            )
            detail_rows_added = write_detail_rows(
                detail_writer,
                detail_file,
                detail_keys,
                email_sources,
                name,
                pro_link,
                website_final,
                facebook_final,
                new_master_emails,
            )

        warning_tags = unique_preserve_order(profile_errors)
        warning_text = f"; warnings={','.join(warning_tags)}" if warning_tags else ""

        if valid_emails:
            record_status(
                status_map,
                pro_link,
                "processed",
                (
                    f"emails_found={len(valid_emails)}; "
                    f"master_saved={master_rows_added}; "
                    f"detail_saved={detail_rows_added}{warning_text}"
                ),
            )
            return {
                "status": "processed",
                "master_saved": master_rows_added,
                "detail_saved": detail_rows_added,
            }

        # If we reached here, no emails were found.
        # We only mark as 'failed' if there were warnings AND we didn't finish the fallback check.
        # But since we currently always try to finish fallback, we'll mark as 'no_email'
        # to avoid infinite retries of profiles with broken website links.
        checked_steps = ["profile"]
        if website_final:
            checked_steps.append("website")
        if google_facebook_checked:
            checked_steps.append("google_fallback")
        if facebook_checked:
            checked_steps.append("facebook")

        status_msg = f"checked_{'_'.join(checked_steps)}{warning_text}"
        record_status(status_map, pro_link, "no_email", status_msg)
        return {"status": "no_email", "master_saved": 0, "detail_saved": 0}
    except PROFILE_PROCESSING_ERRORS as exc:
        if stop_requested(runtime, stop_event):
            return {"status": "stopped", "master_saved": 0, "detail_saved": 0}
        log_failure("profile_processing", pro_link, exc, pro_link)
        record_status(status_map, pro_link, "failed", str(exc))
        log(f"    [!] Error processing profile: {exc}")
        return {"status": "failed", "master_saved": 0, "detail_saved": 0}
    finally:
        await pro_page.close()
