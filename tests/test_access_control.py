"""Tests for Supabase-backed application access checks."""

import unittest
from types import SimpleNamespace

from scraper.access_control import (
    AccessControlClient,
    AccessControlConfig,
    format_access_decision,
)


class FakeRpcCall:
    """Small fake for the Supabase RPC execute chain."""

    def __init__(self, data=None, exc=None):
        self.data = data
        self.exc = exc

    def execute(self):
        if self.exc:
            raise self.exc

        return SimpleNamespace(data=self.data)


class FakeSupabaseClient:
    """Capture RPC calls without touching the network."""

    def __init__(self, data=None, exc=None):
        self.data = data
        self.exc = exc
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeRpcCall(self.data, self.exc)


class AccessControlTests(unittest.TestCase):
    """Exercise allowed, denied, and technical-error access decisions."""

    def make_client(self, fake_client):
        return AccessControlClient(
            AccessControlConfig(
                supabase_url="https://example.supabase.co",
                supabase_key="publishable-key",
                app_name="matloob-lead-scraper",
            ),
            supabase_client=fake_client,
            device_id_provider=lambda: "device-123",
            identity_provider=lambda: {
                "os_user": "matloob",
                "machine_name": "office-pc",
                "platform": "Windows",
            },
        )

    def test_approved_status_allows_app_start(self):
        fake_client = FakeSupabaseClient(
            [{"status": "approved", "message": "Access approved.", "request_id": "req-1"}]
        )
        client = self.make_client(fake_client)

        decision = client.check_access()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.status, "approved")
        self.assertEqual(decision.request_id, "req-1")
        self.assertEqual(fake_client.calls[0][0], "request_app_access")
        self.assertEqual(fake_client.calls[0][1]["p_device_id"], "device-123")
        self.assertEqual(fake_client.calls[0][1]["p_os_user"], "matloob")

    def test_pending_status_blocks_app_with_request_message(self):
        fake_client = FakeSupabaseClient(
            [{"status": "pending", "message": "Waiting for admin approval.", "request_id": "req-2"}]
        )
        client = self.make_client(fake_client)

        decision = client.check_access()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.status, "pending")
        self.assertIn("Waiting for admin approval", format_access_decision(decision))

    def test_supabase_exception_fails_closed_as_technical_error(self):
        fake_client = FakeSupabaseClient(exc=TimeoutError("request timed out"))
        client = self.make_client(fake_client)

        decision = client.check_access()

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.technical_error)
        self.assertEqual(decision.status, "technical_error")
        self.assertIn("Technical error", format_access_decision(decision))

    def test_missing_supabase_config_fails_closed(self):
        client = AccessControlClient(
            AccessControlConfig(supabase_url="", supabase_key="", app_name="matloob-lead-scraper")
        )

        decision = client.check_access()

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.technical_error)
        self.assertEqual(decision.status, "technical_error")


if __name__ == "__main__":
    unittest.main()
