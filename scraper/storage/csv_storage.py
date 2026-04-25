"""CSV storage layer for master, detail, status, final, and failure log files."""

import csv
import os
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from scraper.config import (
    BBB_DETAIL_OUTPUT_FILE,
    BBB_FAIL_LOG_FILE,
    BBB_FINAL_DETAIL_FILE,
    BBB_FINAL_OUTPUT_FILE,
    BBB_OUTPUT_FILE,
    BBB_STATUS_FILE,
    CSV_OUTPUT_DIR,
    DETAIL_HEADERS,
    FINAL_DETAIL_HEADERS,
    FINAL_OUTPUT_DIR,
    HOUZZ_DETAIL_OUTPUT_FILE,
    HOUZZ_FAIL_LOG_FILE,
    HOUZZ_FINAL_DETAIL_FILE,
    HOUZZ_FINAL_OUTPUT_FILE,
    HOUZZ_OUTPUT_FILE,
    HOUZZ_STATUS_FILE,
    LEGACY_PROGRESS_FILE,
    LOG_OUTPUT_DIR,
    MASTER_HEADERS,
    STATUS_HEADERS,
)
from scraper.filters.email_filters import is_valid_email_candidate
from scraper.filters.email_quality import score_email_quality

QUALITY_LEVELS = ("high", "medium", "low")
QUALITY_RANK = {"high": 3, "medium": 2, "low": 1}
DUPLICATE_REPORT_HEADERS = ["Email", "Duplicate Rows"]
INVALID_FILENAME_CHARS = '<>:"/\\|?*'

ACTIVE_PATHS = {
    "source": "houzz",
    "output_file": HOUZZ_OUTPUT_FILE,
    "detail_output_file": HOUZZ_DETAIL_OUTPUT_FILE,
    "status_file": HOUZZ_STATUS_FILE,
    "fail_log_file": HOUZZ_FAIL_LOG_FILE,
    "final_output_file": HOUZZ_FINAL_OUTPUT_FILE,
    "final_detail_file": HOUZZ_FINAL_DETAIL_FILE,
}


def get_extra_export_paths(source):
    """Return extra export artifacts generated for one source."""
    clean_source = (source or "houzz").lower()
    paths = {
        "excel_export_file": str(FINAL_OUTPUT_DIR / f"{clean_source}_email_export.xlsx"),
        "duplicate_report_file": str(
            FINAL_OUTPUT_DIR / f"{clean_source}_duplicate_email_report.csv"
        ),
    }
    for quality in QUALITY_LEVELS:
        paths[f"{quality}_quality_output_file"] = str(
            FINAL_OUTPUT_DIR / f"{clean_source}_{quality}_quality_emails.csv"
        )
        paths[f"{quality}_quality_detail_file"] = str(
            FINAL_OUTPUT_DIR / f"{clean_source}_{quality}_quality_email_details.csv"
        )
    return paths


def _clean_output_filename(out_filename):
    """Return a safe CSV filename, discarding any user-provided directories."""
    raw_filename = str(out_filename or "").strip()
    if not raw_filename:
        return None

    filename = PureWindowsPath(PurePosixPath(raw_filename).name).name
    filename = "".join(
        "_" if char in INVALID_FILENAME_CHARS or ord(char) < 32 else char
        for char in filename
    ).strip(" .")
    if not filename:
        return None
    if not filename.lower().endswith(".csv"):
        filename = f"{filename}.csv"
    return filename


