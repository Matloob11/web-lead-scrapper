"""Tests for BBB helper utilities."""

import unittest

from scraper.sources.bbb_profile import (
    canonical_bbb_profile_url,
    extract_bbb_profile_links,
    pick_bbb_website,
)


class BbbHelperTests(unittest.TestCase):
    """Validate BBB URL normalization and website selection."""

    def test_canonical_bbb_profile_removes_address_id(self):
        self.assertEqual(
            canonical_bbb_profile_url(
                "https://www.bbb.org/us/ca/los-angeles/profile/"
                "air-conditioning-contractor/adeedo-1216-100067260/"
                "addressId/172103"
            ),
            (
                "https://www.bbb.org/us/ca/los-angeles/profile/"
                "air-conditioning-contractor/adeedo-1216-100067260"
            ),
        )

    def test_extract_bbb_profile_links_dedupes_canonical_variants(self):
        links = [
            {
                "href": (
                    "https://www.bbb.org/us/ca/los-angeles/profile/"
                    "air-conditioning-contractor/adeedo-1216-100067260/"
                    "addressId/172103"
                ),
                "text": "Air Conditioning Contractor",
                "aria": "",
            },
            {
                "href": (
                    "https://www.bbb.org/us/ca/los-angeles/profile/"
                    "air-conditioning-contractor/adeedo-1216-100067260"
                ),
                "text": "Air Conditioning Contractor",
                "aria": "",
            },
        ]
        self.assertEqual(
            extract_bbb_profile_links(links),
            [
                (
                    "https://www.bbb.org/us/ca/los-angeles/profile/"
                    "air-conditioning-contractor/adeedo-1216-100067260"
                )
            ],
        )

    def test_pick_bbb_website_rejects_government_and_social_links(self):
        links = [
            {"href": "https://www.cslb.ca.gov/", "text": "Website", "aria": ""},
            {"href": "https://www.facebook.com/example", "text": "Facebook", "aria": ""},
            {"href": "https://examplebuilder.com", "text": "Visit Website", "aria": ""},
        ]
        self.assertEqual(pick_bbb_website(links), "https://examplebuilder.com")


if __name__ == "__main__":
    unittest.main()
