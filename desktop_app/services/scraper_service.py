"""Background task coordinator for the desktop dashboard."""

import asyncio
import csv
import queue
import smtplib
import threading
from typing import Any

from playwright.async_api import Error as PlaywrightError

from desktop_app.models import OutreachRunConfig, ScraperRunConfig
from desktop_app.services.file_service import (
    build_source_summary,
    open_path,
    reset_source_outputs,
)
from desktop_app.services.outreach_service import (
    CampaignConfig,
    EmailOutreachService,
    SMTPSettings,
    load_contacts_from_csv,
    validate_contact_source_path,
)
from houzz_pro_scraper import export_final_for_source, run_scraper
from scraper.config import PROJECT_ROOT
from scraper.runtime import ScraperRuntimeController

SCRAPER_TASK_ERRORS = (csv.Error, OSError, PlaywrightError, RuntimeError, ValueError)
EXPORT_TASK_ERRORS = (csv.Error, OSError, RuntimeError, ValueError)
OUTREACH_TASK_ERRORS = (csv.Error, OSError, RuntimeError, ValueError, smtplib.SMTPException)


def build_effective_run_options(config: ScraperRunConfig) -> dict[str, Any]:
    """Return backend scraper options after applying dashboard convenience toggles."""
    skip_slow_fallbacks = config.fast_mode
    return {
        "skip_facebook": config.skip_facebook or skip_slow_fallbacks,
        "skip_google_fallback": config.skip_google_fallback or skip_slow_fallbacks,
        "quality_filter": ("high",) if config.email_only else config.quality_filter,
    }


def build_campaign_config(config: OutreachRunConfig) -> CampaignConfig:
    """Return outreach campaign settings for the backend service."""
    return CampaignConfig(
        campaign_id=config.campaign_id.strip(),
        subject_a=config.subject_a.strip(),
        subject_b=config.subject_b.strip(),
        body=config.body.strip(),
        company_name=config.company_name.strip(),
        physical_address=config.physical_address.strip(),
        unsubscribe_url=config.unsubscribe_url.strip(),
        sender_name=config.sender_name.strip(),
        dry_run=config.dry_run,
        allow_manual_permission_override=config.confirm_permission,
        session_limit=config.session_limit,
        min_delay_seconds=config.min_delay_seconds,
        max_delay_seconds=config.max_delay_seconds,
    )