def get_source_paths(source="houzz", out_filename=None):
    """Return the filesystem paths for all scraper output types for a source."""
    clean_out_filename = _clean_output_filename(out_filename)
    if source == "bbb":
        paths = {
            "source": "bbb",
            "output_file": BBB_OUTPUT_FILE,
            "detail_output_file": BBB_DETAIL_OUTPUT_FILE,
            "status_file": BBB_STATUS_FILE,
            "fail_log_file": BBB_FAIL_LOG_FILE,
            "final_output_file": BBB_FINAL_OUTPUT_FILE,
            "final_detail_file": BBB_FINAL_DETAIL_FILE,
        }
        if clean_out_filename:
            paths["output_file"] = os.path.join(
                os.path.dirname(BBB_OUTPUT_FILE),
                clean_out_filename,
            )
        paths.update(get_extra_export_paths("bbb"))
        return paths

    paths = {
        "source": "houzz",
        "output_file": HOUZZ_OUTPUT_FILE,
        "detail_output_file": HOUZZ_DETAIL_OUTPUT_FILE,
        "status_file": HOUZZ_STATUS_FILE,
        "fail_log_file": HOUZZ_FAIL_LOG_FILE,
        "final_output_file": HOUZZ_FINAL_OUTPUT_FILE,
        "final_detail_file": HOUZZ_FINAL_DETAIL_FILE,
    }
    if clean_out_filename:
        paths["output_file"] = os.path.join(
            os.path.dirname(HOUZZ_OUTPUT_FILE),
            clean_out_filename,
        )
    paths.update(get_extra_export_paths("houzz"))
    return paths


def set_active_source(source="houzz", out_filename=None):
    """Set the source whose output files should be treated as active."""
    ACTIVE_PATHS.update(get_source_paths(source, out_filename=out_filename))
    return dict(ACTIVE_PATHS)


def get_active_output_file():
    """Return the active master email CSV path."""
    return ACTIVE_PATHS["output_file"]


def get_active_detail_output_file():
    """Return the active detailed results CSV path."""
    return ACTIVE_PATHS["detail_output_file"]


def get_active_status_file():
    """Return the active status CSV path."""
    return ACTIVE_PATHS["status_file"]


def get_active_fail_log_file():
    """Return the active failure log CSV path."""
    return ACTIVE_PATHS["fail_log_file"]


def get_active_final_output_file():
    """Return the active final clean-email CSV path."""
    return ACTIVE_PATHS["final_output_file"]


def get_active_final_detail_file():
    """Return the active final detailed export CSV path."""
    return ACTIVE_PATHS["final_detail_file"]


def get_active_extra_export_path(key):
    """Return an active extra export path, deriving it if old test paths are patched in."""
    if key in ACTIVE_PATHS:
        return ACTIVE_PATHS[key]
    source = ACTIVE_PATHS.get("source", "houzz")
    final_dir = os.path.dirname(ACTIVE_PATHS.get("final_output_file", ""))
    if final_dir:
        if key == "excel_export_file":
            return os.path.join(final_dir, f"{source}_email_export.xlsx")
        if key == "duplicate_report_file":
            return os.path.join(final_dir, f"{source}_duplicate_email_report.csv")
        for quality in QUALITY_LEVELS:
            if key == f"{quality}_quality_output_file":
                return os.path.join(final_dir, f"{source}_{quality}_quality_emails.csv")
            if key == f"{quality}_quality_detail_file":
                return os.path.join(
                    final_dir,
                    f"{source}_{quality}_quality_email_details.csv",
                )
    return get_extra_export_paths(ACTIVE_PATHS.get("source", "houzz"))[key]


def ensure_parent_dir(path):
    """Create the parent directory for *path* when it does not exist."""
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def ensure_csv_header(path, headers):
    """Create a CSV file with *headers* if it does not already exist."""
    ensure_parent_dir(path)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        migrate_detail_csv_if_needed(path)
        return
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(headers)


def _quality_rank(row):
    quality = (row.get("email_quality") or row.get("Quality") or "").strip().lower()
    saved = str(row.get("saved_to_master_output", "")).strip() == "1"
    return QUALITY_RANK.get(quality, 0), int(saved)


def _pick_best_row(existing_row, candidate_row):
    """Keep the row with the strongest quality/confidence for a deduped email."""
    if existing_row is None:
        return candidate_row
    if _quality_rank(candidate_row) > _quality_rank(existing_row):
        return candidate_row
    return existing_row


def _final_detail_row(row):
    """Map an internal detail CSV row into the email-only final export schema."""
    return {"Email": (row.get("email") or "").strip().lower()}


def _write_email_csv(path, rows):
    """Write a one-column email CSV."""
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(MASTER_HEADERS)
        for row in rows:
            writer.writerow([row["Email"]])


def _write_detail_csv(path, rows):
    """Write a final detail CSV."""
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=FINAL_DETAIL_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _cell_ref(row_number, column_number):
    """Return an Excel cell reference for 1-based row and column numbers."""
    letters = ""
    column = column_number
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_number}"


