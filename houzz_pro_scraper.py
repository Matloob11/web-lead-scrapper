"""Entry point for the Houzz/BBB email scraper CLI and programmatic API."""

import argparse
import asyncio
import contextlib
import csv
import random

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from scraper.browser_helpers import goto_with_retry
from scraper.browser_launcher import launch_persistent_browser
from scraper.config import (
    CONCURRENT_PROFILES,
    DEFAULT_SEARCH_COUNTRY,
    PROFILE_TIMEOUT_MS,
)
from scraper.control import responsive_sleep, stop_requested
from scraper.identity import DEVICE_ID_ENV_VAR, get_device_id, normalize_device_id
from scraper.sources.bbb_profile import run_bbb_search
from scraper.sources.houzz_profile import process_profile
from scraper.storage.csv_storage import (
    ensure_output_files,
    export_final_emails,
    get_active_detail_output_file,
    get_active_output_file,
    load_existing_detail_keys,
    load_master_emails,
    load_statuses,
    set_active_source,
    write_statuses,
)
from scraper.storage.mongodb_storage import db_manager
from scraper.utils import (
    compact_whitespace,
    infer_country_from_url,
    unique_preserve_order,
)

SCRAPER_RUN_ERRORS = (csv.Error, OSError, PlaywrightError, RuntimeError, ValueError)


def init_stats():
    """Build the mutable counters used to summarize one scraping run."""
    return {
        "profiles_attempted": 0,
        "profiles_skipped": 0,
        "processed": 0,
        "failed": 0,
        "no_email": 0,
        "master_saved": 0,
        "detail_saved": 0,
    }


def print_summary(stats, logger=print):
    """Emit the final summary for a completed scraping run."""
    logger("\n--- Run Summary ---")
    logger(f"Profiles attempted: {stats['profiles_attempted']}")
    logger(f"Profiles skipped:   {stats['profiles_skipped']}")
    logger(f"Processed:          {stats['processed']}")
    logger(f"Failed:             {stats['failed']}")
    logger(f"No email:           {stats['no_email']}")
    logger(f"Master emails:      {stats['master_saved']}")
    logger(f"Detail rows:        {stats['detail_saved']}")


def resolve_access_identity(device_id=None, access_identity=None):
    """Resolve the admin access identity without requiring user-entered license text."""
    explicit_identity = normalize_device_id(device_id or access_identity)
    return explicit_identity or get_device_id()


def require_admin_access(access_identity, source, target, logger=print):
    """Require MongoDB admin approval before allowing scraper work."""
    clean_license = db_manager.normalize_license_key(access_identity)
    access = db_manager.request_access(clean_license, source, target)
    if access.get("allowed"):
        logger("[SYSTEM] Access approved by admin panel.")
        return clean_license

    status = str(access.get("status") or "unknown").strip()
    message = str(access.get("message") or "Access is not approved.").strip()
    raise PermissionError(f"{message} [status: {status}]")


def _finish_activity(activity_id, emails_count, status):
    """Best-effort MongoDB activity update for CLI-owned runs."""
    if activity_id is None:
        return
    with contextlib.suppress(Exception):
        db_manager.update_activity(activity_id, emails_count, status=status)


