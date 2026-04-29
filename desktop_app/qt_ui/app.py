"""PySide6 dashboard window for managing scraper runs and output files."""

# pylint: disable=attribute-defined-outside-init,invalid-name

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from desktop_app.models import OutreachRunConfig, ScraperRunConfig
from desktop_app.qt_ui.components import MetricCard, Section
from desktop_app.qt_ui.theme import APP_STYLE, COLORS
from desktop_app.services.file_service import build_source_summary
from desktop_app.services.scraper_service import ScraperDashboardService
from desktop_app.view_models import (
    RuntimeSnapshotDict,
    SummarySnapshotDict,
    build_progress_note,
    format_source,
    format_timestamp,
    safe_int,
    summary_file_paths,
)
from scraper.config import PROJECT_ROOT

MAX_WIDGET_SIZE = 16777215
SHELL_STACK_BREAKPOINT = 940
WORKSPACE_STACK_BREAKPOINT = 650
METRIC_ORDER = ("checked", "active", "processed", "no_email", "failed", "emails")
OUTREACH_DEFAULT_BODY = """Hi {name},

I noticed you may have construction or remodeling needs in {city}. We are a registered
construction company and can help with estimates, planning, and reliable crew scheduling
for {project_type} work.

Would it be useful if I sent a short estimate checklist?

Thanks,
{company_name}
"""


