"""PySide6 dashboard window for managing scraper runs and output files."""

# pylint: disable=attribute-defined-outside-init,invalid-name

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
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

from desktop_app.models import ScraperRunConfig
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

        # Page 2: Billing
        self.billing_page = self._build_billing_page()
        self.content_stack.addWidget(self.billing_page)

        # Page 3: Admin
        self.admin_page = self._build_admin_page()
        self.content_stack.addWidget(self.admin_page)

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
        self.nav_billing = self._nav_button(
            "My Billing", QStyle.StandardPixmap.SP_FileDialogDetailedView, "billing"
        )

        self.nav_group = QButtonGroup(self)
        self.nav_group.addButton(self.nav_houzz)
        self.nav_group.addButton(self.nav_bbb)
        self.nav_group.addButton(self.nav_data)
        self.nav_group.addButton(self.nav_billing)
        self.nav_houzz.setChecked(True)

        layout.addWidget(self.nav_houzz)
        layout.addWidget(self.nav_bbb)
        layout.addWidget(self.nav_data)
        layout.addWidget(self.nav_billing)
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

        # Billing Quick View
        self.sidebar_billing_label = QLabel("Est. Bill: 0.00 PKR")
        self.sidebar_billing_label.setObjectName("Muted")
        self.sidebar_billing_label.setStyleSheet("font-weight: bold; color: #34b978;")
        layout.addWidget(self.sidebar_billing_label)
        layout.addSpacing(5)

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
        elif view == "billing":
            self.nav_billing.setChecked(True)
            self.content_stack.setCurrentIndex(2)

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

    def _build_billing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        header = QLabel("My Billing & Usage")
        header.setObjectName("PageTitle")
        layout.addWidget(header)

        self.billing_card_container = QWidget()
        self.billing_grid = QGridLayout(self.billing_card_container)
        
        self.bill_emails_card = MetricCard("Total Emails", "#34b978")
        self.bill_pkr_card = MetricCard("Bill (PKR)", "#d7a13f")
        self.bill_usd_card = MetricCard("Bill (USD)", "#6aa6ff")
        self.bill_sessions_card = MetricCard("Total Sessions", "#e16666")

        self.billing_grid.addWidget(self.bill_emails_card, 0, 0)
        self.billing_grid.addWidget(self.bill_pkr_card, 0, 1)
        self.billing_grid.addWidget(self.bill_usd_card, 1, 0)
        self.billing_grid.addWidget(self.bill_sessions_card, 1, 1)
        
        self.billing_card_container.setMinimumHeight(160)
        layout.addWidget(self.billing_card_container)
        
        details = QLabel("Note: Billing is calculated at 0.5 PKR per email fetched.")
        details.setObjectName("Muted")
        layout.addWidget(details)
        layout.addStretch()

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

        btn_layout.addWidget(self.start_btn, 2)
        btn_layout.addWidget(self.stop_btn, 1)
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
        self._update_billing_ui()

    def _update_billing_ui(self) -> None:
        bill = self.service.get_billing_info()
        self.sidebar_billing_label.setText(f"Est. Bill: {bill['pkr']:.2f} PKR")
        
        if self.content_stack.currentIndex() == 2:  # Billing page
            self.bill_emails_card.set_metric(bill['emails'])
            self.bill_pkr_card.set_metric(f"{bill['pkr']:.2f}")
            self.bill_usd_card.set_metric(f"${bill['usd']:.2f}")
            self.bill_sessions_card.set_metric(bill['sessions'])
        
        if self.content_stack.currentIndex() == 3:  # Admin page
            self._refresh_admin_stats()

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

    def _apply_runtime(self, runtime: RuntimeSnapshotDict | None) -> None:
        if not runtime:
            self.run_progress_note.setText("Engine is idle. Ready for new extraction.")
            self.success_rate_note.setText("Configure targets in the sidebar and press Start.")
            return

        self.run_progress_note.setText(build_progress_note(runtime))

        success_rate = runtime.get("success_rate", 0.0)
        if success_rate > 0:
            self.success_rate_note.setText(
                f"Extracting at {round(success_rate * 100)}% efficiency. "
                f"{runtime.get('emails_total', 0)} leads found so far."
            )

    def _apply_summary(self, summary: SummarySnapshotDict) -> None:
        # Update values
        mapping = {
            "checked": summary.get("tracked_profiles", 0),
            "active": summary.get("active", 0),
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
            f"ACTIVE RUNS: {summary.get('active', 0)}",
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
        if is_busy:
            self.status_dot.setText("●  Extracting...")
            self.status_dot.setObjectName("StatusBusy")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        else:
            self.status_dot.setText("●  Idle")
            self.status_dot.setObjectName("StatusIdle")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        self.status_dot.setStyle(self.status_dot.style())

    def _on_start_click(self) -> None:
        out_filename = self.output_filename_input.currentText().strip()
        if out_filename == "Custom":
            out_filename = self.custom_filename_input.text().strip()
            if not out_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_filename = f"{self.current_source().lower()}_custom_{timestamp}.csv"
            elif not out_filename.lower().endswith(".csv"):
                out_filename += ".csv"

        config = ScraperRunConfig(
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
            out_filename=out_filename,
        )
        if self.service.start_run(config):
            self.summary_snapshot = {}  # Reset to force refresh
            self.log_console.clear()

    def _on_stop_click(self) -> None:
        self.service.stop_run()

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
        pass

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