async def run_scraper(
    input_url,
    source="houzz",
    max_pages=None,
    max_profiles=None,
    headless=False,
    skip_facebook=False,
    country=None,
    skip_google_fallback=False,
    auto_export_final=True,
    quality_filter=None,
    retry_no_email=False,
    out_filename=None,
    logger=print,
    stop_event=None,
    runtime=None,
    access_identity=None,
    device_id=None,
    access_prechecked=False,
    track_activity=True,
):
    """Launch a full scraper run for the given source URL."""

    source = normalize_source(source)
    clean_license = resolve_access_identity(device_id=device_id, access_identity=access_identity)
    if not access_prechecked:
        clean_license = require_admin_access(clean_license, source, input_url, logger=logger)

    activity_id = (
        db_manager.track_start(source, input_url, license_key=clean_license)
        if track_activity
        else None
    )
    stats = init_stats()

    async with async_playwright() as p:
        set_active_source(source, out_filename=out_filename)
        search_country = compact_whitespace(country) or infer_country_from_url(input_url)
        if runtime:
            runtime.start_run(
                source,
                input_url,
                max_pages=max_pages,
                max_profiles=max_profiles,
            )
        context = None
        stop_monitor_task = None
        status_map = None
        context_closed = False
        try:
            context = await launch_persistent_browser(p, headless=headless, logger=logger)
            context.set_default_timeout(60000)

            async def close_context_on_stop():
                nonlocal context_closed
                while context and not stop_requested(runtime, stop_event):
                    await asyncio.sleep(0.2)
                if context and not context_closed:
                    logger("[SYSTEM] Stop requested. Closing browser context...")
                    context_closed = True
                    with contextlib.suppress(PlaywrightError):
                        await context.close()

            stop_monitor_task = asyncio.create_task(close_context_on_stop())

            ensure_output_files()

            status_map = load_statuses()
            unique_emails_all = load_master_emails()
            detail_keys = load_existing_detail_keys()
            output_file = get_active_output_file()
            detail_output_file = get_active_detail_output_file()

            with (
                open(output_file, "a", newline="", encoding="utf-8") as master_file,
                open(detail_output_file, "a", newline="", encoding="utf-8") as detail_file,
            ):
                master_writer = csv.writer(master_file)
                detail_writer = csv.writer(detail_file)

                logger(f"[*] Starting Search: {input_url}")
                logger(f"[*] Source: {source.upper()}")

                if source == "bbb":
                    await run_bbb_search(
                        context,
                        input_url,
                        master_writer,
                        master_file,
                        detail_writer,
                        detail_file,
                        unique_emails_all,
                        detail_keys,
                        status_map,
                        stats,
                        max_pages=max_pages,
                        max_profiles=max_profiles,
                        retry_no_email=retry_no_email,
                        stop_event=stop_event,
                        logger=logger,
                        runtime=runtime,
                    )
                else:
                    logger(f"[*] Google FB fallback country: {search_country}")
                    await run_houzz_search(
                        context,
                        input_url,
                        master_writer,
                        master_file,
                        detail_writer,
                        detail_file,
                        unique_emails_all,
                        detail_keys,
                        status_map,
                        stats,
                        max_pages=max_pages,
                        max_profiles=max_profiles,
                        skip_facebook=skip_facebook,
                        skip_google_fallback=skip_google_fallback,
                        search_country=search_country,
                        retry_no_email=retry_no_email,
                        logger=logger,
                        stop_event=stop_event,
                        runtime=runtime,
                    )

            write_statuses(status_map)
            if auto_export_final and not stop_requested(runtime, stop_event):
                export_result = export_final_emails(quality_filter)
                if runtime:
                    runtime.record_export(export_result)
                logger(
                    f"[DONE] Final clean emails exported to {export_result['final_output_file']}"
                )
                logger(f"[DONE] Final detail exported to {export_result['final_detail_file']}")
                logger(f"[DONE] Excel export written to {export_result['excel_export_file']}")
                logger(
                    f"[DONE] Duplicate report written to {export_result['duplicate_report_file']}"
                )
            print_summary(stats, logger=logger)
            logger(f"\n[DONE] Master data saved to {output_file}")
            logger(f"[DONE] Detailed data saved to {detail_output_file}")
            _finish_activity(activity_id, stats["master_saved"], "completed")
            if runtime:
                runtime.complete_run()
        except SCRAPER_RUN_ERRORS as exc:
            if status_map is not None:
                write_statuses(status_map)
            if stop_requested(runtime, stop_event):
                logger("[SYSTEM] Stop completed. Browser work was interrupted safely.")
                _finish_activity(activity_id, stats["master_saved"], "stopped")
                if runtime:
                    runtime.complete_run()
                return
            _finish_activity(activity_id, stats["master_saved"], f"failed: {exc}")
            if runtime:
                runtime.complete_run(error_message=str(exc))
            raise
        finally:
            if stop_monitor_task:
                stop_monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_monitor_task
            if context and not context_closed:
                context_closed = True
                with contextlib.suppress(PlaywrightError):
                    await context.close()