def _sheet_xml(rows):
    """Build a tiny XLSX worksheet using inline strings."""
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell = _cell_ref(row_index, column_index)
            clean_value = escape(str(value or ""))
            cells.append(f'<c r="{cell}" t="inlineStr"><is><t>{clean_value}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml)}</sheetData></worksheet>"
    )


def _write_xlsx(path, sheets):
    """Write a dependency-free Excel workbook for exported email data."""
    ensure_parent_dir(path)
    sheet_names = [name[:31] for name, _ in sheets]
    sheet_entries = []
    relationship_entries = []
    workbook_overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    ]

    for index, sheet_name in enumerate(sheet_names, start=1):
        safe_name = escape(sheet_name, {'"': "&quot;"})
        sheet_entries.append(f'<sheet name="{safe_name}" sheetId="{index}" r:id="rId{index}"/>')
        relationship_entries.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        workbook_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.worksheet+xml"/>'
        )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(workbook_overrides)}</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheet_entries)}</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(relationship_entries)}</Relationships>"
    )

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("_rels/.rels", root_rels)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for index, (_, rows) in enumerate(sheets, start=1):
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))


def migrate_detail_csv_if_needed(path):
    """Upgrade an existing detail CSV to the current header schema when required."""
    if os.path.basename(path) not in {"houzz_results_detailed.csv", "bbb_results_detailed.csv"}:
        return

    try:
        with open(path, encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            rows = list(reader)
            fieldnames = reader.fieldnames or []
    except (csv.Error, OSError) as exc:
        log_failure("detail_migration_load", path, exc)
        return

    if fieldnames == DETAIL_HEADERS:
        return

    migrated_rows = []
    for row in rows:
        sources = set(filter(None, (row.get("sources") or "").split("|")))
        quality, reason = score_email_quality(
            row.get("email", ""),
            business_name=row.get("name", ""),
            website=row.get("website", ""),
            sources=sources,
        )
        row["email_quality"] = row.get("email_quality") or quality
        row["email_quality_reason"] = row.get("email_quality_reason") or reason
        migrated_rows.append({header: row.get(header, "") for header in DETAIL_HEADERS})

    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DETAIL_HEADERS)
        writer.writeheader()
        writer.writerows(migrated_rows)


def ensure_output_files():
    """Create all output folders and CSV files needed for the active source."""
    os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)
    ensure_csv_header(get_active_output_file(), MASTER_HEADERS)
    ensure_csv_header(get_active_detail_output_file(), DETAIL_HEADERS)
    ensure_csv_header(get_active_status_file(), STATUS_HEADERS)


def load_master_emails():
    """Load existing master emails for the active source into a set."""
    emails = set()
    output_file = get_active_output_file()
    if not os.path.exists(output_file):
        return emails

    try:
        with open(output_file, encoding="utf-8", newline="") as file_obj:
            reader = csv.reader(file_obj)
            for row in reader:
                if row and is_valid_email_candidate(row[0].strip()):
                    emails.add(row[0].lower().strip())
    except (csv.Error, OSError) as exc:
        log_failure("output_load", output_file, exc)
    return emails


