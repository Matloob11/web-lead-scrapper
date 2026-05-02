"""Regression coverage for the user-facing scraper with local-only startup."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import desktop_app.services.scraper_service as scraper_service_module
import houzz_pro_scraper
from desktop_app.models import ScraperRunConfig
from desktop_app.services.scraper_service import ScraperDashboardService


class LocalCleanModeTests(unittest.TestCase):
    def test_cli_parser_no_longer_exposes_device_id_option(self):
        help_output = io.StringIO()

        with (
            patch.object(sys, "argv", ["houzz_pro_scraper.py", "--help"]),
            redirect_stdout(help_output),
            self.assertRaises(SystemExit) as exc_context,
        ):
            houzz_pro_scraper.parse_args()

        self.assertEqual(exc_context.exception.code, 0)
        self.assertNotIn("--device" + "-id", help_output.getvalue())

    def test_cli_main_checks_access_before_export(self):
        args = SimpleNamespace(
            source="houzz",
            export_final_only=True,
            quality_filter=("high",),
            url="",
            max_pages=None,
            max_profiles=None,
            headless=False,
            skip_facebook=False,
            country="",
            skip_google_fallback=False,
            no_final_export=False,
            retry_no_email=False,
            out_filename=None,
        )

        with (
            patch.object(houzz_pro_scraper, "parse_args", return_value=args),
            patch.object(houzz_pro_scraper, "require_app_access") as require_access,
            patch.object(houzz_pro_scraper, "export_final_for_source", side_effect=SystemExit(0)),
            self.assertRaises(SystemExit),
        ):
            houzz_pro_scraper.main()

        require_access.assert_called_once()

    def test_dashboard_service_checks_remote_gate_before_start(self):
        service = ScraperDashboardService()
        fake_thread = MagicMock()

        with (
            patch.object(scraper_service_module, "require_app_access") as require_access,
            patch.object(scraper_service_module.threading, "Thread", return_value=fake_thread),
        ):
            started = service.start_run(
                ScraperRunConfig(
                    url="https://www.houzz.com/professionals",
                    source="houzz",
                )
            )

        self.assertTrue(started)
        require_access.assert_called_once()
        fake_thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