class QtDashboardWindow(QMainWindow):
    """Professional PySide6 dashboard for the scraper service."""

    def __init__(self) -> None:
        super().__init__()
        self._ui_ready = False
        self.service = ScraperDashboardService()
        self.summary_snapshot: SummarySnapshotDict = {}
        self.runtime_snapshot: RuntimeSnapshotDict | None = None
        self.metric_cards: dict[str, MetricCard] = {}
        self._current_cols: int = -1

        self.setWindowTitle("Matloob Lead Command Center")
        self.setMinimumSize(1080, 720)
        self.setStyleSheet(APP_STYLE)

        self._build_main_ui()
        self._seed_defaults()
        self._setup_refresh_timer()

        self._ui_ready = True
        self._refresh_dashboard()

    def _build_main_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Sidebar (Static)
        self.sidebar = self._build_sidebar()
        main_layout.addWidget(self.sidebar)

        # Right Content (Dynamic Stack)
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # Page 0: Scraper Dashboard
        self.dashboard_page = QWidget()
        dash_layout = QVBoxLayout(self.dashboard_page)
        dash_layout.setContentsMargins(20, 20, 20, 20)
        dash_layout.setSpacing(20)

        self.metric_grid_container = QWidget()
        self.metric_grid = QGridLayout(self.metric_grid_container)
        self.metric_grid.setContentsMargins(0, 0, 0, 0)
        self.metric_grid.setSpacing(12)
        dash_layout.addWidget(self.metric_grid_container)

        self.main_area = QScrollArea()
        self.main_area.setWidgetResizable(True)
        self.main_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 10, 0)
        self.scroll_layout.setSpacing(15)

        self.scroll_layout.addWidget(self._build_progress_panel())
        self.scroll_layout.addWidget(self._build_activity_panel())
        self.scroll_layout.addStretch(1)

        self.main_area.setWidget(self.scroll_content)
        dash_layout.addWidget(self.main_area)

        self.content_stack.addWidget(self.dashboard_page)

        # Page 1: Dedicated Data Center
        self.data_page = self._build_dedicated_data_page()
        self.content_stack.addWidget(self.data_page)

        # Page 2: Email Outreach
        self.outreach_page = self._build_outreach_page()
        self.content_stack.addWidget(self.outreach_page)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(10)

        brand = QLabel("MATLOOB")
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        layout.addSpacing(20)

        # Web-style navigation menu
        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("Muted")
        layout.addWidget(nav_label)

        self.nav_houzz = self._nav_button(
            "Houzz Scraper", QStyle.StandardPixmap.SP_ComputerIcon, "houzz"
        )
        self.nav_bbb = self._nav_button("BBB Scraper", QStyle.StandardPixmap.SP_DriveHDIcon, "bbb")
        self.nav_data = self._nav_button(
            "Data Center", QStyle.StandardPixmap.SP_DirHomeIcon, "data"
        )
        self.nav_outreach = self._nav_button(
            "Email Outreach", QStyle.StandardPixmap.SP_FileDialogInfoView, "outreach"
        )

        self.nav_group = QButtonGroup(self)
        self.nav_group.addButton(self.nav_houzz)
        self.nav_group.addButton(self.nav_bbb)
        self.nav_group.addButton(self.nav_data)
        self.nav_group.addButton(self.nav_outreach)
        self.nav_houzz.setChecked(True)

        layout.addWidget(self.nav_houzz)
        layout.addWidget(self.nav_bbb)
        layout.addWidget(self.nav_data)
        layout.addWidget(self.nav_outreach)
        layout.addSpacing(15)

        config_label = QLabel("CONFIGURATION")
        config_label.setObjectName("Muted")
        layout.addWidget(config_label)

        layout.addWidget(QLabel("Target Pages:"))
        self.max_pages_input = self._line_edit("Optional")
        layout.addWidget(self.max_pages_input)

        layout.addWidget(QLabel("Profile Slots:"))
        self.max_profiles_input = self._line_edit("Optional")
        layout.addWidget(self.max_profiles_input)

        # Scraper Options
        layout.addSpacing(10)
        self.headless_check = QCheckBox("Hide Browser (Headless)")
        self.email_only_check = QCheckBox("Verified Email Only")
        self.fast_mode_check = QCheckBox("Aggressive Speed")
        self.skip_facebook_check = QCheckBox("Skip Facebook Search")
        self.skip_google_check = QCheckBox("Skip Google Fallback")
        self.retry_no_email_check = QCheckBox("Retry No-Email Profiles")
        self.fresh_start_check = QCheckBox("Fresh Start (Clear Progress)")

        # Add to layout
        for check in [
            self.headless_check,
            self.email_only_check,
            self.fast_mode_check,
            self.skip_facebook_check,
            self.skip_google_check,
            self.retry_no_email_check,
            self.fresh_start_check,
        ]:
            layout.addWidget(check)

        layout.addStretch(1)

        # System Status
        self.status_dot = QLabel("●  Idle")
        self.status_dot.setObjectName("StatusIdle")
        layout.addWidget(self.status_dot)

        # Hidden legacy components to maintain internal logic
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Houzz", "BBB"])
        self.source_combo.hide()
        self.source_combo.currentTextChanged.connect(self._on_source_change)

        return sidebar

    def _nav_button(self, text: str, icon: QStyle.StandardPixmap, view_id: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("NavButton")
        btn.setIcon(self.style().standardIcon(icon))
        btn.setCheckable(True)
        btn.setFixedHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._switch_view(view_id))
        return btn

    def _switch_view(self, view: str) -> None:
        if view == "houzz":
            self.nav_houzz.setChecked(True)
            self.source_combo.setCurrentText("Houzz")
            self.content_stack.setCurrentIndex(0)
        elif view == "bbb":
            self.nav_bbb.setChecked(True)
            self.source_combo.setCurrentText("BBB")
            self.content_stack.setCurrentIndex(0)
        elif view == "data":
            self.nav_data.setChecked(True)
            self.content_stack.setCurrentIndex(1)
        elif view == "outreach":
            self.nav_outreach.setChecked(True)
            self.content_stack.setCurrentIndex(2)
            self._seed_outreach_contact_file()

        self._refresh_dashboard()

    def _build_dedicated_data_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        header = QLabel("Data Center")
        header.setObjectName("PageTitle")
        layout.addWidget(header)

        info = QLabel("Manage your scraped results, history, and exports.")
        info.setObjectName("Muted")
        layout.addWidget(info)

        # Full-page Data Panel
        self.data_console = QPlainTextEdit()
        self.data_console.setReadOnly(True)
        self.data_console.setObjectName("DataConsole")
        self.data_console.setPlaceholderText("No scrape history available for the selected source.")
        layout.addWidget(self.data_console, 1)

        btn_row = QHBoxLayout()
        self.open_dir_btn = QPushButton("Browse Files")
        self.open_dir_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_dir_btn.clicked.connect(self._on_open_directory)

        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self._refresh_dashboard)

        btn_row.addWidget(self.open_dir_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return page

    def _build_outreach_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(16)

        header = QLabel("Email Outreach")
        header.setObjectName("PageTitle")
        layout.addWidget(header)

        form = QFrame()
        form.setObjectName("InputSection")
        grid = QGridLayout(form)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.outreach_contact_file_input = self._line_edit("final/houzz_high_quality_emails.csv")
        self.outreach_contact_file_input.setObjectName("TargetUrlInput")
        browse_btn = QPushButton("Browse")
        browse_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_btn.clicked.connect(self._on_browse_outreach_contacts)

        contact_row = QHBoxLayout()
        contact_row.setContentsMargins(0, 0, 0, 0)
        contact_row.setSpacing(8)
        contact_row.addWidget(self.outreach_contact_file_input, 1)
        contact_row.addWidget(browse_btn)

        self.outreach_campaign_id_input = self._line_edit("construction-outreach")
        self.outreach_company_input = self._line_edit("Company name")
        self.outreach_sender_name_input = self._line_edit("Sender display name")
        self.outreach_address_input = self._line_edit("Physical postal address")
        self.outreach_unsubscribe_input = self._line_edit("https://yourdomain.com/unsubscribe")
        self.outreach_subject_a_input = self._line_edit("Planning a remodel in {city}?")
        self.outreach_subject_b_input = self._line_edit("Need a construction estimate in {city}?")

        self.outreach_body_input = QPlainTextEdit()
        self.outreach_body_input.setObjectName("LogConsole")
        self.outreach_body_input.setMinimumHeight(170)
        self.outreach_body_input.setPlainText(OUTREACH_DEFAULT_BODY)

        fields: list[tuple[str, QWidget | QHBoxLayout]] = [
            ("Contacts CSV", contact_row),
            ("Campaign ID", self.outreach_campaign_id_input),
            ("Company", self.outreach_company_input),
            ("Sender", self.outreach_sender_name_input),
            ("Address", self.outreach_address_input),
            ("Unsubscribe URL", self.outreach_unsubscribe_input),
            ("Subject A", self.outreach_subject_a_input),
            ("Subject B", self.outreach_subject_b_input),
        ]
        for row_index, (label_text, widget_or_layout) in enumerate(fields):
            label = QLabel(label_text)
            label.setObjectName("InputLabel")
            grid.addWidget(label, row_index, 0)
            if isinstance(widget_or_layout, QHBoxLayout):
                grid.addLayout(widget_or_layout, row_index, 1)
            else:
                grid.addWidget(widget_or_layout, row_index, 1)

        body_row = len(fields)
        body_label = QLabel("Body")
        body_label.setObjectName("InputLabel")
        body_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        grid.addWidget(body_label, body_row, 0)
        grid.addWidget(self.outreach_body_input, body_row, 1)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnStretch(1, 1)
        layout.addWidget(form)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.outreach_dry_run_check = QCheckBox("Dry Run")
        self.outreach_dry_run_check.setChecked(True)
        self.outreach_permission_check = QCheckBox("Permission Confirmed")
        self.outreach_session_limit_input = self._line_edit("25")
        self.outreach_min_delay_input = self._line_edit("60")
        self.outreach_max_delay_input = self._line_edit("180")
        controls.addWidget(self.outreach_dry_run_check)
        controls.addWidget(self.outreach_permission_check)
        controls.addWidget(QLabel("Session Limit"))
        controls.addWidget(self.outreach_session_limit_input)
        controls.addWidget(QLabel("Delay Min"))
        controls.addWidget(self.outreach_min_delay_input)
        controls.addWidget(QLabel("Delay Max"))
        controls.addWidget(self.outreach_max_delay_input)
        layout.addLayout(controls)

        action_row = QHBoxLayout()
        self.outreach_analyze_btn = QPushButton("Analyze")
        self.outreach_analyze_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.outreach_analyze_btn.clicked.connect(self._on_analyze_outreach_click)
        self.outreach_send_btn = QPushButton("Start Outreach")
        self.outreach_send_btn.setObjectName("PrimaryButton")
        self.outreach_send_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.outreach_send_btn.clicked.connect(self._on_send_outreach_click)
        action_row.addWidget(self.outreach_analyze_btn)
        action_row.addWidget(self.outreach_send_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.outreach_report_console = QPlainTextEdit()
        self.outreach_report_console.setReadOnly(True)
        self.outreach_report_console.setObjectName("DataConsole")
        self.outreach_report_console.setMinimumHeight(190)
        layout.addWidget(self.outreach_report_console, 1)

        return page

    def _line_edit(self, placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFixedHeight(34)
        return edit

    def _build_progress_panel(self) -> Section:
        section = Section("")

        # Initialize labels but don't add them to the panel layout
        # as requested (to keep the UI clean)
        self.run_progress_note = QLabel()
        self.success_rate_note = QLabel()

        self._add_search_inputs(section.body_layout)
        section.body_layout.addSpacing(8)
        self._add_action_controls(section.body_layout)
        return section

    def _add_search_inputs(self, layout: QVBoxLayout) -> None:
        container = QFrame()
        container.setObjectName("InputSection")
        grid = QGridLayout(container)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        url_label = QLabel("Target Search URL")
        url_label.setObjectName("InputLabel")
        url_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        file_label = QLabel("Output CSV Name")
        file_label.setObjectName("InputLabel")
        file_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.target_url_input = self._line_edit("Paste Houzz or BBB search URL here...")
        self.target_url_input.setObjectName("TargetUrlInput")
        self.target_url_input.setFixedHeight(42)

        self.output_filename_input = QComboBox()
        self.output_filename_input.setObjectName("OutputFilenameInput")
        self.output_filename_input.setFixedHeight(42)
        self.output_filename_input.setCursor(Qt.CursorShape.PointingHandCursor)
        self._populate_output_options()
        self.output_filename_input.currentTextChanged.connect(self._on_output_type_changed)

        self.custom_filename_input = self._line_edit("Type custom name here (e.g., my_data.csv)...")
        self.custom_filename_input.setObjectName("CustomFilenameInput")
        self.custom_filename_input.hide()

        combo_layout = QVBoxLayout()
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(5)
        combo_layout.addWidget(self.output_filename_input)
        combo_layout.addWidget(self.custom_filename_input)

        grid.addWidget(url_label, 0, 0)
        grid.addWidget(self.target_url_input, 0, 1)
        grid.addWidget(file_label, 1, 0)
        grid.addLayout(combo_layout, 1, 1)

        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnStretch(1, 1)
        layout.addWidget(container)

    def _on_output_type_changed(self, text: str) -> None:
        if text == "Custom":
            self.custom_filename_input.show()
            self.custom_filename_input.setFocus()
        else:
            self.custom_filename_input.hide()

    def _populate_output_options(self, keep_current: bool = False) -> None:
        """Scan project root for existing CSV files and populate dropdown."""
        current_text = self.output_filename_input.currentText().strip()
        self.output_filename_input.clear()

        # Determine defaults based on current source
        source = self.current_source().lower()
        default_file = f"{source}_emails.csv"
        options = [default_file, "Custom"]

        try:
            for path in PROJECT_ROOT.iterdir():
                item = path.name
                is_csv = path.is_file() and item.endswith(".csv")
                is_log = "_status" in item or "_failures" in item
                if is_csv and item not in options and not is_log:
                    options.append(item)
        except OSError:
            pass

        if "Custom" in options:
            options.remove("Custom")
        options = sorted(options)
        options.append("Custom")

        self.output_filename_input.addItems(options)
        if keep_current and current_text:
            self.output_filename_input.setCurrentText(current_text)
        else:
            self.output_filename_input.setCurrentText(default_file)

    def _show_output_filename_options(self) -> None:
        """Refresh CSV choices and open the editable output filename dropdown."""
        self._populate_output_options(keep_current=True)
        self.output_filename_input.showPopup()

    # eventFilter removed since we don't use editable combobox anymore

    def _build_activity_panel(self) -> Section:
        section = Section("Activity Feed", "Scraper events")
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setObjectName("LogConsole")
        self.log_console.setMinimumHeight(300)
        section.body_layout.addWidget(self.log_console)
        return section

    def _add_action_controls(self, layout: QVBoxLayout) -> None:
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.start_btn = QPushButton("  Start Extraction")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start_click)

        self.stop_btn = QPushButton("  Stop")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_btn.setIconSize(QSize(14, 14))
        self.stop_btn.setFixedHeight(44)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_click)

        self.pause_btn = QPushButton("  Pause")
        self.pause_btn.setObjectName("WarningButton")
        self.pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.pause_btn.setIconSize(QSize(14, 14))
        self.pause_btn.setFixedHeight(44)
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_click)

        self.resume_btn = QPushButton("  Resume")
        self.resume_btn.setObjectName("PrimaryButton")
        self.resume_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.resume_btn.setIconSize(QSize(14, 14))
        self.resume_btn.setFixedHeight(44)
        self.resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._on_resume_click)

        self.restart_btn = QPushButton("  Restart")
        self.restart_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.restart_btn.setIconSize(QSize(14, 14))
        self.restart_btn.setFixedHeight(44)
        self.restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restart_btn.clicked.connect(self._on_restart_click)

        self.export_btn = QPushButton("  Export")
        self.export_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
        self.export_btn.setIconSize(QSize(14, 14))
        self.export_btn.setFixedHeight(44)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self._on_export_click)

        btn_layout.addWidget(self.start_btn, 2)
        btn_layout.addWidget(self.stop_btn, 1)
        btn_layout.addWidget(self.pause_btn, 1)
        btn_layout.addWidget(self.resume_btn, 1)
        btn_layout.addWidget(self.restart_btn, 1)
        btn_layout.addWidget(self.export_btn, 1)
        layout.addLayout(btn_layout)

    def _setup_refresh_timer(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_dashboard)
        self.refresh_timer.start(1000)

    def _refresh_dashboard(self) -> None:
        self._drain_service_events()
        state = self.service.get_state()
        runtime_snapshot = state.get("runtime")
        if runtime_snapshot is not None:
            self.runtime_snapshot = runtime_snapshot

        if not self.summary_snapshot or not state.get("busy"):
            self.summary_snapshot = build_source_summary(self.current_source()).as_dict()

        self._apply_runtime(self.runtime_snapshot)
        self._apply_summary(self.summary_snapshot)
        self._update_status(state)

    def _drain_service_events(self) -> None:
        for event in self.service.drain_events():
            event_type = event.get("type")
            payload = event.get("payload", {})
            if event_type == "log":
                self._append_log(str(payload.get("message", "")))
            elif event_type == "summary":
                summary = payload.get("summary")
                if isinstance(summary, dict):
                    self.summary_snapshot = summary
            elif event_type == "runtime":
                snapshot = payload.get("snapshot")
                if isinstance(snapshot, dict):
                    self.runtime_snapshot = snapshot
            elif event_type == "outreach":
                self._append_outreach_report(payload)

    def _apply_runtime(self, runtime: RuntimeSnapshotDict | None) -> None:
        if not runtime:
            self.run_progress_note.setText("Engine is idle. Ready for new extraction.")
            self.success_rate_note.setText("Configure targets in the sidebar and press Start.")
            return

        self.run_progress_note.setText(build_progress_note(runtime))

        checked = int(runtime.get("checked_total", 0) or 0)
        processed = int(runtime.get("processed", 0) or 0)
        saved = int(runtime.get("master_saved", 0) or 0)
        if checked:
            self.success_rate_note.setText(
                f"{processed} profiles processed, {saved} new emails saved."
            )
        else:
            self.success_rate_note.setText("Extraction started. Waiting for first profile result.")

    def _apply_summary(self, summary: SummarySnapshotDict) -> None:
        # Update values
        active_profiles = 0
        if self.runtime_snapshot:
            active_profiles = int(self.runtime_snapshot.get("active_profiles", 0) or 0)

        mapping = {
            "checked": summary.get("tracked_profiles", 0),
            "active": active_profiles,
            "processed": summary.get("processed_count", 0),
            "no_email": summary.get("no_email_count", 0),
            "failed": summary.get("failed_count", 0),
            "emails": summary.get("final_count", 0),
        }

        # Clear and rebuild if columns changed or first run
        target_cols = self._metric_column_count(self.dashboard_page.width())
        self._relayout_metrics(target_cols)

        for key in METRIC_ORDER:
            if key in self.metric_cards:
                self.metric_cards[key].set_metric(mapping.get(key, 0))

        # Update data console
        data_lines = [
            f"SOURCE: {format_source(str(summary.get('source', '')))}",
            f"LAST UPDATED: {format_timestamp(str(summary.get('last_updated', '')))}",
            "-" * 40,
            f"TOTAL RECORDS: {summary.get('tracked_profiles', 0)}",
            f"VERIFIED EMAILS: {summary.get('processed_count', 0)}",
            f"MISSING DATA: {summary.get('no_email_count', 0)}",
            f"FAILURE COUNT: {summary.get('failed_count', 0)}",
            f"ACTIVE PROFILES: {active_profiles}",
            "-" * 40,
            "FILES FOUND:",
        ]
        data_lines.extend([f"  - {path}" for path in summary_file_paths(summary)])
        self.data_console.setPlainText("\n".join(data_lines))

    def _sync_logs(self, logs: list[str]) -> None:
        current_count = self.log_console.document().blockCount()
        if len(logs) > current_count:
            for i in range(current_count, len(logs)):
                self._append_log(logs[i])

    def _update_status(self, state: dict[str, Any]) -> None:
        is_busy = state.get("busy", False)
        mode = state.get("mode", "idle")
        run_state = ""
        if self.runtime_snapshot:
            run_state = str(self.runtime_snapshot.get("run_state", ""))

        if is_busy:
            if mode == "outreach":
                status_label = "Outreach..."
            elif mode == "export":
                status_label = "Exporting..."
            else:
                status_label = "Paused" if run_state == "paused" else "Extracting..."
            self.status_dot.setText(f"●  {status_label}")
            self.status_dot.setObjectName("StatusBusy")
        else:
            self.status_dot.setText("●  Idle")
            self.status_dot.setObjectName("StatusIdle")

        is_scrape = is_busy and mode == "scrape"
        self.start_btn.setEnabled(not is_busy)
        self.stop_btn.setEnabled(is_scrape)
        self.pause_btn.setEnabled(is_scrape and run_state == "running")
        self.resume_btn.setEnabled(is_scrape and run_state == "paused")
        self.restart_btn.setEnabled(mode != "export")
        self.export_btn.setEnabled(not is_busy)
        if hasattr(self, "outreach_analyze_btn"):
            self.outreach_analyze_btn.setEnabled(not is_busy)
            self.outreach_send_btn.setEnabled(not is_busy)
        self.status_dot.setStyle(self.status_dot.style())

    def _current_output_filename(self) -> str:
        out_filename = self.output_filename_input.currentText().strip()
        if out_filename == "Custom":
            out_filename = self.custom_filename_input.text().strip()
            if not out_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_filename = f"{self.current_source().lower()}_custom_{timestamp}.csv"
            elif not out_filename.lower().endswith(".csv"):
                out_filename += ".csv"
        return out_filename

    def _build_run_config(self) -> ScraperRunConfig:
        return ScraperRunConfig(
            url=self.target_url_input.text().strip(),
            source=self.current_source(),
            max_pages=safe_int(self.max_pages_input.text()),
            max_profiles=safe_int(self.max_profiles_input.text()),
            headless=self.headless_check.isChecked(),
            email_only=self.email_only_check.isChecked(),
            fast_mode=self.fast_mode_check.isChecked(),
            skip_facebook=self.skip_facebook_check.isChecked(),
            skip_google_fallback=self.skip_google_check.isChecked(),
            retry_no_email=self.retry_no_email_check.isChecked(),
            fresh_start=self.fresh_start_check.isChecked(),
            out_filename=self._current_output_filename(),
        )

    def _seed_outreach_contact_file(self) -> None:
        if not hasattr(self, "outreach_contact_file_input"):
            return
        current_text = self.outreach_contact_file_input.text().strip()
        if current_text:
            return
        summary: SummarySnapshotDict = self.summary_snapshot or build_source_summary(
            self.current_source()
        ).as_dict()
        files = summary.get("files", {}) if isinstance(summary, dict) else {}
        final_file = str(files.get("final_output_file", "")).strip()
        if final_file:
            self.outreach_contact_file_input.setText(final_file)

    def _build_outreach_config(self, force_send: bool = False) -> OutreachRunConfig:
        return OutreachRunConfig(
            contact_file=self.outreach_contact_file_input.text().strip(),
            campaign_id=self.outreach_campaign_id_input.text().strip(),
            subject_a=self.outreach_subject_a_input.text().strip(),
            subject_b=self.outreach_subject_b_input.text().strip(),
            body=self.outreach_body_input.toPlainText().strip(),
            company_name=self.outreach_company_input.text().strip(),
            physical_address=self.outreach_address_input.text().strip(),
            unsubscribe_url=self.outreach_unsubscribe_input.text().strip(),
            sender_name=self.outreach_sender_name_input.text().strip(),
            dry_run=self.outreach_dry_run_check.isChecked() and not force_send,
            confirm_permission=self.outreach_permission_check.isChecked(),
            session_limit=safe_int(self.outreach_session_limit_input.text()) or 25,
            min_delay_seconds=self._safe_float(self.outreach_min_delay_input.text(), 60.0),
            max_delay_seconds=self._safe_float(self.outreach_max_delay_input.text(), 180.0),
        )

    def _safe_float(self, raw_value: str, default: float) -> float:
        try:
            value = float((raw_value or "").strip())
        except ValueError:
            return default
        return value if value >= 0 else default

    def _on_browse_outreach_contacts(self) -> None:
        start_dir = str(PROJECT_ROOT / "final")
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select Contacts CSV",
            start_dir,
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.outreach_contact_file_input.setText(path)

    def _on_analyze_outreach_click(self) -> None:
        config = self._build_outreach_config()
        if not config.contact_file:
            QMessageBox.information(self, "Missing Contacts", "Please select a contacts CSV.")
            return
        try:
            plan = self.service.analyze_outreach(config)
        except (OSError, ValueError, csv.Error) as exc:
            QMessageBox.critical(self, "Analyze Failed", str(exc))
            return
        self.outreach_report_console.setPlainText(
            self._format_outreach_plan(plan.summary, plan.decisions)
        )

    def _on_send_outreach_click(self) -> None:
        config = self._build_outreach_config()
        if not config.contact_file:
            QMessageBox.information(self, "Missing Contacts", "Please select a contacts CSV.")
            return
        if not config.dry_run:
            response = QMessageBox.question(
                self,
                "Start Outreach",
                (
                    "This will send only eligible contacts and block invalid, duplicate, "
                    "suppressed, high-risk, or unconfirmed contacts. Continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        if not self.service.start_outreach(config):
            QMessageBox.warning(
                self,
                "Could Not Start",
                "Outreach may be blocked by contact file validation or another running task.",
            )
            return
        self.outreach_report_console.setPlainText("Outreach task started. Watch the activity feed.")

    def _append_outreach_report(self, payload: dict[str, Any]) -> None:
        summary = payload.get("summary", {})
        decisions = payload.get("decisions", [])
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(decisions, list):
            decisions = []
        report = self._format_outreach_summary(summary, decisions)
        if payload.get("error"):
            report = f"ERROR: {payload.get('error')}\n\n{report}"
        self.outreach_report_console.setPlainText(report)

    def _format_outreach_plan(self, summary: dict[str, int], decisions: Any) -> str:
        decision_rows = [decision.__dict__ for decision in decisions]
        return self._format_outreach_summary(summary, decision_rows)

    def _format_outreach_summary(self, summary: dict[str, int], decisions: list[Any]) -> str:
        lines = [
            "OUTREACH AUDIT",
            "-" * 40,
            f"Total: {summary.get('total', 0)}",
            f"Sent: {summary.get('sent', 0)}",
            f"Dry run ready: {summary.get('dry_run', 0)}",
            f"Queued: {summary.get('queued', 0)}",
            f"Missing permission: {summary.get('missing_permission', 0)}",
            f"Suppressed: {summary.get('suppressed', 0)}",
            f"Already sent: {summary.get('already_sent', 0)}",
            f"Duplicate in file: {summary.get('duplicate_input', 0)}",
            f"Invalid: {summary.get('invalid', 0)}",
            f"Risk blocked: {summary.get('risk_blocked', 0)}",
            f"Compliance blocked: {summary.get('compliance_blocked', 0)}",
            f"Failed: {summary.get('failed', 0)}",
            f"Session limit: {summary.get('session_limit', 0)}",
            "-" * 40,
            "RECIPIENTS:",
        ]
        for row in decisions[:200]:
            if not isinstance(row, dict):
                continue
            email = row.get("email", "")
            status = row.get("status", "")
            reason = row.get("reason", "")
            risk = row.get("risk_score", "")
            lines.append(f"{email} | {status} | risk={risk} | {reason}")
        if len(decisions) > 200:
            lines.append(f"... {len(decisions) - 200} more rows")
        return "\n".join(lines)

    def _on_start_click(self) -> None:
        config = self._build_run_config()
        if not config.url:
            QMessageBox.information(self, "Missing URL", "Please enter a target search URL.")
            return

        if self.service.start_run(config):
            self.summary_snapshot = {}  # Reset to force refresh
            self.log_console.clear()
        else:
            state = self.service.get_state()
            if not state.get("busy"):
                QMessageBox.warning(
                    self,
                    "Could Not Start",
                    "Another task may already be running. Check the activity feed.",
                )

    def _on_stop_click(self) -> None:
        self.service.stop_run()

    def _on_pause_click(self) -> None:
        self.service.pause_run()

    def _on_resume_click(self) -> None:
        self.service.resume_run()

    def _on_restart_click(self) -> None:
        config = self._build_run_config()
        if not config.url:
            QMessageBox.information(self, "Missing URL", "Please enter a target search URL.")
            return
        if not self.service.restart_run(config):
            QMessageBox.warning(
                self,
                "Could Not Restart",
                "Restart is only available for scraping.",
            )

    def _on_export_click(self) -> None:
        quality_filter = ("high",) if self.email_only_check.isChecked() else ("high", "medium")
        if not self.service.start_export(self.current_source(), quality_filter):
            QMessageBox.warning(
                self,
                "Export Blocked",
                "Another task may already be running.",
            )

    def _on_open_directory(self) -> None:
        summary: SummarySnapshotDict = self.summary_snapshot or {}
        files = summary_file_paths(summary)
        if not files:
            QMessageBox.information(self, "No Files", "No output files found to browse.")
            return

        path = files[0]
        try:
            self.service.open_system_path(str(Path(path).resolve().parent))
        except (FileNotFoundError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _on_source_change(self, *_args: Any) -> None:
        if not self.service.get_state().get("busy"):
            self.runtime_snapshot = None
        self.summary_snapshot = build_source_summary(self.current_source()).as_dict()
        self._populate_output_options()
        if hasattr(self, "outreach_contact_file_input"):
            self.outreach_contact_file_input.clear()
            self._seed_outreach_contact_file()
        self._refresh_dashboard()

    def current_source(self) -> str:
        """Return the currently selected scraper source."""
        return "bbb" if self.source_combo.currentText().lower() == "bbb" else "houzz"

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._ui_ready:
            self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        if not hasattr(self, "dashboard_page"):
            return

        main_width = self.dashboard_page.width()
        self._relayout_metrics(self._metric_column_count(main_width))

    def _metric_column_count(self, _available_width: int) -> int:
        return 3

    def _relayout_metrics(self, columns: int) -> None:
        if not self.metric_cards:
            for key in METRIC_ORDER:
                accent = COLORS.get(key, "#3b82f6")
                self.metric_cards[key] = MetricCard(key.replace("_", " ").title(), accent)

        # Only relayout if needed
        if self._current_cols == columns:
            return

        # Clear grid
        while self.metric_grid.count() > 0:
            item = self.metric_grid.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.setParent(None)

        for i, key in enumerate(METRIC_ORDER):
            row = i // columns
            col = i % columns
            card = self.metric_cards[key]
            self.metric_grid.addWidget(card, row, col)

        self._current_cols = columns

    def _seed_defaults(self) -> None:
        self.log_console.clear()
        self.summary_snapshot = build_source_summary(self.current_source()).as_dict()
        self._seed_outreach_contact_file()

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        level, clean_message = self._format_log_message(message)
        self.log_console.appendPlainText(f"{timestamp}  {level:<7} {clean_message}")
        self.log_console.verticalScrollBar().setValue(
            self.log_console.verticalScrollBar().maximum()
        )

    def _format_log_message(self, message: str) -> tuple[str, str]:
        clean_message = (message or "").strip()
        markers = (
            ("[ERROR]", "ERROR"),
            ("[SYSTEM]", "SYSTEM"),
            ("[DONE]", "DONE"),
            ("[retry]", "RETRY"),
            ("[!]", "WARN"),
            ("[*]", "INFO"),
        )
        for marker, level in markers:
            if clean_message.startswith(marker):
                return level, clean_message[len(marker) :].strip()
        return "INFO", clean_message

    def closeEvent(self, event) -> None:
        service_state = self.service.get_state()
        if service_state.get("busy"):
            response = QMessageBox.question(
                self,
                "Close Dashboard",
                (
                    "A background task is still running. Closing the window may interrupt "
                    "the process. Close anyway?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()


def main() -> int:
    """Launch the PySide6 dashboard."""
    existing_app = QApplication.instance()
    app = QApplication(sys.argv) if existing_app is None else cast(QApplication, existing_app)
    app.setStyle("Fusion")
    window = QtDashboardWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
