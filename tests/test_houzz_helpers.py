"""Tests for Houzz profile helper utilities."""

import unittest

from scraper.sources.houzz_profile import extract_profile_links


class HouzzHelperTests(unittest.TestCase):
    """Validate Houzz link extraction edge cases."""

    def test_extract_profile_links_rejects_non_navigation_website_links(self):
        website_url, facebook_url, mailto_emails = extract_profile_links(
            [
                {"href": "javascript:void(0)", "text": "Visit Website", "aria": ""},
                {"href": "tel:5551234567", "text": "Website", "aria": ""},
                {"href": "https://examplebuilder.com", "text": "Visit Website", "aria": ""},
            ]
        )

        self.assertEqual(website_url, "https://examplebuilder.com")
        self.assertEqual(facebook_url, "")
        self.assertEqual(mailto_emails, set())


if __name__ == "__main__":
    unittest.main()
