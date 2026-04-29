"""Compliant email outreach planning, risk checks, and SMTP sending.

This module deliberately optimizes for consent, auditability, and deliverability.
It does not provide spam-bypass behavior: every recipient is accounted for, and
unsafe recipients are blocked with a clear reason.
"""

from __future__ import annotations

import csv
import os
import random
import smtplib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from string import Formatter
from typing import Any, Protocol
from urllib.parse import quote_plus

from scraper.config import PROJECT_ROOT, RUNTIME_DIR
from scraper.filters.email_filters import is_valid_email_candidate

PERMISSION_STATUSES = {
    "confirmed",
    "confirmed_opt_in",
    "manual_confirmed",
    "opt_in",
    "opt-in",
    "permission",
    "permission_based",
    "subscribed",
    "verified",
    "yes",
}
SUPPRESSION_HEADERS = ["email", "reason", "created_at"]
SENT_LEDGER_HEADERS = [
    "email",
    "campaign_id",
    "subject",
    "variant",
    "status",
    "reason",
    "message_id",
    "sent_at",
]
TRACKING_HEADERS = ["email", "campaign_id", "event_type", "created_at"]
CONTACT_FIELD_ALIASES = {
    "email": ("email", "e-mail", "mail", "Email"),
    "name": ("name", "full_name", "contact_name", "Name"),
    "city": ("city", "location", "City"),
    "project_type": ("project_type", "project type", "service", "trade", "Project Type"),
    "company": ("company", "business", "business_name", "Company"),
    "permission_status": (
        "permission_status",
        "permission status",
        "consent",
        "consent_status",
        "Permission Status",
    ),
}
SPAM_TRIGGERS = {
    "act now": 18,
    "best price": 12,
    "buy now": 15,
    "cash": 8,
    "cheapest": 16,
    "click here": 12,
    "deal": 8,
    "free": 14,
    "guarantee": 12,
    "guaranteed": 16,
    "limited time": 16,
    "no obligation": 8,
    "offer": 10,
    "risk-free": 12,
    "save money": 10,
    "urgent": 14,
    "winner": 20,
}
MAX_RISK_SCORE = 100
HIGH_RISK_THRESHOLD = 70
ALLOWED_CONTACT_DIRS = {"", "final"}


class EmailTransport(Protocol):
    """Transport boundary used by the sender and tests."""

    def send(self, message: EmailMessage) -> str:
        """Send one email and return the provider message id when available."""


@dataclass(frozen=True)
class Contact:
    """One outreach recipient plus personalization fields."""

    email: str
    name: str = ""
    city: str = ""
    project_type: str = ""
    company: str = ""
    permission_status: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        object.__setattr__(self, "permission_status", self.permission_status.strip().lower())

    @property
    def has_permission(self) -> bool:
        """Return whether this contact is allowed for marketing outreach."""
        return self.permission_status in PERMISSION_STATUSES


@dataclass(frozen=True)
class CampaignConfig:
    """Settings for one outbound campaign."""

    campaign_id: str
    subject_a: str
    body: str
    subject_b: str = ""
    company_name: str = ""
    physical_address: str = ""
    unsubscribe_url: str = ""
    sender_name: str = ""
    dry_run: bool = True
    require_permission: bool = True
    allow_manual_permission_override: bool = False
    session_limit: int = 25
    daily_limit: int = 50
    min_delay_seconds: float = 60.0
    max_delay_seconds: float = 180.0
    block_high_risk: bool = True


