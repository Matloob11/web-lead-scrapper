"""Tests for automatic device identity generation."""

import os
import unittest
from unittest.mock import patch

from scraper.identity import DEVICE_ID_ENV_VAR, get_device_id


class IdentityTests(unittest.TestCase):
    """Validate the user-free access identity used for admin approval."""

    def test_device_id_uses_environment_override(self):
        with patch.dict(os.environ, {DEVICE_ID_ENV_VAR: " device-test-123 "}, clear=False):
            self.assertEqual(get_device_id(), "DEVICE-TEST-123")

    def test_device_id_is_stable_prefixed_and_uppercase(self):
        first = get_device_id(
            seed_parts=("desktop-one", "windows", "x64", "machine-guid"),
        )
        second = get_device_id(
            seed_parts=("desktop-one", "windows", "x64", "machine-guid"),
        )

        self.assertEqual(first, second)
        self.assertRegex(first, r"^DEVICE-[A-F0-9]{16}$")


if __name__ == "__main__":
    unittest.main()
