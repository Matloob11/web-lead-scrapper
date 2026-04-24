import random

from scraper.config import BROWSER_EXECUTABLE_CANDIDATES, USER_AGENTS, USER_DATA_DIR


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def find_browser_executable():
    for candidate in BROWSER_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def build_launch_options(headless, user_agent, executable_path=None):
    """Build Playwright browser launch options from user-selected settings."""
    launch_options = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 800},
        "user_agent": user_agent,
        "ignore_https_errors": True,
    }
    if executable_path:
        launch_options["executable_path"] = executable_path
    return launch_options


async def launch_persistent_browser(playwright, headless=False, logger=None):
    # Pick a random User-Agent for rotation
    selected_ua = random.choice(USER_AGENTS)
    _log(logger, f"[*] Rotating User-Agent: {selected_ua[:50]}...")
    _log(logger, f"[*] Browser mode: {'hidden/headless' if headless else 'visible'}")

    executable_path = find_browser_executable()
    launch_options = build_launch_options(headless, selected_ua, executable_path)
    if executable_path:
        _log(logger, f"[*] Using browser: {executable_path}")
    else:
        _log(logger, "[*] Using Playwright bundled Chromium")

    return await playwright.chromium.launch_persistent_context(USER_DATA_DIR, **launch_options)