@dataclass(frozen=True)
class SMTPSettings:
    """SMTP credentials loaded from environment variables."""

    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str = ""
    reply_to: str = ""
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> SMTPSettings:
        """Build settings from MATLOOB_* environment variables."""
        host = os.environ.get("MATLOOB_SMTP_HOST", "").strip()
        username = os.environ.get("MATLOOB_SMTP_USERNAME", "").strip()
        password = os.environ.get("MATLOOB_SMTP_PASSWORD", "").strip()
        from_email = os.environ.get("MATLOOB_FROM_EMAIL", username).strip()
        missing = [
            name
            for name, value in {
                "MATLOOB_SMTP_HOST": host,
                "MATLOOB_SMTP_USERNAME": username,
                "MATLOOB_SMTP_PASSWORD": password,
                "MATLOOB_FROM_EMAIL": from_email,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing SMTP environment variables: {', '.join(missing)}")

        try:
            port = int(os.environ.get("MATLOOB_SMTP_PORT", "587").strip() or "587")
        except ValueError as exc:
            raise ValueError("MATLOOB_SMTP_PORT must be a number.") from exc

        use_tls_value = os.environ.get("MATLOOB_SMTP_USE_TLS", "1").strip().lower()
        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            from_email=from_email,
            from_name=os.environ.get("MATLOOB_FROM_NAME", "").strip(),
            reply_to=os.environ.get("MATLOOB_REPLY_TO", "").strip(),
            use_tls=use_tls_value not in {"0", "false", "no"},
        )


@dataclass(frozen=True)
class SpamRiskReport:
    """Risk score and copy suggestions for a message."""

    score: int
    level: str
    warnings: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecipientDecision:
    """Decision for one contact in a campaign plan."""

    email: str
    status: str
    reason: str
    variant: str = ""
    subject: str = ""
    body: str = ""
    risk_score: int = 0
    risk_level: str = "low"
    warnings: tuple[str, ...] = ()
    message_id: str = ""

    @property
    def eligible(self) -> bool:
        """Return True when this decision can be sent."""
        return self.status in {"queued", "dry_run"}


@dataclass(frozen=True)
class CampaignPlan:
    """Campaign decisions with aggregate status counts."""

    decisions: list[RecipientDecision]
    summary: dict[str, int] = field(default_factory=dict)
    compliance_issues: tuple[str, ...] = ()


class SmtpEmailTransport:
    """Small SMTP transport wrapper."""

    def __init__(self, settings: SMTPSettings) -> None:
        self.settings = settings

    def send(self, message: EmailMessage) -> str:
        """Send one email through SMTP."""
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=60) as smtp:
            if self.settings.use_tls:
                smtp.starttls()
            smtp.login(self.settings.username, self.settings.password)
            smtp.send_message(message)
        return str(message.get("Message-ID") or "")


