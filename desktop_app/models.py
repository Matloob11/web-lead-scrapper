"""Data models used by the desktop dashboard layer."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ScraperRunConfig:
    """Settings collected from the dashboard before starting a run."""

    url: str = ""
    source: str = "houzz"
    access_identity: str = ""
    max_pages: int | None = None
    max_profiles: int | None = None
    headless: bool = False
    skip_facebook: bool = False
    skip_google_fallback: bool = False
    retry_no_email: bool = False
    country: str = ""
    auto_export_final: bool = True
    quality_filter: tuple[str, ...] = ("high", "medium")
    fresh_start: bool = False
    email_only: bool = False
    fast_mode: bool = False
    out_filename: str | None = None

    def as_dict(self):
        """Return a plain dictionary form of the config."""
        return asdict(self)


@dataclass(frozen=True)
class SourceDashboardSummary:
    """Aggregated source-level counts displayed by the dashboard."""

    source: str
    master_count: int = 0
    detail_count: int = 0
    final_count: int = 0
    tracked_profiles: int = 0
    processed_count: int = 0
    failed_count: int = 0
    no_email_count: int = 0
    duplicate_count: int = 0
    high_quality_count: int = 0
    medium_quality_count: int = 0
    low_quality_count: int = 0
    last_updated: str = ""
    files: dict[str, str] = field(default_factory=dict)

    @property
    def success_rate(self):
        """Return the processed ratio for all tracked profiles."""
        total = self.processed_count + self.failed_count + self.no_email_count
        if not total:
            return 0.0
        return self.processed_count / total

    def as_dict(self):
        """Return a dictionary representation with derived metrics included."""
        data = asdict(self)
        data["success_rate"] = self.success_rate
        return data
