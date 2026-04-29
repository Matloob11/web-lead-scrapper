"""Regression coverage for the user-facing scraper with local-only startup."""

import inspect
import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import desktop_app.services.scraper_service as scraper_service_module
import houzz_pro_scraper
from desktop_app.models import ScraperRunConfig
from desktop_app.services.scraper_service import ScraperDashboardService


class LocalCleanModeTests(unittest.TestCase):
    def test_cli_entry_points_do_not_accept_removed_access_parameters(self):
        run_signature = inspect.signature(houzz_pro_scraper.run_scraper)
        export_signature = inspect.signature(houzz_pro_scraper.export_final_for_source)

        removed_run_params = {
            "access_identity",
            "device_id",
            "access_prechecked",
            "track_activity",
        }
        self.assertTrue(removed_run_params.isdisjoint(run_signature.parameters))
        self.assertNotIn("access_identity", export_signature.parameters)
        self.assertNotIn("device_id", export_signature.parameters)
        self.assertNotIn("access_prechecked", export_signature.parameters)

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

    def test_dashboard_service_starts_without_remote_gate_or_usage_api(self):
        service = ScraperDashboardService()
        fake_thread = MagicMock()

        with patch.object(scraper_service_module.threading, "Thread", return_value=fake_thread):
            started = service.start_run(
                ScraperRunConfig(
                    url="https://www.houzz.com/professionals",
                    source="houzz",
                )
        )

        self.assertTrue(started)
        self.assertFalse(hasattr(scraper_service_module, "_".join(("db", "manager"))))
        fake_thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
