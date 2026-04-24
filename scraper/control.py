"""Shared pause/stop helpers for responsive scraper runs."""

import asyncio


def stop_requested(runtime=None, stop_event=None):
    """Return True when either desktop runtime or legacy stop event requested stop."""
    return bool((stop_event and stop_event.is_set()) or (runtime and runtime.is_stop_requested()))


async def responsive_sleep(seconds, runtime=None, stop_event=None, interval=0.2):
    """Sleep in short chunks so pause and stop requests are handled quickly."""
    loop = asyncio.get_running_loop()
    end_time = loop.time() + max(seconds, 0)

    while True:
        if stop_requested(runtime, stop_event):
            return True
        if runtime:
            await runtime.wait_if_paused()

        remaining = end_time - loop.time()
        if remaining <= 0:
            return stop_requested(runtime, stop_event)
        await asyncio.sleep(min(interval, remaining))
