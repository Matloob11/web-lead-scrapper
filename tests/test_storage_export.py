"""Tests for final export filtering and deduplication behavior."""

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.config import DETAIL_HEADERS
from scraper.storage import csv_storage


class StorageExportTests(unittest.TestCase):
    """Validate final export generation from the detailed results CSV."""

    def test_custom_output_filename_stays_inside_project_root(self):
        paths = csv_storage.get_source_paths("houzz", r"..\..\outside")
        output_path = Path(paths["output_file"])

        self.assertEqual(output_path.name, "outside.csv")
        self.assertEqual(output_path.parent, Path(csv_storage.HOUZZ_OUTPUT_FILE).parent)

    def test_custom_output_filename_replaces_invalid_chars(self):
        paths = csv_storage.get_source_paths("bbb", "bad:name")
        self.assertEqual(Path(paths["output_file"]).name, "bad_name.csv")

    def test_export_quality_filter_accepts_single_string(self):
        self.assertEqual(csv_storage.normalize_quality_filter("HIGH"), {"high"})

    def test_export_final_emails_filters_quality_and_dedupes(self):
        """Ensure final exports keep allowed qualities and remove duplicate emails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            detail_file = root / "details.csv"
            final_file = root / "final.csv"
            final_detail_file = root / "final_detail.csv"

            with detail_file.open("w", newline="", encoding="utf-8") as file_obj:
                writer = csv.DictWriter(file_obj, fieldnames=DETAIL_HEADERS)
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "email": "high@examplebuilder.com",
                            "name": "Example Builder",
                            "houzz_profile": "profile-1",
                            "website": "https://examplebuilder.com",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "high",
                            "email_quality_reason": "business_domain_generic_inbox",
                            "saved_to_master_output": "1",
                        },
                        {
                            "email": "high@examplebuilder.com",
                            "name": "Example Builder Duplicate",
                            "houzz_profile": "profile-2",
                            "website": "https://examplebuilder.com",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "high",
                            "email_quality_reason": "business_domain_generic_inbox",
                            "saved_to_master_output": "0",
                        },
                        {
                            "email": "low@gmail.com",
                            "name": "Low Quality",
                            "houzz_profile": "profile-3",
                            "website": "https://lowquality.com",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "low",
                            "email_quality_reason": "generic_free_email",
                            "saved_to_master_output": "1",
                        },
                    ]
                )

            original_paths = dict(csv_storage.ACTIVE_PATHS)
            try:
                csv_storage.ACTIVE_PATHS.update(
                    {
                        "source": "houzz",
                        "detail_output_file": str(detail_file),
                        "final_output_file": str(final_file),
                        "final_detail_file": str(final_detail_file),
                        "excel_export_file": str(root / "export.xlsx"),
                        "duplicate_report_file": str(root / "duplicates.csv"),
                        "high_quality_output_file": str(root / "high.csv"),
                        "high_quality_detail_file": str(root / "high_detail.csv"),
                        "medium_quality_output_file": str(root / "medium.csv"),
                        "medium_quality_detail_file": str(root / "medium_detail.csv"),
                        "low_quality_output_file": str(root / "low.csv"),
                        "low_quality_detail_file": str(root / "low_detail.csv"),
                        "fail_log_file": str(root / "failures.csv"),
                    }
                )
                result = csv_storage.export_final_emails(["high"])
            finally:
                csv_storage.ACTIVE_PATHS.clear()
                csv_storage.ACTIVE_PATHS.update(original_paths)

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["duplicate_count"], 1)
            self.assertTrue(Path(result["excel_export_file"]).exists())
            self.assertTrue(Path(result["duplicate_report_file"]).exists())
            self.assertEqual(result["quality_files"]["high"]["count"], 1)
            self.assertEqual(result["quality_files"]["low"]["count"], 1)

            with final_file.open(newline="", encoding="utf-8") as file_obj:
                rows = list(csv.reader(file_obj))
            self.assertEqual(rows, [["Email"], ["high@examplebuilder.com"]])

            with final_detail_file.open(newline="", encoding="utf-8") as file_obj:
                detail_rows = list(csv.DictReader(file_obj))
            self.assertEqual(len(detail_rows), 1)
            self.assertEqual(detail_rows[0], {"Email": "high@examplebuilder.com"})

            with Path(result["duplicate_report_file"]).open(
                newline="",
                encoding="utf-8",
            ) as file_obj:
                duplicate_rows = list(csv.DictReader(file_obj))
            self.assertEqual(
                duplicate_rows[0],
                {"Email": "high@examplebuilder.com", "Duplicate Rows": "2"},
            )


if __name__ == "__main__":
    unittest.main()
