"""Tests for business filters, email filters, and email quality scoring."""

import unittest

from scraper.filters.business_filters import is_target_business_text, is_target_profile_url
from scraper.filters.email_filters import is_valid_email_candidate
from scraper.filters.email_quality import score_email_quality


class FilterTests(unittest.TestCase):
    """Cover the main filtering behavior used by scraping workflows."""

    def test_business_filter_allows_target_categories(self):
        self.assertTrue(is_target_business_text("general contractor renovation"))
        self.assertTrue(is_target_business_text("real estate broker property"))
        self.assertTrue(
            is_target_profile_url("https://www.bbb.org/us/ca/x/profile/electrical-contractors/foo")
        )

    def test_business_filter_rejects_unrelated_categories(self):
        self.assertFalse(is_target_business_text("restaurant cafe"))
        self.assertFalse(is_target_business_text("dentist contractor"))

    def test_email_filter_rejects_vendor_and_government_domains(self):
        self.assertFalse(is_valid_email_candidate("info@thinkservice-email.com"))
        self.assertFalse(is_valid_email_candidate("licensing@cslb.ca.gov"))
        self.assertFalse(is_valid_email_candidate("name@example.com"))
        self.assertTrue(is_valid_email_candidate("info@realbuilder.com"))

    def test_email_quality_scores_business_and_free_emails(self):
        self.assertEqual(
            score_email_quality(
                "info@adeedo.com",
                "Adeedo!",
                "https://www.adeedo.com/",
                {"website"},
            ),
            ("high", "business_domain_generic_inbox"),
        )
        self.assertEqual(
            score_email_quality(
                "topfamilyconstruction@gmail.com",
                "Top Family Construction and Remodeling Inc",
                "https://www.topfamilyconstruction.com/",
                {"website"},
            ),
            ("medium", "free_email_matches_business_name"),
        )
        self.assertEqual(
            score_email_quality(
                "info@gmail.com",
                "Random Business",
                "https://randombusiness.com",
                {"website"},
            ),
            ("low", "generic_free_email"),
        )


if __name__ == "__main__":
    unittest.main()