def export_final_for_source(
    source,
    quality_filter=None,
    out_filename=None,
    logger=print,
    access_identity=None,
    device_id=None,
    access_prechecked=False,
):
    """Export final quality-filtered emails for a source without scraping."""
    source = normalize_source(source)
    clean_license = resolve_access_identity(device_id=device_id, access_identity=access_identity)
    if not access_prechecked:
        require_admin_access(clean_license, source, "export_final_only", logger=logger)
    set_active_source(source, out_filename=out_filename)
    ensure_output_files()
    export_result = export_final_emails(quality_filter)
    logger(f"[DONE] Exported {export_result['count']} {source.upper()} emails")
    logger(f"[DONE] Final clean emails: {export_result['final_output_file']}")
    logger(f"[DONE] Final detail: {export_result['final_detail_file']}")
    logger(f"[DONE] Excel export: {export_result['excel_export_file']}")
    logger(
        f"[DONE] Duplicate report: {export_result['duplicate_report_file']} "
        f"({export_result['duplicate_count']} duplicate emails)"
    )
    return export_result


async def run_houzz_search(
    context,
    input_url,
    master_writer,
    master_file,
    detail_writer,
    detail_file,
    unique_emails_all,
    detail_keys,
    status_map,
    stats,
    max_pages=None,
    max_profiles=None,
    skip_facebook=False,
    skip_google_fallback=False,
    search_country=DEFAULT_SEARCH_COUNTRY,
    retry_no_email=False,
    logger=print,
    stop_event=None,
    runtime=None,
):
    """Paginate a Houzz search URL and process each professional profile."""

    site_cache = {}
    facebook_cache = {}
    google_cache = {}

    main_page = await context.new_page()
    await Stealth().apply_stealth_async(main_page)

    try:
        semaphore = asyncio.Semaphore(CONCURRENT_PROFILES)

        async def profile_worker(pro_link):
            async with semaphore:
                if runtime:
                    await runtime.wait_if_paused()
                if stop_requested(runtime, stop_event):
                    return
                # Add a small staggered start to avoid hitting the server with all workers at once
                if await responsive_sleep(random.uniform(0.2, 0.8), runtime, stop_event):
                    return

                stats["profiles_attempted"] += 1
                if runtime:
                    runtime.record_attempted_profile(pro_link)

                result = await process_profile(
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
                    allow_facebook=not skip_facebook,
                    allow_google_fallback=not skip_google_fallback,
                    country=search_country or DEFAULT_SEARCH_COUNTRY,
                    logger=logger,
                    runtime=runtime,
                    stop_event=stop_event,
                )

                if result["status"] in stats:
                    stats[result["status"]] += 1
                stats["master_saved"] += result["master_saved"]
                stats["detail_saved"] += result["detail_saved"]
                if runtime:
                    runtime.record_profile_result(pro_link, result)

                # Signal service to update DB
                if hasattr(runtime, "service") and runtime.service:
                    runtime.service.record_profile_result(pro_link, result)

        await goto_with_retry(
            main_page,
            input_url,
            "houzz_search_init",
            timeout_ms=PROFILE_TIMEOUT_MS,
            logger=logger,
        )

        page_count = 1
        stop_requested_flag = False

        while True:
            if runtime:
                await runtime.wait_if_paused()
            if stop_requested(runtime, stop_event):
                logger("\n[*] Stop requested. Ending Houzz run.")
                break
            logger(f"\n--- Houzz Search Page {page_count} ---")
            links = await main_page.eval_on_selector_all(
                "a.hz-pro-ctl",
                "elements => elements.map(el => el.href)",
            )
            unique_links = unique_preserve_order(links)
            if runtime:
                runtime.register_page(page_count, len(unique_links))

            logger(f"Found {len(unique_links)} professionals.")

            tasks = []
            scheduled_profiles = 0
            for pro_link in unique_links:
                if runtime:
                    await runtime.wait_if_paused()
                if stop_requested(runtime, stop_event):
                    logger("[!] Stop signal received. Finishing up...")
                    stop_requested_flag = True
                    break

                existing_status = status_map.get(pro_link, {})
                previous_status = existing_status.get("status")
                if previous_status == "processed" or (
                    previous_status == "no_email" and not retry_no_email
                ):
                    stats["profiles_skipped"] += 1
                    if runtime:
                        runtime.record_skipped_profile(pro_link)
                    continue

                if (
                    max_profiles
                    and (stats["profiles_attempted"] + scheduled_profiles) >= max_profiles
                ):
                    stop_requested_flag = True
                    break

                if previous_status == "failed":
                    logger(f"\n[~] Retrying failed profile: {pro_link}")

                tasks.append(asyncio.create_task(profile_worker(pro_link)))
                scheduled_profiles += 1

            if tasks:
                await asyncio.gather(*tasks)

            if stop_requested_flag:
                if (stop_event and stop_event.is_set()) or (
                    runtime and runtime.is_stop_requested()
                ):
                    logger("\n[*] Stop requested. Ending Houzz run.")
                else:
                    logger("\n[*] Reached max profile limit.")
                break

            if max_pages and page_count >= max_pages:
                logger("\n[*] Reached max page limit.")
                break

            next_btn = await main_page.query_selector("a.hz-pagination-link--next")
            if next_btn:
                logger("\n[*] Moving to next Houzz search results page...")
                await next_btn.click()
                await main_page.wait_for_load_state("domcontentloaded")
                page_count += 1
                if await responsive_sleep(random.uniform(2.0, 4.0), runtime, stop_event):
                    logger("\n[*] Stop requested. Ending Houzz run.")
                    break
            else:
                logger("\n[*] All pages finished.")
                break
    finally:
        await main_page.close()


