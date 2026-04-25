"""Tests for external website scraping helpers."""

import asyncio
import unittest

from scraper.sources.website_scraper import get_site_emails


class WebsiteHelperTests(unittest.TestCase):
    """Validate website scraper guards that do not require a browser."""

    def test_get_site_emails_skips_non_http_urls(self):
        emails, had_error = asyncio.run(get_site_emails(None, "javascript:void(0)"))

        self.assertEqual(emails, set())
        self.assertFalse(had_error)


if __name__ == "__main__":
    unittest.main()
