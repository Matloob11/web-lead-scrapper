"""File-based summary helpers for the desktop dashboard."""

import csv
import os
from pathlib import Path

from desktop_app.models import SourceDashboardSummary
from scraper.config import PROJECT_ROOT
from scraper.storage.csv_storage import get_source_paths


def _count_csv_rows(path):
    if not path:
        return 0
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0
    with open(path, encoding="utf-8", newline="") as file_obj:
        return max(sum(1 for _ in file_obj) - 1, 0)


def _read_status_map(path):
    status_map = {}
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return status_map

    with open(path, encoding="utf-8", newline="") as file_obj:
        for row in csv.DictReader(file_obj):
            profile_url = (row.get("profile_url") or "").strip()
            if not profile_url:
                continue
            status_map[profile_url] = {
                "status": (row.get("status") or "").strip().lower(),
                "updated_at": (row.get("updated_at") or "").strip(),
            }
    return status_map


def _read_quality_counts(path):
    counts = {"high": 0, "medium": 0, "low": 0}
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return counts

    with open(path, encoding="utf-8", newline="") as file_obj:
        for row in csv.DictReader(file_obj):
            quality = (row.get("email_quality") or "").strip().lower()
            if quality in counts:
                counts[quality] += 1
    return counts


def build_source_summary(source):
    clean_source = (source or "houzz").lower()
    paths = get_source_paths(clean_source)
    status_map = _read_status_map(paths["status_file"])
    quality_counts = _read_quality_counts(paths["detail_output_file"])

    processed_count = sum(1 for row in status_map.values() if row["status"] == "processed")
    failed_count = sum(1 for row in status_map.values() if row["status"] == "failed")
    no_email_count = sum(1 for row in status_map.values() if row["status"] == "no_email")
    last_updated = max(
        (row["updated_at"] for row in status_map.values() if row["updated_at"]),
        default="",
    )

    return SourceDashboardSummary(
        source=clean_source,
        master_count=_count_csv_rows(paths["output_file"]),
        detail_count=_count_csv_rows(paths["detail_output_file"]),
        final_count=_count_csv_rows(paths["final_output_file"]),
        tracked_profiles=len(status_map),
        processed_count=processed_count,
        failed_count=failed_count,
        no_email_count=no_email_count,
        duplicate_count=_count_csv_rows(paths.get("duplicate_report_file", "")),
        high_quality_count=quality_counts["high"],
        medium_quality_count=quality_counts["medium"],
        low_quality_count=quality_counts["low"],
        last_updated=last_updated,
        files=paths,
    )


def open_path(path):
    """Open a file or directory using the operating system shell."""
    if not path:
        raise FileNotFoundError("Path is required.")
    os.startfile(path)


def reset_source_outputs(source):
    """Delete generated files for one source to prepare a fresh run."""
    clean_source = (source or "houzz").lower()
    paths = get_source_paths(clean_source)
    removable_paths = [
        path
        for key, path in paths.items()
        if key != "source" and key.endswith(("_file", "_output_file", "_detail_file"))
    ]

    project_root = Path(PROJECT_ROOT).resolve()
    removed = []
    for raw_path in removable_paths:
        resolved_path = Path(raw_path).resolve()
        if project_root not in resolved_path.parents and resolved_path != project_root:
            raise ValueError(f"Refusing to delete unexpected path: {resolved_path}")
        if resolved_path.exists() and resolved_path.is_file():
            resolved_path.unlink()
            removed.append(str(resolved_path))
    return removed
