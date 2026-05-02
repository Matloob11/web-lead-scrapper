"""Tests for desktop dashboard services and runtime tracking."""

import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from desktop_app.models import OutreachRunConfig, ScraperRunConfig
from desktop_app.services.file_service import build_source_summary, reset_source_outputs
from desktop_app.services.scraper_service import (
    ScraperDashboardService,
    build_campaign_config,
    build_effective_run_options,
)
from desktop_app.view_models import safe_int, summary_file_paths
from scraper.browser_launcher import build_launch_options
from scraper.control import responsive_sleep
from scraper.runtime import ScraperRuntimeController


class DesktopServiceTests(unittest.TestCase):
    """Exercise summary building and runtime controller updates."""

    def test_browser_headless_option_is_passed_to_launch_options(self):
        options = build_launch_options(
            True,
            "Mozilla/5.0 Test",
            executable_path=r"C:\Browser\chrome.exe",
        )

        self.assertTrue(options["headless"])
        self.assertEqual(options["user_agent"], "Mozilla/5.0 Test")
        self.assertEqual(options["executable_path"], r"C:\Browser\chrome.exe")

    def test_build_source_summary_counts_files_statuses_and_quality_mix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "houzz_emails.csv"
            detail_file = root / "houzz_results_detailed.csv"
            status_file = root / "houzz_scrape_status.csv"
            fail_log_file = root / "houzz_failures.csv"
            final_file = root / "houzz_final.csv"
            final_detail_file = root / "houzz_final_detail.csv"

            master_file.write_text("Email\none@example.com\ntwo@example.com\n", encoding="utf-8")
            final_file.write_text("Email\none@example.com\n", encoding="utf-8")
            fail_log_file.write_text(
                "timestamp,step,profile_url,target_url,error\n",
                encoding="utf-8",
            )
            final_detail_file.write_text(
                "Email,Quality,Reason,Name,Website,Profile\n",
                encoding="utf-8",
            )

            with detail_file.open("w", newline="", encoding="utf-8") as file_obj:
                writer = csv.DictWriter(
                    file_obj,
                    fieldnames=[
                        "email",
                        "name",
                        "houzz_profile",
                        "website",
                        "facebook",
                        "sources",
                        "email_quality",
                        "email_quality_reason",
                        "saved_to_master_output",
                    ],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "email": "one@example.com",
                            "name": "Example One",
                            "houzz_profile": "profile-1",
                            "website": "https://example.com",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "high",
                            "email_quality_reason": "reason-1",
                            "saved_to_master_output": "1",
                        },
                        {
                            "email": "two@gmail.com",
                            "name": "Example Two",
                            "houzz_profile": "profile-2",
                            "website": "https://example.org",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "medium",
                            "email_quality_reason": "reason-2",
                            "saved_to_master_output": "1",
                        },
                        {
                            "email": "three@yahoo.com",
                            "name": "Example Three",
                            "houzz_profile": "profile-3",
                            "website": "https://example.net",
                            "facebook": "",
                            "sources": "website",
                            "email_quality": "low",
                            "email_quality_reason": "reason-3",
                            "saved_to_master_output": "0",
                        },
                    ]
                )

            with status_file.open("w", newline="", encoding="utf-8") as file_obj:
                writer = csv.writer(file_obj)
                writer.writerow(["profile_url", "status", "detail", "updated_at"])
                writer.writerow(["profile-1", "processed", "", "2026-04-24T09:00:00"])
                writer.writerow(["profile-2", "failed", "", "2026-04-24T09:01:00"])
                writer.writerow(["profile-3", "no_email", "", "2026-04-24T09:02:00"])
                writer.writerow(["profile-2", "processed", "", "2026-04-24T09:03:00"])

            fake_paths = {
                "source": "houzz",
                "output_file": str(master_file),
                "detail_output_file": str(detail_file),
                "status_file": str(status_file),
                "fail_log_file": str(fail_log_file),
                "final_output_file": str(final_file),
                "final_detail_file": str(final_detail_file),
            }

            with patch(
                "desktop_app.services.file_service.get_source_paths",
                return_value=fake_paths,
            ):
                summary = build_source_summary("houzz")

            self.assertEqual(summary.master_count, 2)
            self.assertEqual(summary.detail_count, 3)
            self.assertEqual(summary.final_count, 1)
            self.assertEqual(summary.tracked_profiles, 3)
            self.assertEqual(summary.processed_count, 2)
            self.assertEqual(summary.failed_count, 0)
            self.assertEqual(summary.no_email_count, 1)
            self.assertEqual(summary.high_quality_count, 1)
            self.assertEqual(summary.medium_quality_count, 1)
            self.assertEqual(summary.low_quality_count, 1)
            self.assertEqual(summary.last_updated, "2026-04-24T09:03:00")

    def test_reset_source_outputs_uses_custom_output_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            custom_file = root / "custom.csv"
            status_file = root / "status.csv"
            custom_file.write_text("Email\nold@example.com\n", encoding="utf-8")
            status_file.write_text("profile_url,status,detail,updated_at\n", encoding="utf-8")
            fake_paths = {
                "source": "houzz",
                "output_file": str(custom_file),
                "status_file": str(status_file),
            }

            with (
                patch("desktop_app.services.file_service.PROJECT_ROOT", root),
                patch(
                    "desktop_app.services.file_service.get_source_paths",
                    return_value=fake_paths,
                ) as get_source_paths,
            ):
                removed = reset_source_outputs("houzz", out_filename="custom.csv")

            get_source_paths.assert_called_once_with("houzz", out_filename="custom.csv")
            self.assertEqual({Path(path).name for path in removed}, {"custom.csv", "status.csv"})
            self.assertFalse(custom_file.exists())
            self.assertFalse(status_file.exists())

    def test_summary_file_paths_accepts_summary_file_dict(self):
        files = summary_file_paths(
            {
                "files": {
                    "source": "houzz",
                    "output_file": r"C:\project\houzz_emails.csv",
                    "status_file": "",
                }
            }
        )

        self.assertEqual(files, [r"C:\project\houzz_emails.csv"])

    def test_safe_int_ignores_invalid_optional_limits(self):
        self.assertEqual(safe_int(" 5 "), 5)
        self.assertIsNone(safe_int(""))
        self.assertIsNone(safe_int("abc"))
        self.assertIsNone(safe_int("-2"))

    def test_dashboard_toggles_apply_effective_run_options(self):
        options = build_effective_run_options(ScraperRunConfig(email_only=True, fast_mode=True))

        self.assertTrue(options["skip_facebook"])
        self.assertTrue(options["skip_google_fallback"])
        self.assertEqual(options["quality_filter"], ("high",))

    def test_build_campaign_config_maps_dashboard_outreach_settings(self):
        campaign = build_campaign_config(
            OutreachRunConfig(
                contact_file="final/houzz_high_quality_emails.csv",
                campaign_id="spring-remodel",
                subject_a="Planning a remodel in {city}?",
                subject_b="Need a construction estimate in {city}?",
                body="Hi {name}, we help with {project_type}.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
                dry_run=False,
                confirm_permission=True,
                session_limit=12,
                min_delay_seconds=5,
                max_delay_seconds=20,
            )
        )

        self.assertEqual(campaign.campaign_id, "spring-remodel")
        self.assertEqual(campaign.subject_b, "Need a construction estimate in {city}?")
        self.assertFalse(campaign.dry_run)
        self.assertTrue(campaign.allow_manual_permission_override)
        self.assertEqual(campaign.session_limit, 12)
        self.assertEqual(campaign.min_delay_seconds, 5)
        self.assertEqual(campaign.max_delay_seconds, 20)

    def test_analyze_outreach_rejects_non_contact_csv_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "output" / "logs"
            log_dir.mkdir(parents=True)
            log_file = log_dir / "houzz_scrape_failures.csv"
            log_file.write_text("Email\nowner@examplebuilder.com\n", encoding="utf-8")

            service = ScraperDashboardService()
            config = OutreachRunConfig(
                contact_file=str(log_file),
                campaign_id="spring-remodel",
                subject_a="Planning a remodel?",
                body="Hi {name}, we help with projects.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
                dry_run=True,
                confirm_permission=True,
            )

            with (
                patch(
                    "desktop_app.services.scraper_service.PROJECT_ROOT",
                    root,
                ),
                self.assertRaises(ValueError),
            ):
                service.analyze_outreach(config)

    def test_start_outreach_rejects_non_contact_csv_before_thread_start(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "output" / "logs"
            log_dir.mkdir(parents=True)
            log_file = log_dir / "houzz_scrape_failures.csv"
            log_file.write_text("Email\nowner@examplebuilder.com\n", encoding="utf-8")

            service = ScraperDashboardService()
            config = OutreachRunConfig(
                contact_file=str(log_file),
                campaign_id="spring-remodel",
                subject_a="Planning a remodel?",
                body="Hi {name}, we help with projects.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
                dry_run=True,
                confirm_permission=True,
            )

            with patch("desktop_app.services.scraper_service.PROJECT_ROOT", root):
                started = service.start_outreach(config)

            self.assertFalse(started)
            state = service.get_state()
            self.assertFalse(state["busy"])
            events = service.drain_events()

        self.assertTrue(any(event["type"] == "outreach" for event in events))

    def test_dashboard_service_checks_access_before_scrape_start(self):
        service = ScraperDashboardService()
        fake_thread = MagicMock()

        with (
            patch("desktop_app.services.scraper_service.require_app_access") as require_access,
            patch(
                "desktop_app.services.scraper_service.threading.Thread",
                return_value=fake_thread,
            ),
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

    def test_dashboard_service_blocks_scrape_when_access_denied(self):
        service = ScraperDashboardService()

        with (
            patch(
                "desktop_app.services.scraper_service.require_app_access",
                side_effect=SystemExit(1),
            ),
            patch("desktop_app.services.scraper_service.threading.Thread") as thread_class,
        ):
            started = service.start_run(
                ScraperRunConfig(
                    url="https://www.houzz.com/professionals",
                    source="houzz",
                )
            )

        self.assertFalse(started)
        thread_class.assert_not_called()
        self.assertFalse(service.get_state()["busy"])

    def test_runtime_controller_tracks_progress_and_completion(self):
        runtime = ScraperRuntimeController()
        runtime.start_run("houzz", "https://example.com", max_profiles=10)
        runtime.register_page(1, discovered_count=6)
        runtime.record_skipped_profile("profile-skip")
        runtime.record_attempted_profile("profile-1")
        runtime.record_profile_result(
            "profile-1",
            {"status": "processed", "master_saved": 2, "detail_saved": 2},
        )
        runtime.record_export(
            {
                "count": 2,
                "final_output_file": "final.csv",
                "final_detail_file": "detail.csv",
            }
        )
        runtime.complete_run()

        snapshot = runtime.snapshot()
        self.assertEqual(snapshot.run_state, "completed")
        self.assertEqual(snapshot.current_page, 1)
        self.assertEqual(snapshot.profiles_discovered, 6)
        self.assertEqual(snapshot.profiles_skipped, 1)
        self.assertEqual(snapshot.profiles_attempted, 1)
        self.assertEqual(snapshot.processed, 1)
        self.assertEqual(snapshot.master_saved, 2)
        self.assertEqual(snapshot.detail_saved, 2)
        self.assertEqual(snapshot.final_export_count, 2)
        self.assertAlmostEqual(snapshot.progress_ratio, 0.2)

    def test_responsive_sleep_returns_when_stop_is_requested(self):
        async def scenario():
            runtime = ScraperRuntimeController()
            runtime.start_run("houzz", "https://example.com")
            runtime.request_stop()
            return await responsive_sleep(5, runtime=runtime, interval=0.01)

        self.assertTrue(asyncio.run(scenario()))


if __name__ == "__main__":
    unittest.main()
