"""Runtime state container shared between the scraper and desktop UI."""

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from threading import Event, Lock


def _now_iso():
    """Return the current local timestamp in a compact ISO format."""
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Immutable snapshot of the current run state."""

    run_state: str = "idle"
    source: str = "houzz"
    input_url: str = ""
    max_pages: int | None = None
    max_profiles: int | None = None
    current_page: int = 0
    profiles_discovered: int = 0
    profiles_attempted: int = 0
    profiles_skipped: int = 0
    processed: int = 0
    failed: int = 0
    no_email: int = 0
    master_saved: int = 0
    detail_saved: int = 0
    active_profiles: int = 0
    last_message: str = ""
    last_profile_url: str = ""
    started_at: str = ""
    finished_at: str = ""
    final_export_count: int = 0
    final_output_file: str = ""
    final_detail_file: str = ""
    error_message: str = ""

    @property
    def checked_total(self):
        return self.processed + self.failed + self.no_email + self.profiles_skipped

    @property
    def progress_ratio(self):
        if self.max_profiles:
            return min(1.0, self.checked_total / max(self.max_profiles, 1))
        if self.max_pages:
            return min(1.0, self.current_page / max(self.max_pages, 1))
        return 0.0

    def as_dict(self):
        data = asdict(self)
        data["checked_total"] = self.checked_total
        data["progress_ratio"] = self.progress_ratio
        return data


class ScraperRuntimeController:
    """Thread-safe controller used for run state, pause, resume, and stop."""

    def __init__(
        self,
        on_log: Callable[[str], None] | None = None,
        on_snapshot: Callable[[RuntimeSnapshot], None] | None = None,
    ):
        self._lock = Lock()
        self._stop_requested = Event()
        self._pause_requested = Event()
        self._on_log = on_log
        self._on_snapshot = on_snapshot
        self._snapshot = RuntimeSnapshot()

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def snapshot_dict(self):
        return self.snapshot().as_dict()

    def _emit_snapshot(self, snapshot):
        if self._on_snapshot:
            self._on_snapshot(snapshot)

    def _replace(self, **changes):
        with self._lock:
            snapshot_data = asdict(self._snapshot)
            snapshot_data.update(changes)
            self._snapshot = RuntimeSnapshot(**snapshot_data)
            snapshot = self._snapshot
        self._emit_snapshot(snapshot)
        return snapshot

    def log(self, message):
        clean_message = (message or "").rstrip()
        if not clean_message:
            return
        self._replace(last_message=clean_message)
        if self._on_log:
            self._on_log(clean_message)

    def start_run(self, source, input_url, max_pages=None, max_profiles=None):
        self._stop_requested.clear()
        self._pause_requested.clear()
        self._replace(
            run_state="running",
            source=source,
            input_url=input_url,
            max_pages=max_pages,
            max_profiles=max_profiles,
            current_page=0,
            profiles_discovered=0,
            profiles_attempted=0,
            profiles_skipped=0,
            processed=0,
            failed=0,
            no_email=0,
            master_saved=0,
            detail_saved=0,
            active_profiles=0,
            last_message="",
            last_profile_url="",
            started_at=_now_iso(),
            finished_at="",
            final_export_count=0,
            final_output_file="",
            final_detail_file="",
            error_message="",
        )

    def request_pause(self):
        self._pause_requested.set()
        if self.snapshot().run_state == "running":
            self._replace(run_state="paused")

    def request_resume(self):
        self._pause_requested.clear()
        if (
            self.snapshot().run_state in {"paused", "stopping"}
            and not self._stop_requested.is_set()
        ):
            self._replace(run_state="running")

    def request_stop(self):
        self._stop_requested.set()
        self._pause_requested.clear()
        self._replace(run_state="stopping")

    def is_paused(self):
        return self._pause_requested.is_set()

    def is_stop_requested(self):
        return self._stop_requested.is_set()

    async def wait_if_paused(self):
        while self.is_paused() and not self.is_stop_requested():
            await asyncio.sleep(0.25)

    def register_page(self, page_number, discovered_count=0):
        current = self.snapshot()
        self._replace(
            current_page=max(page_number, current.current_page),
            profiles_discovered=current.profiles_discovered + max(discovered_count, 0),
        )

    def record_skipped_profile(self, profile_url=""):
        current = self.snapshot()
        self._replace(
            profiles_skipped=current.profiles_skipped + 1,
            last_profile_url=profile_url or current.last_profile_url,
        )

    def record_attempted_profile(self, profile_url=""):
        current = self.snapshot()
        self._replace(
            profiles_attempted=current.profiles_attempted + 1,
            active_profiles=current.active_profiles + 1,
            last_profile_url=profile_url or current.last_profile_url,
        )

    def record_profile_result(self, profile_url, result):
        current = self.snapshot()
        status = result.get("status", "")
        updates = {
            "active_profiles": max(0, current.active_profiles - 1),
            "last_profile_url": profile_url or current.last_profile_url,
            "master_saved": current.master_saved + int(result.get("master_saved", 0) or 0),
            "detail_saved": current.detail_saved + int(result.get("detail_saved", 0) or 0),
        }

        if status in {"processed", "failed", "no_email"}:
            updates[status] = getattr(current, status) + 1

        self._replace(**updates)

    def record_export(self, export_result):
        self._replace(
            final_export_count=int(export_result.get("count", 0) or 0),
            final_output_file=export_result.get("final_output_file", ""),
            final_detail_file=export_result.get("final_detail_file", ""),
        )

    def complete_run(self, error_message=""):
        final_state = (
            "failed" if error_message else "stopped" if self.is_stop_requested() else "completed"
        )
        self._replace(
            run_state=final_state,
            active_profiles=0,
            finished_at=_now_iso(),
            error_message=error_message,
        )