def load_existing_detail_keys():
    """Load existing ``(email, profile_url)`` keys from the detail CSV."""
    keys = set()
    detail_output_file = get_active_detail_output_file()
    if not os.path.exists(detail_output_file) or os.path.getsize(detail_output_file) == 0:
        return keys

    try:
        with open(detail_output_file, encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                profile_url = (row.get("houzz_profile") or "").strip()
                if email and profile_url and is_valid_email_candidate(email):
                    keys.add((email, profile_url))
    except (csv.Error, OSError) as exc:
        log_failure("detail_output_load", detail_output_file, exc)
    return keys


def load_statuses():
    """Load the active source status map, including legacy progress when present."""
    status_map = {}

    if os.path.exists(LEGACY_PROGRESS_FILE):
        with open(LEGACY_PROGRESS_FILE, encoding="utf-8") as file_obj:
            for line in file_obj:
                profile_url = line.strip()
                if profile_url:
                    status_map[profile_url] = {
                        "status": "processed",
                        "detail": "legacy_progress",
                        "updated_at": "",
                    }

    status_file = get_active_status_file()
    if not os.path.exists(status_file) or os.path.getsize(status_file) == 0:
        return status_map

    with open(status_file, encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            profile_url = (row.get("profile_url") or "").strip()
            if not profile_url:
                continue
            status_map[profile_url] = {
                "status": (row.get("status") or "").strip(),
                "detail": (row.get("detail") or "").strip(),
                "updated_at": (row.get("updated_at") or "").strip(),
            }
    return status_map


def write_statuses(status_map):
    """Rewrite the status CSV from the provided in-memory status map."""
    status_file = get_active_status_file()
    ensure_parent_dir(status_file)
    with open(status_file, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(STATUS_HEADERS)
        for profile_url in sorted(status_map):
            row = status_map[profile_url]
            writer.writerow(
                [
                    profile_url,
                    row.get("status", ""),
                    row.get("detail", ""),
                    row.get("updated_at", ""),
                ]
            )


def append_status_row(profile_url, status, detail, updated_at):
    """Append one status row to the active status CSV."""
    status_file = get_active_status_file()
    ensure_csv_header(status_file, STATUS_HEADERS)
    with open(status_file, "a", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow([profile_url, status, detail, updated_at])


def record_status(status_map, profile_url, status, detail=""):
    """Update the in-memory status map and append the same status row to disk."""
    updated_at = datetime.now().isoformat(timespec="seconds")
    status_map[profile_url] = {
        "status": status,
        "detail": detail,
        "updated_at": updated_at,
    }
    append_status_row(profile_url, status, detail, updated_at)


def log_failure(step, target_url, error, profile_url=""):
    """Append one failure row to the active failure log CSV."""
    fail_log_file = get_active_fail_log_file()
    ensure_parent_dir(fail_log_file)
    file_exists = os.path.exists(fail_log_file) and os.path.getsize(fail_log_file) > 0
    with open(fail_log_file, "a", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        if not file_exists:
            writer.writerow(["timestamp", "step", "profile_url", "target_url", "error"])
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                step,
                profile_url,
                target_url,
                str(error),
            ]
        )


def write_detail_rows(
    detail_writer,
    detail_file,
    detail_keys,
    email_sources,
    name,
    pro_link,
    website_final,
    facebook_final,
    new_master_emails,
):
    """Write unique detailed email rows for one processed profile."""
    detail_rows_added = 0

    for email in sorted(email_sources):
        if not is_valid_email_candidate(email):
            continue

        source_set = email_sources[email]
        sources = "|".join(sorted(source_set))
        quality, reason = score_email_quality(
            email,
            business_name=name,
            website=website_final,
            sources=source_set,
        )
        key = (email, pro_link)
        saved_to_master_output = 1 if email in new_master_emails else 0

        if key not in detail_keys:
            detail_writer.writerow(
                [
                    email,
                    name,
                    pro_link,
                    website_final,
                    facebook_final,
                    sources,
                    quality,
                    reason,
                    saved_to_master_output,
                ]
            )
            detail_keys.add(key)
            detail_rows_added += 1

    detail_file.flush()
    return detail_rows_added


def write_master_rows(master_writer, master_file, unique_emails_all, valid_emails, logger=None):
    """Write newly discovered emails to the master CSV and return what was added."""
    master_rows_added = 0
    new_master_emails = set()

    for email in sorted(valid_emails):
        if email in unique_emails_all:
            continue
        unique_emails_all.add(email)
        new_master_emails.add(email)
        master_writer.writerow([email])
        master_rows_added += 1
        if logger:
            logger(f"    [SAVED]: {email}")
        else:
            print(f"    [SAVED]: {email}")

    master_file.flush()
    return master_rows_added, new_master_emails


def _load_detail_rows(detail_output_file):
    """Load detail rows from disk, returning an empty list when none exist."""
    if not os.path.exists(detail_output_file) or os.path.getsize(detail_output_file) == 0:
        return []
    with open(detail_output_file, encoding="utf-8", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def _dedupe_rows_by_email(rows, allowed_qualities=None):
    """Select the best detail row per email, optionally by quality."""
    allowed = set(allowed_qualities or QUALITY_LEVELS)
    selected = {}
    for row in rows:
        email = (row.get("email") or "").strip().lower()
        quality = (row.get("email_quality") or "").strip().lower()
        if not email or quality not in allowed or not is_valid_email_candidate(email):
            continue
        row["email"] = email
        row["email_quality"] = quality
        selected[email] = _pick_best_row(selected.get(email), row)
    return [_final_detail_row(selected[email]) for email in sorted(selected)]


def _build_duplicate_rows(rows):
    """Build one duplicate-report row per email that appears in multiple detail rows."""
    grouped = {}
    for row in rows:
        email = (row.get("email") or "").strip().lower()
        if not email or not is_valid_email_candidate(email):
            continue
        grouped.setdefault(email, []).append(row)

    duplicate_rows = []
    for email in sorted(grouped):
        email_rows = grouped[email]
        if len(email_rows) < 2:
            continue
        duplicate_rows.append(
            {
                "Email": email,
                "Duplicate Rows": str(len(email_rows)),
            }
        )
    return duplicate_rows


def normalize_quality_filter(allowed_qualities):
    """Normalize optional export quality filters to known lowercase levels."""
    if allowed_qualities is None:
        return {"high", "medium"}
    raw_qualities = [allowed_qualities] if isinstance(allowed_qualities, str) else allowed_qualities

    qualities = {
        str(quality).strip().lower()
        for quality in raw_qualities
        if str(quality).strip().lower() in QUALITY_LEVELS
    }
    return qualities or {"high", "medium"}


def _write_duplicate_report(path, duplicate_rows):
    """Write duplicate email report rows."""
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DUPLICATE_REPORT_HEADERS)
        writer.writeheader()
        writer.writerows(duplicate_rows)


def _rows_for_xlsx(headers, dict_rows):
    """Turn dictionaries into worksheet rows with a header row."""
    return [headers, *[[row.get(header, "") for header in headers] for row in dict_rows]]


def export_final_emails(allowed_qualities=None):
    """Create final CSV, Excel, duplicate, and quality-split exports."""
    allowed_qualities = normalize_quality_filter(allowed_qualities)
    detail_output_file = get_active_detail_output_file()
    final_output_file = get_active_final_output_file()
    final_detail_file = get_active_final_detail_file()
    excel_export_file = get_active_extra_export_path("excel_export_file")
    duplicate_report_file = get_active_extra_export_path("duplicate_report_file")

    rows = _load_detail_rows(detail_output_file)
    selected_rows = _dedupe_rows_by_email(rows, allowed_qualities)
    duplicate_rows = _build_duplicate_rows(rows)

    _write_email_csv(final_output_file, selected_rows)
    _write_detail_csv(final_detail_file, selected_rows)
    _write_duplicate_report(duplicate_report_file, duplicate_rows)

    quality_files = {}
    xlsx_sheets = [
        ("Selected Emails", _rows_for_xlsx(FINAL_DETAIL_HEADERS, selected_rows)),
    ]
    for quality in QUALITY_LEVELS:
        quality_rows = _dedupe_rows_by_email(rows, {quality})
        output_file = get_active_extra_export_path(f"{quality}_quality_output_file")
        detail_file = get_active_extra_export_path(f"{quality}_quality_detail_file")
        _write_email_csv(output_file, quality_rows)
        _write_detail_csv(detail_file, quality_rows)
        quality_files[quality] = {
            "count": len(quality_rows),
            "output_file": output_file,
            "detail_file": detail_file,
        }
        xlsx_sheets.append((quality.title(), _rows_for_xlsx(FINAL_DETAIL_HEADERS, quality_rows)))

    xlsx_sheets.append(("Duplicates", _rows_for_xlsx(DUPLICATE_REPORT_HEADERS, duplicate_rows)))
    _write_xlsx(excel_export_file, xlsx_sheets)

    return {
        "count": len(selected_rows),
        "final_output_file": final_output_file,
        "final_detail_file": final_detail_file,
        "excel_export_file": excel_export_file,
        "duplicate_report_file": duplicate_report_file,
        "duplicate_count": len(duplicate_rows),
        "quality_files": quality_files,
        "qualities": sorted(allowed_qualities),
    }
