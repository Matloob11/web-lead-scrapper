"""Tests for Google fallback search status tracking."""

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.search.google_facebook_search import (
    is_google_verification_page,
    record_google_fallback_status,
)


class GoogleFallbackSearchTests(unittest.TestCase):
    """Validate captcha detection and Google fallback status persistence."""

    def test_google_verification_page_is_detected_from_url_or_text(self):
        self.assertTrue(
            is_google_verification_page(
                "https://www.google.com/sorry/index?continue=https://google.com/search",
                "",
            )
        )
        self.assertTrue(
            is_google_verification_page(
                "https://www.google.com/search?q=test",
                "Our systems have detected unusual traffic from your computer network.",
            )
        )
        self.assertFalse(
            is_google_verification_page(
                "https://www.google.com/search?q=test",
                "Search result for Example Builders on Facebook.",
            )
        )

    def test_google_fallback_status_file_upserts_profile_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status_file = Path(temp_dir) / "google_fallback_search_status.csv"

            record_google_fallback_status(
                "profile-1",
                "Example Builders",
                "Austin, TX",
                "USA",
                'site:facebook.com "Example Builders" "Austin, TX" fb in USA',
                "no_result",
                status_file=str(status_file),
            )
            record_google_fallback_status(
                "profile-1",
                "Example Builders",
                "Austin, TX",
                "USA",
                'site:facebook.com "Example Builders" "Austin, TX" fb in USA',
                "result_found",
                candidate_count=1,
                first_candidate="https://www.facebook.com/examplebuilders",
                status_file=str(status_file),
            )

            with status_file.open(encoding="utf-8", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "Example Builders")
            self.assertEqual(rows[0]["status"], "result_found")
            self.assertEqual(rows[0]["candidate_count"], "1")
            self.assertEqual(
                rows[0]["first_candidate"],
                "https://www.facebook.com/examplebuilders",
            )


if __name__ == "__main__":
    unittest.main()
