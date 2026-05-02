"""Open a persistent browser session for manual site setup.

Run this helper as ``python -m tools.open_browser`` from the project root so
the ``scraper`` package resolves cleanly in both runtime and static analysis.
"""

import argparse
import asyncio
from urllib.parse import urlparse

from playwright.async_api import async_playwright

if __package__ in {None, ""}:
    raise SystemExit("Run this helper as `python -m tools.open_browser` from the project root.")

from scraper.access_control import require_app_access  # pylint: disable=wrong-import-position
from scraper.browser_launcher import (  # pylint: disable=wrong-import-position
    launch_persistent_browser,
)
from scraper.config import USER_DATA_DIR  # pylint: disable=wrong-import-position


def normalize_helper_url(url: str) -> str:
    """Validate and normalize the manually opened setup URL."""
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed for the helper browser.")
    return cleaned


async def run(url: str) -> None:
    """Open a persistent browser at ``url`` for manual cookie or VPN setup."""
    async with async_playwright() as p:
        print(f"[*] Opening browser with persistent profile in: {USER_DATA_DIR}")
        print("[*] Install/connect your VPN extension, then open BBB.")
        print("[*] Close the browser window when setup is done.")

        context = await launch_persistent_browser(p, headless=False)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        while len(context.pages) > 0:
            await asyncio.sleep(1)

        print("[*] Browser closed. Session saved.")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the manual browser helper."""
    parser = argparse.ArgumentParser(description="Open persistent browser for manual setup")
    parser.add_argument("--url", default="https://www.bbb.org/", help="URL to open")
    return parser.parse_args()


def main() -> None:
    """Start the asynchronous manual browser helper."""
    require_app_access()
    args = parse_args()
    asyncio.run(run(normalize_helper_url(args.url)))


if __name__ == "__main__":
    main()