class EmailOutreachService:
    """Own outreach state files and campaign execution."""

    def __init__(self, state_dir: Path | str | None = None) -> None:
        self.state_dir = Path(state_dir or RUNTIME_DIR / "outreach")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.suppression_file = self.state_dir / "suppression_list.csv"
        self.sent_ledger_file = self.state_dir / "sent_ledger.csv"
        self.tracking_file = self.state_dir / "tracking_events.csv"
        self._ensure_csv(self.suppression_file, SUPPRESSION_HEADERS)
        self._ensure_csv(self.sent_ledger_file, SENT_LEDGER_HEADERS)
        self._ensure_csv(self.tracking_file, TRACKING_HEADERS)

    def _ensure_csv(self, path: Path, headers: list[str]) -> None:
        if path.exists() and path.stat().st_size > 0:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as file_obj:
            csv.writer(file_obj).writerow(headers)

    def add_suppression(self, email: str, reason: str = "manual") -> None:
        """Add an email to the suppression list."""
        clean_email = normalize_email(email)
        if not clean_email:
            return
        suppressed = self.load_suppression()
        if clean_email in suppressed:
            return
        with self.suppression_file.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=SUPPRESSION_HEADERS)
            writer.writerow(
                {
                    "email": clean_email,
                    "reason": reason.strip() or "manual",
                    "created_at": utc_now_iso(),
                }
            )

    def load_suppression(self) -> dict[str, str]:
        """Return suppressed emails mapped to their reason."""
        rows = self._read_dict_rows(self.suppression_file)
        return {
            normalize_email(row.get("email", "")): (row.get("reason") or "suppressed")
            for row in rows
            if normalize_email(row.get("email", ""))
        }

    def record_sent(
        self,
        *,
        email: str,
        campaign_id: str,
        subject: str,
        variant: str,
        status: str,
        reason: str,
        message_id: str = "",
    ) -> None:
        """Append one send attempt to the sent ledger."""
        with self.sent_ledger_file.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=SENT_LEDGER_HEADERS)
            writer.writerow(
                {
                    "email": normalize_email(email),
                    "campaign_id": campaign_id,
                    "subject": subject,
                    "variant": variant,
                    "status": status,
                    "reason": reason,
                    "message_id": message_id,
                    "sent_at": utc_now_iso(),
                }
            )

    def load_sent_rows(self) -> list[dict[str, str]]:
        """Return sent ledger rows."""
        return self._read_dict_rows(self.sent_ledger_file)

    def record_tracking_event(self, email: str, campaign_id: str, event_type: str) -> None:
        """Record an open/click/bounce event from a hosted tracking endpoint."""
        clean_event = (event_type or "").strip().lower()
        if clean_event == "bounce":
            self.add_suppression(email, "bounce")
        with self.tracking_file.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=TRACKING_HEADERS)
            writer.writerow(
                {
                    "email": normalize_email(email),
                    "campaign_id": campaign_id,
                    "event_type": clean_event,
                    "created_at": utc_now_iso(),
                }
            )

    def analytics_summary(self, campaign_id: str) -> dict[str, int | float]:
        """Return local analytics for a campaign."""
        sent_count = sum(
            1
            for row in self.load_sent_rows()
            if row.get("campaign_id") == campaign_id and row.get("status") == "sent"
        )
        event_rows = [
            row
            for row in self._read_dict_rows(self.tracking_file)
            if row.get("campaign_id") == campaign_id
        ]
        opens = len({row.get("email") for row in event_rows if row.get("event_type") == "open"})
        clicks = len({row.get("email") for row in event_rows if row.get("event_type") == "click"})
        bounces = len({row.get("email") for row in event_rows if row.get("event_type") == "bounce"})
        return {
            "sent": sent_count,
            "opens": opens,
            "clicks": clicks,
            "bounces": bounces,
            "open_rate": opens / sent_count if sent_count else 0.0,
            "click_rate": clicks / sent_count if sent_count else 0.0,
            "bounce_rate": bounces / sent_count if sent_count else 0.0,
        }

    def plan_campaign(self, contacts: list[Contact], config: CampaignConfig) -> CampaignPlan:
        """Return a complete send plan for every contact."""
        compliance_issues = tuple(validate_campaign(config))
        suppressed = self.load_suppression()
        sent_emails = {
            normalize_email(row.get("email", ""))
            for row in self.load_sent_rows()
            if row.get("status") == "sent"
        }
        seen_in_input: set[str] = set()
        decisions: list[RecipientDecision] = []

        for index, contact in enumerate(contacts):
            email = normalize_email(contact.email)
            variant, raw_subject = choose_subject(config, index)
            subject = render_template(raw_subject, contact, config)
            body = render_template(config.body, contact, config)
            risk = analyze_spam_risk(subject, body)

            status = "dry_run" if config.dry_run else "queued"
            reason = "ready_for_preview" if config.dry_run else "ready_to_send"
            if not is_valid_email_candidate(email):
                status, reason = "invalid", "invalid_or_placeholder_email"
            elif email in seen_in_input:
                status, reason = "duplicate_input", "duplicate_in_import_file"
            elif email in suppressed:
                status, reason = "suppressed", suppressed[email]
            elif email in sent_emails:
                status, reason = "already_sent", "global_duplicate_prevention"
            elif compliance_issues:
                status, reason = "compliance_blocked", "; ".join(compliance_issues)
            elif (
                config.require_permission
                and not contact.has_permission
                and not config.allow_manual_permission_override
            ):
                status, reason = "missing_permission", "permission_status_not_verified"
            elif config.block_high_risk and risk.score >= HIGH_RISK_THRESHOLD:
                status, reason = "risk_blocked", "high_spam_risk_copy"

            seen_in_input.add(email)
            decisions.append(
                RecipientDecision(
                    email=email,
                    status=status,
                    reason=reason,
                    variant=variant,
                    subject=subject,
                    body=append_required_footer(body, contact, config),
                    risk_score=risk.score,
                    risk_level=risk.level,
                    warnings=risk.warnings,
                )
            )

        return CampaignPlan(
            decisions=decisions,
            summary=summarize_decisions(decisions),
            compliance_issues=compliance_issues,
        )

    def send_campaign(
        self,
        contacts: list[Contact],
        config: CampaignConfig,
        *,
        smtp_settings: SMTPSettings | None = None,
        transport: EmailTransport | None = None,
        sleep_fn: Any = time.sleep,
        rng: random.Random | None = None,
        logger: Any = None,
    ) -> CampaignPlan:
        """Plan and send eligible campaign messages.

        Dry-run campaigns never use transport and never write the sent ledger.
        Actual sends are recorded only after the transport accepts the message.
        """
        plan = self.plan_campaign(contacts, config)
        if config.dry_run:
            return plan

        settings = smtp_settings or SMTPSettings.from_env()
        active_transport = transport or SmtpEmailTransport(settings)
        randomizer = rng or random.Random()
        sent_this_session = 0
        completed: list[RecipientDecision] = []

        for decision in plan.decisions:
            if decision.status != "queued":
                completed.append(decision)
                continue
            if sent_this_session >= max(0, config.session_limit):
                completed.append(
                    replace_decision(
                        decision,
                        status="session_limit",
                        reason="session_limit_reached",
                    )
                )
                continue

            if sent_this_session > 0:
                delay = randomizer.uniform(config.min_delay_seconds, config.max_delay_seconds)
                if logger:
                    logger(f"[OUTREACH] Waiting {delay:.1f}s before next email.")
                sleep_fn(delay)

            try:
                message = build_email_message(
                    settings,
                    Contact(decision.email, permission_status="verified"),
                    config,
                    subject=decision.subject,
                    body=decision.body,
                )
                message_id = active_transport.send(message)
                sent_this_session += 1
                self.record_sent(
                    email=decision.email,
                    campaign_id=config.campaign_id,
                    subject=decision.subject,
                    variant=decision.variant,
                    status="sent",
                    reason="delivered_to_smtp",
                    message_id=message_id,
                )
                if logger:
                    logger(f"[OUTREACH] Sent to {decision.email}")
                completed.append(
                    replace_decision(
                        decision,
                        status="sent",
                        reason="delivered_to_smtp",
                        message_id=message_id,
                    )
                )
            except (OSError, smtplib.SMTPException, ValueError) as exc:
                self.record_sent(
                    email=decision.email,
                    campaign_id=config.campaign_id,
                    subject=decision.subject,
                    variant=decision.variant,
                    status="failed",
                    reason=str(exc),
                )
                completed.append(
                    replace_decision(
                        decision,
                        status="failed",
                        reason=str(exc),
                    )
                )

        return CampaignPlan(
            decisions=completed,
            summary=summarize_decisions(completed),
            compliance_issues=plan.compliance_issues,
        )

    def _read_dict_rows(self, path: Path) -> list[dict[str, str]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open(encoding="utf-8", newline="") as file_obj:
            return [
                {key: value for key, value in row.items()}
                for row in csv.DictReader(file_obj)
                if row
            ]


def normalize_email(email: str) -> str:
    """Return a normalized email address."""
    return (email or "").strip().lower()


def utc_now_iso() -> str:
    """Return a stable UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_field(row: dict[str, str], field: str) -> str:
    """Read a CSV row field using common aliases."""
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in CONTACT_FIELD_ALIASES[field]:
        alias_key = alias.strip().lower()
        if alias_key in lowered:
            return str(lowered[alias_key] or "").strip()
    return ""


def load_contacts_from_csv(path: str | Path) -> list[Contact]:
    """Load contacts from a one-column or detailed CSV file."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Contact CSV not found: {csv_path}")
    with csv_path.open(encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        if not reader.fieldnames:
            return []
        return [
            Contact(
                email=get_field(row, "email"),
                name=get_field(row, "name"),
                city=get_field(row, "city"),
                project_type=get_field(row, "project_type"),
                company=get_field(row, "company"),
                permission_status=get_field(row, "permission_status"),
            )
            for row in reader
        ]


def validate_contact_source_path(
    path: str | Path,
    *,
    project_root: Path | str = PROJECT_ROOT,
) -> None:
    """Require outreach imports to come from master/final email export CSVs."""
    contact_path = Path(path).resolve()
    root = Path(project_root).resolve()
    if not contact_path.exists():
        raise FileNotFoundError(f"Contact CSV not found: {contact_path}")
    if contact_path.suffix.lower() != ".csv":
        raise ValueError("Outreach contacts must be loaded from a CSV file.")
    if root not in contact_path.parents and contact_path != root:
        raise ValueError("Outreach contacts must be inside the project folder.")

    relative_path = contact_path.relative_to(root)
    relative_parts = relative_path.parts
    if len(relative_parts) == 1:
        relative_dir = ""
    elif len(relative_parts) == 2:
        relative_dir = relative_parts[0].lower()
    else:
        relative_dir = "/".join(part.lower() for part in relative_parts[:-1])

    file_name = contact_path.name.lower()
    is_allowed_dir = relative_dir in ALLOWED_CONTACT_DIRS
    is_email_export = file_name.endswith("_emails.csv")
    if not is_allowed_dir or not is_email_export:
        raise ValueError(
            "Outreach can only use master/final email export CSVs such as "
            "houzz_emails.csv, bbb_emails.csv, or final/*_emails.csv."
        )

    with contact_path.open(encoding="utf-8", newline="") as file_obj:
        reader = csv.reader(file_obj)
        headers = next(reader, [])
    normalized_headers = {header.strip().lower() for header in headers}
    if "email" not in normalized_headers:
        raise ValueError("Contact CSV must contain an Email column.")


def validate_campaign(config: CampaignConfig) -> list[str]:
    """Return blocking compliance issues for a campaign."""
    issues = []
    if not config.campaign_id.strip():
        issues.append("campaign_id_required")
    if not config.subject_a.strip():
        issues.append("subject_required")
    if not config.body.strip():
        issues.append("body_required")
    if not config.company_name.strip():
        issues.append("company_name_required")
    if not config.physical_address.strip():
        issues.append("physical_address_required")
    if not config.unsubscribe_url.strip():
        issues.append("unsubscribe_url_required")
    if config.session_limit < 1:
        issues.append("session_limit_must_be_positive")
    if config.daily_limit < 1:
        issues.append("daily_limit_must_be_positive")
    if config.min_delay_seconds < 0 or config.max_delay_seconds < 0:
        issues.append("delay_must_not_be_negative")
    if config.min_delay_seconds > config.max_delay_seconds:
        issues.append("min_delay_must_not_exceed_max_delay")
    return issues


def choose_subject(config: CampaignConfig, index: int) -> tuple[str, str]:
    """Return A/B variant and subject text for an index."""
    if config.subject_b.strip() and index % 2 == 1:
        return "B", config.subject_b
    return "A", config.subject_a


def render_template(template: str, contact: Contact, config: CampaignConfig) -> str:
    """Render supported personalization placeholders."""
    values = {
        "name": contact.name or "there",
        "city": contact.city or "your area",
        "project_type": contact.project_type or "construction",
        "company": contact.company or "",
        "email": contact.email,
        "company_name": config.company_name,
        "physical_address": config.physical_address,
        "unsubscribe_link": unsubscribe_link(config.unsubscribe_url, contact.email),
    }
    rendered = template
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name and field_name not in values:
            values[field_name] = ""
    return rendered.format_map(DefaultFormatMap(values))


def unsubscribe_link(base_url: str, email: str) -> str:
    """Return a recipient-specific unsubscribe URL."""
    clean_base = (base_url or "").strip()
    if not clean_base:
        return ""
    separator = "&" if "?" in clean_base else "?"
    return f"{clean_base}{separator}email={quote_plus(normalize_email(email))}"


def append_required_footer(body: str, contact: Contact, config: CampaignConfig) -> str:
    """Append required commercial email footer if it is not already present."""
    footer = (
        f"\n\n--\n{config.company_name}\n{config.physical_address}\n"
        f"Unsubscribe: {unsubscribe_link(config.unsubscribe_url, contact.email)}"
    )
    body_lower = body.lower()
    has_address = (
        config.physical_address.lower() in body_lower if config.physical_address else False
    )
    has_unsubscribe = "unsubscribe" in body_lower
    if has_address and has_unsubscribe:
        return body
    return f"{body.rstrip()}{footer}"


def analyze_spam_risk(subject: str, body: str) -> SpamRiskReport:
    """Score common deliverability risks and suggest calmer copy."""
    combined = f"{subject}\n{body}"
    lower = combined.lower()
    score = 0
    warnings: list[str] = []
    suggestions: list[str] = []

    for phrase, weight in SPAM_TRIGGERS.items():
        if phrase in lower:
            score += weight
            warnings.append(f"Contains high-risk phrase: {phrase}")

    if subject and subject == subject.upper() and any(char.isalpha() for char in subject):
        score += 20
        warnings.append("Subject is all caps.")
    exclamation_count = combined.count("!")
    if exclamation_count >= 3:
        score += min(20, exclamation_count * 4)
        warnings.append("Too many exclamation marks.")
    link_count = lower.count("http://") + lower.count("https://")
    if link_count > 2:
        score += 12
        warnings.append("Too many links for an initial outreach email.")
    if "unsubscribe" not in lower:
        score += 8
        warnings.append("Missing visible unsubscribe language.")
    if "{name}" not in body and "hi " not in lower and "hello " not in lower:
        score += 6
        warnings.append("Message feels generic; add a human greeting or personalization.")

    if warnings:
        suggestions.append(
            "Use calmer construction-service wording and make the subject match the message."
        )
    if any(phrase in lower for phrase in ("free", "guaranteed", "cheapest", "act now")):
        suggestions.append(
            "Replace hype with a helpful question about the recipient's project or estimate needs."
        )
    if link_count > 1:
        suggestions.append("Keep the first email to one clear website or unsubscribe link.")

    clean_score = min(MAX_RISK_SCORE, score)
    if clean_score >= HIGH_RISK_THRESHOLD:
        level = "high"
    elif clean_score >= 35:
        level = "medium"
    else:
        level = "low"
    return SpamRiskReport(clean_score, level, tuple(warnings), tuple(suggestions))


def build_email_message(
    settings: SMTPSettings,
    contact: Contact,
    config: CampaignConfig,
    *,
    subject: str,
    body: str,
) -> EmailMessage:
    """Build a standards-friendly plain-text email message."""
    message = EmailMessage()
    sender_name = config.sender_name or settings.from_name or config.company_name
    message["From"] = formataddr((sender_name, settings.from_email))
    message["To"] = contact.email
    message["Subject"] = subject
    if settings.reply_to:
        message["Reply-To"] = settings.reply_to
    message["Message-ID"] = make_msgid()
    message["List-Unsubscribe"] = f"<{unsubscribe_link(config.unsubscribe_url, contact.email)}>"
    message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    message.set_content(append_required_footer(body, contact, config))
    return message


def summarize_decisions(decisions: list[RecipientDecision]) -> dict[str, int]:
    """Return counts for every status plus a total."""
    summary: dict[str, int] = {"total": len(decisions)}
    for decision in decisions:
        summary[decision.status] = summary.get(decision.status, 0) + 1
    for status in (
        "sent",
        "dry_run",
        "queued",
        "invalid",
        "duplicate_input",
        "suppressed",
        "already_sent",
        "missing_permission",
        "risk_blocked",
        "compliance_blocked",
        "failed",
        "session_limit",
    ):
        summary.setdefault(status, 0)
    return summary


def replace_decision(
    decision: RecipientDecision,
    *,
    status: str | None = None,
    reason: str | None = None,
    message_id: str | None = None,
) -> RecipientDecision:
    """Return a copy of a decision with changed fields."""
    return RecipientDecision(
        email=decision.email,
        status=decision.status if status is None else status,
        reason=decision.reason if reason is None else reason,
        variant=decision.variant,
        subject=decision.subject,
        body=decision.body,
        risk_score=decision.risk_score,
        risk_level=decision.risk_level,
        warnings=decision.warnings,
        message_id=decision.message_id if message_id is None else message_id,
    )


class DefaultFormatMap(dict[str, str]):
    """Format map that leaves unknown values empty instead of crashing."""

    def __missing__(self, key: str) -> str:
        return ""
