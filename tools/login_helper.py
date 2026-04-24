"""Launch a persistent browser session for manual account login.

Run this helper as ``python -m tools.login_helper`` from the project root so
the ``scraper`` package resolves naturally without path mutation hacks.
"""

import asyncio

from playwright.async_api import async_playwright

if __package__ in {None, ""}:
    raise SystemExit("Run this helper as `python -m tools.login_helper` from the project root.")

from scraper.browser_launcher import (  # pylint: disable=wrong-import-position
    launch_persistent_browser,
)
from scraper.config import USER_DATA_DIR  # pylint: disable=wrong-import-position


async def run() -> None:
    """Open Facebook in a persistent browser profile for interactive login."""
    async with async_playwright() as p:
        print(f"[*] Opening browser with persistent profile in: {USER_DATA_DIR}")
        print("[*] Please log in to Facebook and any other sites needed.")
        print("[*] CLOSE the browser window manually when you are done.")

        context = await launch_persistent_browser(p, headless=False)

        page = await context.new_page()
        await page.goto("https://www.facebook.com")

        while len(context.pages) > 0:
            await asyncio.sleep(1)

        print("[*] Browser closed. Session saved.")


def main() -> None:
    """Start the asynchronous login helper."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
