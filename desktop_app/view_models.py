"""Presentation helpers for dashboard-friendly runtime and summary values."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeAlias

RuntimeSnapshotDict: TypeAlias = dict[str, Any]
SummarySnapshotDict: TypeAlias = dict[str, Any]


def safe_int(value: str | None) -> int | None:
    """Convert an optional string to an integer when a value is present."""
    if value is None:
        return None
    clean_value = value.strip()
    if not clean_value:
        return None
    try:
        parsed_value = int(clean_value)
    except ValueError:
        return None
    return parsed_value if parsed_value > 0 else None


def build_progress_note(runtime: RuntimeSnapshotDict) -> str:
    """Build a short dashboard progress note from the current runtime snapshot."""
    progress_ratio = float(runtime.get("progress_ratio", 0.0) or 0.0)
    if runtime.get("max_profiles"):
        return (
            f"{runtime.get('checked_total', 0)} of "
            f"{runtime.get('max_profiles')} profile slots consumed "
            f"({round(progress_ratio * 100)}%)."
        )
    if runtime.get("max_pages"):
        return (
            f"Page {runtime.get('current_page', 0)} of "
            f"{runtime.get('max_pages')} targeted pages "
            f"({round(progress_ratio * 100)}%)."
        )
    return "Live crawl mode: progress is open-ended until you stop it or the source finishes."


def format_source(source: str) -> str:
    """Format a scraper source value for display in the dashboard."""
    return "BBB" if source == "bbb" else "Houzz"


def format_timestamp(value: str) -> str:
    """Format an ISO timestamp for dashboard display."""
    if not value:
        return "No timestamp yet"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d %b %Y %I:%M %p")


def summary_file_paths(summary: SummarySnapshotDict) -> list[str]:
    """Return file paths from a summary, accepting current and legacy shapes."""
    files = summary.get("files", {})
    path_values: list[str] = []
    if isinstance(files, dict):
        path_values = [
            value
            for key, value in files.items()
            if isinstance(key, str)
            and key != "source"
            and key.endswith("_file")
            and isinstance(value, str)
            and value
        ]
    elif isinstance(files, (list, tuple, set)):
        path_values = [path for path in files if isinstance(path, str) and path]
    else:
        return []
    return path_values
