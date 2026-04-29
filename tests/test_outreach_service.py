"""Tests for compliant email outreach planning, risk checks, and ledgers."""

import csv
import os
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from desktop_app.services.outreach_service import (
    CampaignConfig,
    Contact,
    EmailOutreachService,
    SMTPSettings,
    analyze_spam_risk,
    build_email_message,
    load_contacts_from_csv,
    validate_contact_source_path,
)


class FakeTransport:
    """Capture outgoing messages without touching the network."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> str:
        self.messages.append(message)
        return f"fake-{len(self.messages)}"


class OutreachServiceTests(unittest.TestCase):
    """Exercise the outreach safety boundary and sending workflow."""

    def test_load_contacts_from_csv_preserves_fields_and_permission_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contact_file = Path(temp_dir) / "contacts.csv"
            with contact_file.open("w", newline="", encoding="utf-8") as file_obj:
                writer = csv.DictWriter(
                    file_obj,
                    fieldnames=["Email", "Name", "City", "Project Type", "Permission Status"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Email": "OWNER@ExampleBuilder.com ",
                        "Name": "Sam Owner",
                        "City": "Dallas",
                        "Project Type": "kitchen remodel",
                        "Permission Status": "verified",
                    }
                )

            contacts = load_contacts_from_csv(contact_file)

        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].email, "owner@examplebuilder.com")
        self.assertEqual(contacts[0].name, "Sam Owner")
        self.assertEqual(contacts[0].city, "Dallas")
        self.assertEqual(contacts[0].project_type, "kitchen remodel")
        self.assertEqual(contacts[0].permission_status, "verified")

    def test_plan_accounts_for_every_contact_and_blocks_missing_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EmailOutreachService(state_dir=Path(temp_dir))
            config = CampaignConfig(
                campaign_id="spring-remodel",
                subject_a="Planning a remodel in {city}?",
                body="Hi {name}, we help with {project_type} projects in {city}.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
            )
            contacts = [
                Contact(
                    "owner@examplebuilder.com",
                    name="Sam",
                    city="Dallas",
                    permission_status="verified",
                ),
                Contact("unknown@examplebuilder.com", name="Alex", city="Austin"),
                Contact("bad-address", name="Bad", city="Houston", permission_status="verified"),
                Contact(
                    "owner@examplebuilder.com",
                    name="Duplicate",
                    city="Dallas",
                    permission_status="verified",
                ),
            ]

            plan = service.plan_campaign(contacts, config)

        self.assertEqual(len(plan.decisions), 4)
        self.assertEqual(plan.summary["total"], 4)
        self.assertEqual(plan.summary["dry_run"], 1)
        self.assertEqual(plan.summary["missing_permission"], 1)
        self.assertEqual(plan.summary["invalid"], 1)
        self.assertEqual(plan.summary["duplicate_input"], 1)

    def test_suppression_and_sent_ledger_prevent_repeat_sends(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EmailOutreachService(state_dir=Path(temp_dir))
            service.add_suppression("suppressed@examplebuilder.com", "unsubscribed")
            service.record_sent(
                email="sent@examplebuilder.com",
                campaign_id="spring-remodel",
                subject="Planning a remodel?",
                variant="A",
                status="sent",
                reason="delivered_to_smtp",
                message_id="msg-1",
            )
            config = CampaignConfig(
                campaign_id="spring-remodel",
                subject_a="Planning a remodel?",
                body="Hi, we help with remodel planning.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
            )
            contacts = [
                Contact("suppressed@examplebuilder.com", permission_status="verified"),
                Contact("sent@examplebuilder.com", permission_status="verified"),
            ]

            plan = service.plan_campaign(contacts, config)

        statuses = {decision.email: decision.status for decision in plan.decisions}
        self.assertEqual(statuses["suppressed@examplebuilder.com"], "suppressed")
        self.assertEqual(statuses["sent@examplebuilder.com"], "already_sent")

    def test_sent_ledger_blocks_email_across_campaigns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EmailOutreachService(state_dir=Path(temp_dir))
            service.record_sent(
                email="sent@examplebuilder.com",
                campaign_id="older-campaign",
                subject="Older subject",
                variant="A",
                status="sent",
                reason="delivered_to_smtp",
                message_id="msg-1",
            )
            config = CampaignConfig(
                campaign_id="new-campaign",
                subject_a="Planning a remodel?",
                body="Hi, we help with remodel planning.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
            )

            plan = service.plan_campaign(
                [Contact("sent@examplebuilder.com", permission_status="verified")],
                config,
            )

        self.assertEqual(plan.decisions[0].status, "already_sent")
        self.assertEqual(plan.decisions[0].reason, "global_duplicate_prevention")

    def test_contact_source_path_allows_only_master_and_final_email_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            final_dir = root / "final"
            output_dir = root / "output" / "logs"
            final_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)

            root_master = root / "houzz_emails.csv"
            final_export = final_dir / "houzz_high_quality_emails.csv"
            log_file = output_dir / "houzz_scrape_failures.csv"
            status_file = root / "google_fallback_search_status.csv"
            outside_file = root.parent / "outside.csv"

            for path in [root_master, final_export, log_file, status_file, outside_file]:
                path.write_text("Email\nowner@examplebuilder.com\n", encoding="utf-8")

            self.assertIsNone(validate_contact_source_path(root_master, project_root=root))
            self.assertIsNone(validate_contact_source_path(final_export, project_root=root))

            with self.assertRaises(ValueError):
                validate_contact_source_path(log_file, project_root=root)
            with self.assertRaises(ValueError):
                validate_contact_source_path(status_file, project_root=root)
            with self.assertRaises(ValueError):
                validate_contact_source_path(outside_file, project_root=root)

    def test_spam_risk_flags_hype_and_suggests_human_copy(self):
        report = analyze_spam_risk(
            "ACT NOW!!! Guaranteed cheapest construction quote",
            "Click here for a limited time FREE offer!!!",
        )

        self.assertGreaterEqual(report.score, 70)
        self.assertEqual(report.level, "high")
        self.assertTrue(any("calmer" in suggestion.lower() for suggestion in report.suggestions))

    def test_send_campaign_dry_run_does_not_use_transport_or_sent_ledger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EmailOutreachService(state_dir=Path(temp_dir))
            transport = FakeTransport()
            config = CampaignConfig(
                campaign_id="spring-remodel",
                subject_a="Planning a remodel in {city}?",
                body="Hi {name}, we help with {project_type} projects in {city}.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
                dry_run=True,
            )

            plan = service.send_campaign(
                [
                    Contact(
                        "owner@examplebuilder.com",
                        name="Sam",
                        city="Dallas",
                        permission_status="verified",
                    )
                ],
                config,
                transport=transport,
                sleep_fn=lambda _seconds: None,
            )

            sent_rows = service.load_sent_rows()

        self.assertEqual(plan.summary["dry_run"], 1)
        self.assertEqual(transport.messages, [])
        self.assertEqual(sent_rows, [])

    def test_send_campaign_records_sent_message_with_unsubscribe_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EmailOutreachService(state_dir=Path(temp_dir))
            transport = FakeTransport()
            config = CampaignConfig(
                campaign_id="spring-remodel",
                subject_a="Planning a remodel in {city}?",
                body="Hi {name}, we help with {project_type} projects in {city}.",
                company_name="Matloob Construction",
                physical_address="123 Main St, Dallas, TX",
                unsubscribe_url="https://example.com/unsubscribe",
                dry_run=False,
                min_delay_seconds=0,
                max_delay_seconds=0,
            )
            settings = SMTPSettings(
                host="smtp.example.com",
                port=587,
                username="mailer@example.com",
                password="secret",
                from_email="mailer@example.com",
                from_name="Matloob Construction",
            )

            plan = service.send_campaign(
                [
                    Contact(
                        "owner@examplebuilder.com",
                        name="Sam",
                        city="Dallas",
                        permission_status="verified",
                    )
                ],
                config,
                smtp_settings=settings,
                transport=transport,
                sleep_fn=lambda _seconds: None,
            )

            sent_rows = service.load_sent_rows()

        self.assertEqual(plan.summary["sent"], 1)
        self.assertEqual(len(transport.messages), 1)
        self.assertIn("List-Unsubscribe", transport.messages[0])
        self.assertIn("List-Unsubscribe-Post", transport.messages[0])
        self.assertEqual(len(sent_rows), 1)
        self.assertEqual(sent_rows[0]["email"], "owner@examplebuilder.com")

    def test_smtp_settings_load_from_environment_without_hardcoded_secrets(self):
        env = {
            "MATLOOB_SMTP_HOST": "smtp.gmail.com",
            "MATLOOB_SMTP_PORT": "587",
            "MATLOOB_SMTP_USERNAME": "sender@example.com",
            "MATLOOB_SMTP_PASSWORD": "app-password",
            "MATLOOB_FROM_EMAIL": "sender@example.com",
            "MATLOOB_FROM_NAME": "Matloob Construction",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = SMTPSettings.from_env()

        self.assertEqual(settings.host, "smtp.gmail.com")
        self.assertEqual(settings.port, 587)
        self.assertEqual(settings.username, "sender@example.com")
        self.assertEqual(settings.password, "app-password")
        self.assertEqual(settings.from_name, "Matloob Construction")

    def test_build_email_message_appends_required_footer(self):
        settings = SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="mailer@example.com",
            password="secret",
            from_email="mailer@example.com",
            from_name="Matloob Construction",
        )
        config = CampaignConfig(
            campaign_id="spring-remodel",
            subject_a="Planning a remodel?",
            body="Hi {name}, can we help with your project?",
            company_name="Matloob Construction",
            physical_address="123 Main St, Dallas, TX",
            unsubscribe_url="https://example.com/unsubscribe",
        )

        message = build_email_message(
            settings,
            Contact("owner@examplebuilder.com", name="Sam", permission_status="verified"),
            config,
            subject="Planning a remodel?",
            body="Hi Sam, can we help with your project?",
        )

        body = message.get_content()
        self.assertIn("Matloob Construction", body)
        self.assertIn("123 Main St, Dallas, TX", body)
        self.assertIn("Unsubscribe:", body)
        self.assertEqual(message["To"], "owner@examplebuilder.com")


if __name__ == "__main__":
    unittest.main()