def normalize_source(source):
    """Normalize user input to the canonical ``houzz`` or ``bbb`` source name."""
    clean_source = compact_whitespace(source).lower()
    if clean_source in {"1", "houzz", "house", "h"}:
        return "houzz"
    if clean_source in {"2", "bbb", "b"}:
        return "bbb"
    return "houzz"


def prompt_source():
    """Prompt the CLI user to choose the source site."""
    print("Select website:")
    print("1) Houzz")
    print("2) BBB")
    return normalize_source(input("Enter option 1 or 2: ").strip())


def parse_args():
    """Parse CLI arguments for the scraper entry point."""
    parser = argparse.ArgumentParser(description="Houzz/BBB email scraper")
    parser.add_argument(
        "--source",
        choices=["houzz", "bbb", "1", "2"],
        help="Website source to scrape",
    )
    parser.add_argument("--url", help="Search results URL for the selected source")
    parser.add_argument("--max-pages", type=int, help="Stop after N result pages")
    parser.add_argument("--max-profiles", type=int, help="Stop after N profiles in this run")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--skip-facebook", action="store_true", help="Do not check Facebook pages")
    parser.add_argument("--country", help="Country name for Google Facebook fallback, e.g. USA")
    parser.add_argument(
        "--skip-google-fallback",
        action="store_true",
        help="Do not use Google to find missing Facebook pages",
    )
    parser.add_argument(
        "--retry-no-email",
        action="store_true",
        help="Retry profiles previously marked no_email",
    )
    parser.add_argument(
        "--no-final-export",
        action="store_true",
        help="Do not export final quality-filtered email CSV after scraping",
    )
    parser.add_argument(
        "--out-filename",
        help="Custom name for the output CSV file (e.g. leads_today.csv)",
    )
    parser.add_argument(
        "--export-final-only",
        action="store_true",
        help="Export final quality-filtered email CSV without scraping",
    )
    parser.add_argument(
        "--quality-filter",
        nargs="+",
        choices=["high", "medium", "low"],
        default=["high", "medium"],
        help="Email qualities to include in final export",
    )
    parser.add_argument(
        "--device-id",
        help=(
            "Optional device identity override for admin approval. If omitted, "
            f"{DEVICE_ID_ENV_VAR} or the automatic machine ID is used."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Parse CLI arguments and launch the appropriate scraper."""
    args = parse_args()
    source = normalize_source(args.source) if args.source else prompt_source()
    device_id = resolve_access_identity(device_id=args.device_id)

    try:
        if args.export_final_only:
            export_final_for_source(source, args.quality_filter, device_id=device_id)
            raise SystemExit(0)

        label = "BBB" if source == "bbb" else "Houzz"
        url_to_scrape = (args.url or input(f"Enter {label} Search URL: ").strip()).strip()
        if url_to_scrape:
            asyncio.run(
                run_scraper(
                    url_to_scrape,
                    source=source,
                    max_pages=args.max_pages,
                    max_profiles=args.max_profiles,
                    headless=args.headless,
                    skip_facebook=args.skip_facebook,
                    country=args.country,
                    skip_google_fallback=args.skip_google_fallback,
                    auto_export_final=not args.no_final_export,
                    quality_filter=args.quality_filter,
                    retry_no_email=args.retry_no_email,
                    out_filename=args.out_filename,
                    device_id=device_id,
                )
            )
        else:
            print("URL is required.")
    except PermissionError as exc:
        print(f"[SYSTEM] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
