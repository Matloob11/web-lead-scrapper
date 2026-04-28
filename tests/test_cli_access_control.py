"""Regression tests for CLI/admin access control wiring."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import houzz_pro_scraper
from scraper.identity import DEVICE_ID_ENV_VAR
from scraper.storage.mongodb_storage import ACCESS_PENDING, MongoDBManager


class _FakePlaywrightContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False


class _FakeBrowserContext:
    def __init__(self):
        self.closed = False
        self.default_timeout = None

    def set_default_timeout(self, timeout_ms):
        self.default_timeout = timeout_ms

    async def close(self):
        self.closed = True


class _FakeUsersCollection:
    def __init__(self, user):
        self.user = user
        self.updates = []

    def find_one(self, _identity):
        return self.user

    def update_one(self, identity, update, upsert=False):
        self.updates.append((identity, update, upsert))


class _FakeDatabase:
    def __init__(self, user):
        self.users = _FakeUsersCollection(user)


class CliAccessControlTests(unittest.TestCase):
    """Direct scraper entry points must follow the same admin rules as the GUI."""

    def test_run_scraper_denies_unapproved_device_before_browser_launch(self):
        with (
            patch.dict(os.environ, {DEVICE_ID_ENV_VAR: "device-test"}, clear=False),
            patch.object(
                houzz_pro_scraper.db_manager,
                "request_access",
                return_value={
                    "allowed": False,
                    "status": "pending",
                    "message": "Access pending. Admin approval is required.",
                },
            ) as request_access,
            patch.object(houzz_pro_scraper, "async_playwright") as async_playwright,
            self.assertRaisesRegex(PermissionError, "Access pending"),
        ):
            asyncio.run(
                houzz_pro_scraper.run_scraper(
                    "https://www.houzz.com/professionals",
                    source="houzz",
                )
            )

        request_access.assert_called_once_with(
            "DEVICE-TEST",
            "houzz",
            "https://www.houzz.com/professionals",
        )
        async_playwright.assert_not_called()

    def test_run_scraper_tracks_approved_cli_activity(self):
        fake_context = _FakeBrowserContext()

        async def fake_houzz_run(*args, **_kwargs):
            stats = args[9]
            stats["processed"] = 1
            stats["master_saved"] = 3
            stats["detail_saved"] = 3

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_file = root / "emails.csv"
            detail_file = root / "details.csv"

            with (
                patch.dict(os.environ, {DEVICE_ID_ENV_VAR: "device-test"}, clear=False),
                patch.object(
                    houzz_pro_scraper.db_manager,
                    "request_access",
                    return_value={
                        "allowed": True,
                        "status": "approved",
                        "message": "Access approved.",
                    },
                ) as request_access,
                patch.object(
                    houzz_pro_scraper.db_manager,
                    "track_start",
                    return_value="activity-id",
                ) as track_start,
                patch.object(
                    houzz_pro_scraper.db_manager,
                    "update_activity",
                ) as update_activity,
                patch.object(
                    houzz_pro_scraper,
                    "async_playwright",
                    return_value=_FakePlaywrightContext(),
                ),
                patch.object(
                    houzz_pro_scraper,
                    "launch_persistent_browser",
                    new=AsyncMock(return_value=fake_context),
                ),
                patch.object(houzz_pro_scraper, "ensure_output_files"),
                patch.object(houzz_pro_scraper, "load_statuses", return_value={}),
                patch.object(houzz_pro_scraper, "load_master_emails", return_value=set()),
                patch.object(houzz_pro_scraper, "load_existing_detail_keys", return_value=set()),
                patch.object(
                    houzz_pro_scraper,
                    "get_active_output_file",
                    return_value=str(master_file),
                ),
                patch.object(
                    houzz_pro_scraper,
                    "get_active_detail_output_file",
                    return_value=str(detail_file),
                ),
                patch.object(houzz_pro_scraper, "write_statuses"),
                patch.object(houzz_pro_scraper, "run_houzz_search", side_effect=fake_houzz_run),
            ):
                asyncio.run(
                    houzz_pro_scraper.run_scraper(
                        "https://www.houzz.com/professionals",
                        source="houzz",
                        auto_export_final=False,
                    )
                )

        request_access.assert_called_once_with(
            "DEVICE-TEST",
            "houzz",
            "https://www.houzz.com/professionals",
        )
        track_start.assert_called_once_with(
            "houzz",
            "https://www.houzz.com/professionals",
            license_key="DEVICE-TEST",
        )
        update_activity.assert_called_with("activity-id", 3, status="completed")
        self.assertTrue(fake_context.closed)

    def test_export_final_denies_unapproved_license(self):
        with (
            patch.dict(os.environ, {DEVICE_ID_ENV_VAR: "device-test"}, clear=False),
            patch.object(
                houzz_pro_scraper.db_manager,
                "request_access",
                return_value={
                    "allowed": False,
                    "status": "blocked",
                    "message": "Access blocked by admin.",
                },
            ) as request_access,
            patch.object(houzz_pro_scraper, "export_final_emails") as export_final_emails,
            self.assertRaisesRegex(PermissionError, "Access blocked"),
        ):
            houzz_pro_scraper.export_final_for_source(
                "houzz",
            )

        request_access.assert_called_once_with("DEVICE-TEST", "houzz", "export_final_only")
        export_final_emails.assert_not_called()

    def test_existing_user_without_explicit_status_stays_pending(self):
        manager = MongoDBManager()
        manager.computer_name = "DESKTOP-TEST"
        manager.db = _FakeDatabase(
            {
                "computer_name": "DESKTOP-TEST",
                "license_key": "ABC-123",
            }
        )

        with patch.object(manager, "_connect_or_status", return_value=True):
            access = manager.request_access("abc-123", "houzz", "https://example.com/search")

        self.assertFalse(access["allowed"])
        self.assertEqual(access["status"], ACCESS_PENDING)
        update = manager.db.users.updates[0][1]["$set"]
        self.assertEqual(update["access_status"], ACCESS_PENDING)

    def test_mongodb_connect_requires_env_uri(self):
        manager = MongoDBManager()

        with (
            patch.dict(os.environ, {"MATLOOB_MONGO_URI": ""}, clear=False),
            patch("scraper.storage.mongodb_storage.MongoClient") as mongo_client,
        ):
            connected = manager.connect()

        self.assertFalse(connected)
        mongo_client.assert_not_called()

    def test_mongodb_connect_uses_env_uri(self):
        manager = MongoDBManager()
        fake_client = MagicMock()

        with (
            patch.dict(
                os.environ,
                {"MATLOOB_MONGO_URI": "mongodb://localhost:27017/test"},
                clear=False,
            ),
            patch(
                "scraper.storage.mongodb_storage.MongoClient",
                return_value=fake_client,
            ) as mongo_client,
        ):
            connected = manager.connect()

        self.assertTrue(connected)
        mongo_client.assert_called_once_with(
            "mongodb://localhost:27017/test",
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        fake_client.admin.command.assert_called_once_with("ismaster")


if __name__ == "__main__":
    unittest.main()