class ScraperDashboardService:
    """Own background scrape/export jobs and stream events back to the UI."""

    def __init__(self) -> None:
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._runtime: ScraperRuntimeController = ScraperRuntimeController(
            on_log=self._emit_log,
            on_snapshot=lambda snapshot: self._emit(
                "runtime",
                {"snapshot": snapshot.as_dict()},
            ),
        )
        self._mode = "idle"
        self._pending_restart: ScraperRunConfig | None = None
        self._outreach = EmailOutreachService()

    def _emit(self, event_type, payload=None):
        self._events.put({"type": event_type, "payload": payload or {}})

    def _emit_log(self, message):
        self._emit("log", {"message": message})

    def drain_events(self):
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def get_state(self):
        with self._lock:
            runtime_snapshot = self._runtime.snapshot_dict() if self._runtime else None
            return {
                "mode": self._mode,
                "busy": self._thread is not None,
                "runtime": runtime_snapshot,
                "restart_queued": self._pending_restart is not None,
            }

    def refresh_summary(self, source):
        summary = build_source_summary(source)
        self._emit("summary", {"summary": summary.as_dict()})
        return summary

    def start_run(self, config):
        with self._lock:
            if self._thread is not None:
                return False

            self._runtime.start_run(
                config.source,
                config.url,
                max_pages=config.max_pages,
                max_profiles=config.max_profiles,
            )
            self._mode = "scrape"

            self._thread = threading.Thread(
                target=self._run_scrape_task,
                args=(config,),
                daemon=True,
            )
            self._thread.start()

        self._emit("task", {"mode": "scrape", "status": "started"})
        return True

    def _run_scrape_task(self, config):
        try:
            effective_options = build_effective_run_options(config)
            self._emit_log(
                "[SYSTEM] Run options: "
                f"browser={'hidden/headless' if config.headless else 'visible'}; "
                f"facebook={'skip' if effective_options['skip_facebook'] else 'enabled'}; "
                "google_fallback="
                f"{'skip' if effective_options['skip_google_fallback'] else 'enabled'}; "
                f"retry_no_email={'on' if config.retry_no_email else 'off'}; "
                f"email_only={'on' if config.email_only else 'off'}; "
                f"speed={'fast' if config.fast_mode else 'normal'}; "
                f"auto_export={'on' if config.auto_export_final else 'off'}"
            )
            if config.fresh_start:
                removed = reset_source_outputs(config.source, out_filename=config.out_filename)
                if removed:
                    self._emit_log(
                        "[SYSTEM] Fresh start enabled. Previous source files were cleared."
                    )
                else:
                    self._emit_log(
                        "[SYSTEM] Fresh start enabled. No previous source files were found."
                    )
                self.refresh_summary(config.source)

            runtime = self._runtime
            if runtime is None:
                raise RuntimeError("Scraper runtime was not initialized.")

            asyncio.run(
                run_scraper(
                    config.url,
                    source=config.source,
                    max_pages=config.max_pages,
                    max_profiles=config.max_profiles,
                    headless=config.headless,
                    skip_facebook=effective_options["skip_facebook"],
                    country=config.country,
                    skip_google_fallback=effective_options["skip_google_fallback"],
                    auto_export_final=config.auto_export_final,
                    quality_filter=effective_options["quality_filter"],
                    retry_no_email=config.retry_no_email,
                    out_filename=config.out_filename,
                    logger=runtime.log,
                    runtime=runtime,
                )
            )
        except SCRAPER_TASK_ERRORS as exc:
            self._emit_log(f"[ERROR] {exc}")
            if self._runtime:
                self._runtime.complete_run(error_message=str(exc))
        finally:
            source = config.source
            self.refresh_summary(source)

            with self._lock:
                self._thread = None
                self._mode = "idle"
                # Keep runtime but signal completion
                self._runtime.complete_run()
                pending_restart = self._pending_restart
                self._pending_restart = None

            self._emit("task", {"mode": "scrape", "status": "finished", "source": source})

            if pending_restart:
                self._emit_log("[SYSTEM] Restarting scraper with current panel settings...")
                self.start_run(pending_restart)

    def start_export(self, source, quality_filter):
        with self._lock:
            if self._thread is not None:
                return False
            self._mode = "export"
            self._thread = threading.Thread(
                target=self._run_export_task,
                args=(source, tuple(quality_filter)),
                daemon=True,
            )
            self._thread.start()

        self._emit("task", {"mode": "export", "status": "started"})
        return True

    def _run_export_task(self, source, quality_filter):
        try:
            export_result = export_final_for_source(
                source,
                quality_filter=quality_filter,
                logger=self._emit_log,
            )
            self._emit("export", {"result": export_result, "source": source})
        except EXPORT_TASK_ERRORS as exc:
            self._emit_log(f"[ERROR] Export failed: {exc}")
        finally:
            self.refresh_summary(source)
            with self._lock:
                self._thread = None
                self._mode = "idle"
            self._emit("task", {"mode": "export", "status": "finished", "source": source})

    def analyze_outreach(self, config: OutreachRunConfig):
        """Load contacts and return a dry-run outreach plan."""
        validate_contact_source_path(config.contact_file, project_root=PROJECT_ROOT)
        contacts = load_contacts_from_csv(config.contact_file)
        campaign = build_campaign_config(config)
        plan = self._outreach.plan_campaign(contacts, campaign)
        self._emit(
            "outreach",
            {
                "status": "analyzed",
                "summary": plan.summary,
                "decisions": [decision.__dict__ for decision in plan.decisions],
            },
        )
        return plan

    def start_outreach(self, config: OutreachRunConfig):
        """Start an outreach campaign in the background."""
        try:
            validate_contact_source_path(config.contact_file, project_root=PROJECT_ROOT)
        except OUTREACH_TASK_ERRORS as exc:
            self._emit_log(f"[ERROR] Outreach failed: {exc}")
            self._emit(
                "outreach",
                {
                    "status": "failed",
                    "error": str(exc),
                    "summary": {},
                    "decisions": [],
                },
            )
            return False

        with self._lock:
            if self._thread is not None:
                return False
            self._mode = "outreach"
            self._thread = threading.Thread(
                target=self._run_outreach_task,
                args=(config,),
                daemon=True,
            )
            self._thread.start()

        self._emit("task", {"mode": "outreach", "status": "started"})
        return True

    def _run_outreach_task(self, config: OutreachRunConfig):
        try:
            validate_contact_source_path(config.contact_file, project_root=PROJECT_ROOT)
            contacts = load_contacts_from_csv(config.contact_file)
            campaign = build_campaign_config(config)
            smtp_settings = None if campaign.dry_run else SMTPSettings.from_env()
            self._emit_log(
                "[OUTREACH] "
                f"Campaign={campaign.campaign_id}; contacts={len(contacts)}; "
                f"mode={'dry-run' if campaign.dry_run else 'send'}; "
                f"session_limit={campaign.session_limit}; "
                f"delay={campaign.min_delay_seconds:.0f}-{campaign.max_delay_seconds:.0f}s"
            )
            plan = self._outreach.send_campaign(
                contacts,
                campaign,
                smtp_settings=smtp_settings,
                logger=self._emit_log,
            )
            self._emit(
                "outreach",
                {
                    "status": "finished",
                    "summary": plan.summary,
                    "decisions": [decision.__dict__ for decision in plan.decisions],
                },
            )
            self._emit_log(f"[OUTREACH] Finished. Summary: {plan.summary}")
        except OUTREACH_TASK_ERRORS as exc:
            self._emit_log(f"[ERROR] Outreach failed: {exc}")
            self._emit(
                "outreach",
                {
                    "status": "failed",
                    "error": str(exc),
                    "summary": {},
                    "decisions": [],
                },
            )
        finally:
            with self._lock:
                self._thread = None
                self._mode = "idle"
            self._emit("task", {"mode": "outreach", "status": "finished"})

    def get_outreach_analytics(self, campaign_id: str):
        """Return local analytics for an outreach campaign."""
        return self._outreach.analytics_summary(campaign_id)

    def pause_run(self):
        with self._lock:
            runtime = self._runtime
        if not runtime:
            return False
        runtime.request_pause()
        self._emit_log("[SYSTEM] Pause requested. Active profiles will finish their current step.")
        return True

    def resume_run(self):
        with self._lock:
            runtime = self._runtime
        if not runtime:
            return False
        runtime.request_resume()
        self._emit_log("[SYSTEM] Resume requested. Scraper scheduling is active again.")
        return True

    def stop_run(self):
        with self._lock:
            runtime = self._runtime
        if not runtime:
            return False
        runtime.request_stop()
        self._emit_log("[SYSTEM] Stop requested. The scraper will wind down safely.")
        return True

    def restart_run(self, config):
        with self._lock:
            busy = self._thread is not None
            mode = self._mode
            if busy and mode != "scrape":
                return False
            if busy:
                self._pending_restart = config
                runtime = self._runtime
            else:
                runtime = None

        if runtime:
            runtime.request_stop()
            self._emit_log("[SYSTEM] Restart queued. Current run is being stopped first.")
            return True
        return self.start_run(config)

    def open_system_path(self, path):
        open_path(path)
