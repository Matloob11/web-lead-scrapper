"""Tests for shared URL utility helpers."""

import base64
import unittest
from urllib.parse import quote

from scraper.utils import decode_houzz_trk_link


class UtilsTests(unittest.TestCase):
    """Validate utility edge cases used by scraper sources."""

    def test_decode_houzz_trk_link_handles_urlsafe_escaped_base64(self):
        target_url = "https://examplebuilder.com/contact?from=houzz"
        encoded = base64.urlsafe_b64encode(target_url.encode("utf-8")).decode("ascii")
        encoded = quote(encoded.rstrip("="), safe="")

        self.assertEqual(
            decode_houzz_trk_link(f"https://www.houzz.com/trk/{encoded}/track"),
            target_url,
        )


if __name__ == "__main__":
    unittest.main()
