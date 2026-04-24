"""PySide6 dashboard window for managing scraper runs and output files."""

# pylint: disable=attribute-defined-outside-init,invalid-name,no-name-in-module,too-few-public-methods

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from desktop_app.models import ScraperRunConfig
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
)


class MetricCard(QFrame):
    """Small dashboard card for a headline metric."""

    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.setMinimumHeight(82)
        self.setMaximumHeight(92)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(10)

        marker = QFrame()
        marker.setFixedWidth(4)
        marker.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        layout.addWidget(marker)

        content = QVBoxLayout()
        content.setContentsMargins(0, 8, 0, 8)
        content.setSpacing(0)
        layout.addLayout(content, 1)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricLabel")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("MetricValue")
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("MetricMeta")
        self.meta_label.setWordWrap(True)

        content.addWidget(self.title_label)
        content.addWidget(self.value_label)
        content.addWidget(self.meta_label)
        content.addStretch(1)

    def set_metric(self, value: Any, meta: str = "") -> None:
        """Update the visible metric value and supporting text."""
        self.value_label.setText(str(value))
        self.meta_label.setText(meta)


class Section(QFrame):
    """Reusable bordered section with title and optional subtitle."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Panel")

        self.body_layout = QVBoxLayout(self)
        self.body_layout.setContentsMargins(16, 14, 16, 16)
        self.body_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.body_layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Muted")
            subtitle_label.setWordWrap(True)
            self.body_layout.addWidget(subtitle_label)


class QtDashboardWindow(QMainWindow):
    """Professional PySide6 dashboard for the scraper service."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Matloob Email Operations")
        self.resize(1480, 920)
        self.setMinimumSize(1280, 820)

        self.service = ScraperDashboardService()
        self.runtime_snapshot: RuntimeSnapshotDict | None = None
        self.summary_snapshot: SummarySnapshotDict = build_source_summary("houzz").as_dict()
        self.file_targets: dict[str, str] = {}

        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self._seed_defaults()
        self._append_log("Dashboard ready.")
        self._apply_summary(self.summary_snapshot)
        self._refresh_dashboard()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_events)
        self.poll_timer.start(200)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_main_area(), 1)

    def _build_sidebar(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFixedWidth(330)
        scroll.setWidgetResizable(True)

        panel = QFrame()
        panel.setObjectName("Panel")
        scroll.setWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Matloob")
        title.setObjectName("SidebarTitle")
        subtitle = QLabel("Email operations dashboard")
        subtitle.setObjectName("Muted")

        self.sidebar_status = QLabel("Idle mode")
        self.sidebar_status.setObjectName("Badge")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.sidebar_status)
        layout.addSpacing(6)

        self.url_input = self._line_edit("Houzz or BBB search URL")
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Houzz", "BBB"])
        self.source_combo.currentTextChanged.connect(self._on_source_change)

        self.max_pages_input = self._line_edit("Optional")
        self.max_profiles_input = self._line_edit("Optional")
        self.country_input = self._line_edit("Auto-detect if blank")

        self._add_labeled(layout, "Search URL", self.url_input)
        self._add_labeled(layout, "Source", self.source_combo)
        self._add_two_column_inputs(layout)
        self._add_labeled(layout, "Fallback Country", self.country_input)

        layout.addWidget(self._build_options_panel())
        layout.addStretch(1)
        return scroll

    def _build_main_area(self) -> QWidget:
        main_area = QWidget()
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_metrics_grid())
        layout.addWidget(self._build_workspace_row(), 1)
        return main_area

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Panel")
        layout = QGridLayout(header)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(6)

        title = QLabel("Operations Dashboard")
        title.setObjectName("Title")
        subtitle = QLabel("Houzz + BBB email acquisition")
        subtitle.setObjectName("Muted")

        self.status_badge = QLabel("Idle")
        self.status_badge.setObjectName("Badge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hero_summary = QLabel("")
        self.hero_summary.setWordWrap(True)
        self.hero_hint = QLabel("")
        self.hero_hint.setObjectName("Muted")
        self.hero_hint.setWordWrap(True)

        layout.addWidget(title, 0, 0)
        layout.addWidget(subtitle, 1, 0)
        layout.addWidget(self.status_badge, 0, 1, 2, 1, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.hero_summary, 2, 0, 1, 2)
        layout.addWidget(self.hero_hint, 3, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        return header

    def _build_metrics_grid(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setMaximumHeight(98)
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        self.metric_cards = {
            "checked": MetricCard("Checked Profiles", COLORS["accent"]),
            "active": MetricCard("Active Workers", COLORS["info"]),
            "processed": MetricCard("Processed", COLORS["success"]),
            "no_email": MetricCard("No Email", COLORS["warning"]),
            "failed": MetricCard("Failed", COLORS["danger"]),
            "emails": MetricCard("Emails Saved", COLORS["accent"]),
        }

        positions = {
            "checked": (0, 0),
            "active": (0, 1),
            "processed": (0, 2),
            "no_email": (0, 3),
            "failed": (0, 4),
            "emails": (0, 5),
        }
        for key, card in self.metric_cards.items():
            row, column = positions[key]
            grid.addWidget(card, row, column)

        for column in range(6):
            grid.setColumnStretch(column, 1)
        return wrapper

    def _build_workspace_row(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_progress_panel())
        splitter.addWidget(self._build_activity_panel())
        splitter.addWidget(self._build_data_panel())
        splitter.setSizes([320, 500, 320])
        splitter.setChildrenCollapsible(False)
        return splitter

    def _build_progress_panel(self) -> Section:
        section = Section("Run Health", "Live run and source health")
        section.setMinimumWidth(300)
        section.setMaximumWidth(360)
        section.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.run_progress_label = QLabel("Run Progress")
        self.run_progress_bar = QProgressBar()
        self.run_progress_bar.setRange(0, 100)
        self.run_progress_bar.setValue(0)
        self.run_progress_note = QLabel("No active scrape session.")
        self.run_progress_note.setObjectName("Muted")
        self.run_progress_note.setWordWrap(True)

        self.success_rate_label = QLabel("Source Success Rate")
        self.success_rate_bar = QProgressBar()
        self.success_rate_bar.setRange(0, 100)
        self.success_rate_bar.setValue(0)
        self.success_rate_note = QLabel("Waiting for source totals.")
        self.success_rate_note.setObjectName("Muted")
        self.success_rate_note.setWordWrap(True)

        section.body_layout.addWidget(self.run_progress_label)
        section.body_layout.addWidget(self.run_progress_bar)
        section.body_layout.addWidget(self.run_progress_note)
        section.body_layout.addSpacing(4)
        section.body_layout.addWidget(self.success_rate_label)
        section.body_layout.addWidget(self.success_rate_bar)
        section.body_layout.addWidget(self.success_rate_note)
        section.body_layout.addSpacing(10)
        self._add_quality_controls(section.body_layout)
        section.body_layout.addSpacing(6)
        self._add_action_controls(section.body_layout)
        return section

    def _build_bottom_split(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_activity_panel())
        splitter.addWidget(self._build_data_panel())
        splitter.setSizes([720, 480])
        return splitter

    def _build_activity_panel(self) -> Section:
        section = Section("Activity Feed", "Scraper events")
        section.setMinimumWidth(340)
        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        section.body_layout.addWidget(self.log_console, 1)
        return section

    def _build_data_panel(self) -> Section:
        section = Section("Data Center", "Source totals and files")
        section.setMinimumWidth(280)
        section.setMaximumWidth(380)
        self.data_console = QPlainTextEdit()
        self.data_console.setObjectName("DataConsole")
        self.data_console.setReadOnly(True)
        self.data_console.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        section.body_layout.addWidget(self.data_console, 1)

        buttons = QGridLayout()
        buttons.setSpacing(8)
        section.body_layout.addLayout(buttons)

        self.open_master_button = self._file_button(
            "Master CSV", lambda: self._open_target("output_file")
        )
        self.open_detail_button = self._file_button(
            "Detail CSV", lambda: self._open_target("detail_output_file")
        )
        self.open_status_button = self._file_button(
            "Status CSV", lambda: self._open_target("status_file")
        )
        self.open_final_button = self._file_button("Final Folder", self._open_final_folder)
        self.open_fail_button = self._file_button(
            "Fail Log", lambda: self._open_target("fail_log_file")
        )
        self.open_output_button = self._file_button("Output Folder", self._open_output_folder)
        self.open_excel_button = self._file_button(
            "Excel Export", lambda: self._open_target("excel_export_file")
        )
        self.open_duplicates_button = self._file_button(
            "Duplicates", lambda: self._open_target("duplicate_report_file")
        )

        for index, button in enumerate(
            [
                self.open_master_button,
                self.open_detail_button,
                self.open_status_button,
                self.open_final_button,
                self.open_fail_button,
                self.open_output_button,
                self.open_excel_button,
                self.open_duplicates_button,
            ]
        ):
            buttons.addWidget(button, index // 2, index % 2)
        return section

    def _build_options_panel(self) -> Section:
        section = Section("Run Options")
        self.headless_check = QCheckBox("Headless browser")
        self.skip_facebook_check = QCheckBox("Skip Facebook")
        self.skip_google_check = QCheckBox("Skip Google fallback")
        self.retry_no_email_check = QCheckBox("Retry no_email")
        self.auto_export_check = QCheckBox("Auto export")
        self.auto_export_check.setChecked(True)
        self.fresh_start_check = QCheckBox("Fresh start")

        for checkbox in (
            self.headless_check,
            self.skip_facebook_check,
            self.skip_google_check,
            self.retry_no_email_check,
            self.auto_export_check,
            self.fresh_start_check,
        ):
            section.body_layout.addWidget(checkbox)
        return section

    def _add_quality_controls(self, layout: QVBoxLayout) -> None:
        label = QLabel("Quality Filter")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(12)
        layout.addLayout(row)

        self.high_quality_check = QCheckBox("High")
        self.medium_quality_check = QCheckBox("Medium")
        self.low_quality_check = QCheckBox("Low")
        self.high_quality_check.setChecked(True)
        self.medium_quality_check.setChecked(True)

        for checkbox in (
            self.high_quality_check,
            self.medium_quality_check,
            self.low_quality_check,
        ):
            row.addWidget(checkbox)
        row.addStretch(1)

    def _add_action_controls(self, layout: QVBoxLayout) -> None:
        label = QLabel("Actions")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(8)
        layout.addLayout(grid)

        self.start_button = self._button(
            "Start",
            self._start_run,
            "PrimaryButton",
            QStyle.StandardPixmap.SP_MediaPlay,
        )
        self.pause_button = self._button(
            "Pause",
            self._pause_run,
            "WarningButton",
            QStyle.StandardPixmap.SP_MediaPause,
        )
        self.resume_button = self._button(
            "Resume",
            self._resume_run,
            icon=QStyle.StandardPixmap.SP_MediaPlay,
        )
        self.stop_button = self._button(
            "Stop",
            self._stop_run,
            "DangerButton",
            QStyle.StandardPixmap.SP_MediaStop,
        )
        self.restart_button = self._button(
            "Restart",
            self._restart_run,
            icon=QStyle.StandardPixmap.SP_BrowserReload,
        )
        self.export_button = self._button(
            "Export",
            self._export_only,
            icon=QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self.refresh_button = self._button(
            "Refresh",
            self._refresh_summary_only,
            icon=QStyle.StandardPixmap.SP_BrowserReload,
        )

        grid.addWidget(self.start_button, 0, 0)
        grid.addWidget(self.pause_button, 0, 1)
        grid.addWidget(self.resume_button, 1, 0)
        grid.addWidget(self.stop_button, 1, 1)
        grid.addWidget(self.restart_button, 2, 0)
        grid.addWidget(self.export_button, 2, 1)
        grid.addWidget(self.refresh_button, 3, 0, 1, 2)

    def _add_labeled(self, layout: QVBoxLayout, label_text: str, widget: QWidget) -> None:
        label = QLabel(label_text)
        label.setObjectName("Muted")
        layout.addWidget(label)
        layout.addWidget(widget)

    def _add_two_column_inputs(self, layout: QVBoxLayout) -> None:
        label = QLabel("Run Limits")
        label.setObjectName("Muted")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._input_group("Max pages", self.max_pages_input))
        row.addWidget(self._input_group("Max profiles", self.max_profiles_input))
        layout.addLayout(row)

    def _input_group(self, label_text: str, widget: QWidget) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("Muted")
        layout.addWidget(label)
        layout.addWidget(widget)
        return group

    def _line_edit(self, placeholder: str) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        return line_edit

    def _button(
        self,
        text: str,
        command: Any,
        object_name: str = "",
        icon: QStyle.StandardPixmap | None = None,
    ) -> QPushButton:
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        if icon is not None:
            button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(text)
        button.clicked.connect(command)
        button.setMinimumHeight(38)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button

    def _file_button(self, text: str, command: Any) -> QPushButton:
        return self._button(text, command, icon=QStyle.StandardPixmap.SP_DialogOpenButton)

    def _seed_defaults(self) -> None:
        self.country_input.setText("USA")

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
            ("[+]", "PROFILE"),
            ("[-]", "INFO"),
            ("[~]", "RETRY"),
        )
        for marker, level in markers:
            if clean_message.startswith(marker):
                return level, clean_message.removeprefix(marker).strip()
        return "INFO", clean_message

    def _poll_events(self) -> None:
        for event in self.service.drain_events():
            event_type = event["type"]
            payload = event["payload"]

            if event_type == "log":
                self._append_log(payload.get("message", ""))
            elif event_type == "runtime":
                self.runtime_snapshot = payload.get("snapshot")
            elif event_type == "summary":
                self.summary_snapshot = payload.get("summary")
            elif event_type == "export":
                result = payload.get("result", {})
                self._append_log(
                    "[SYSTEM] Export summary: "
                    f"{result.get('count', 0)} emails written to "
                    f"{result.get('final_output_file', '')}"
                )
                self._append_log(
                    "[SYSTEM] Excel export: "
                    f"{result.get('excel_export_file', '')}; "
                    f"duplicates={result.get('duplicate_count', 0)}"
                )

        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        service_state = self.service.get_state()
        runtime = self._current_runtime(service_state)
        summary = self.summary_snapshot or build_source_summary(self.current_source()).as_dict()

        self._apply_summary(summary)
        self._apply_runtime(runtime, service_state)
        self._refresh_buttons(service_state, runtime)

    def _current_runtime(
        self,
        service_state: dict[str, Any],
    ) -> RuntimeSnapshotDict | None:
        runtime = service_state.get("runtime") or self.runtime_snapshot
        if runtime and runtime.get("source") == self.current_source():
            return runtime
        return None

    def _apply_summary(self, summary: SummarySnapshotDict) -> None:
        self.file_targets = dict(summary.get("files", {}))
        success_rate = float(summary.get("success_rate", 0.0) or 0.0)
        self.success_rate_bar.setValue(round(success_rate * 100))
        self.success_rate_note.setText(
            f"{summary.get('processed_count', 0)} processed from "
            f"{summary.get('tracked_profiles', 0)} tracked profiles for "
            f"{format_source(summary.get('source', 'houzz'))}."
        )

        data_lines = [
            "SOURCE SNAPSHOT",
            f"{'Source':<22}{format_source(summary.get('source', 'houzz'))}",
            f"{'Master emails':<22}{summary.get('master_count', 0)}",
            f"{'Detail rows':<22}{summary.get('detail_count', 0)}",
            f"{'Final exports':<22}{summary.get('final_count', 0)}",
            f"{'Duplicate emails':<22}{summary.get('duplicate_count', 0)}",
            f"{'Tracked profiles':<22}{summary.get('tracked_profiles', 0)}",
            f"{'Processed':<22}{summary.get('processed_count', 0)}",
            f"{'No email':<22}{summary.get('no_email_count', 0)}",
            f"{'Failed':<22}{summary.get('failed_count', 0)}",
            "",
            "QUALITY MIX",
            f"{'High':<22}{summary.get('high_quality_count', 0)}",
            f"{'Medium':<22}{summary.get('medium_quality_count', 0)}",
            f"{'Low':<22}{summary.get('low_quality_count', 0)}",
            "",
            f"{'Last update':<22}{format_timestamp(summary.get('last_updated', ''))}",
            "",
            "FILES",
            f"{'Master CSV':<22}{summary.get('files', {}).get('output_file', '')}",
            f"{'Detail CSV':<22}{summary.get('files', {}).get('detail_output_file', '')}",
            f"{'Status CSV':<22}{summary.get('files', {}).get('status_file', '')}",
            f"{'Final CSV':<22}{summary.get('files', {}).get('final_output_file', '')}",
            f"{'Excel':<22}{summary.get('files', {}).get('excel_export_file', '')}",
            f"{'Duplicates':<22}{summary.get('files', {}).get('duplicate_report_file', '')}",
            f"{'Fail Log':<22}{summary.get('files', {}).get('fail_log_file', '')}",
        ]
        self.data_console.setPlainText("\n".join(data_lines))

    def _apply_runtime(
        self,
        runtime: RuntimeSnapshotDict | None,
        service_state: dict[str, Any],
    ) -> None:
        summary = self.summary_snapshot or {}
        mode = service_state.get("mode", "idle")

        if mode == "export" and runtime is None:
            self._apply_export_mode(summary)
            return

        if not runtime:
            self._apply_idle_mode(summary)
            return

        state = runtime.get("run_state", "idle")
        status_text = state.replace("_", " ").title()
        if service_state.get("restart_queued"):
            status_text += " | Restart queued"
        self._set_status(status_text, state)

        checked_total = runtime.get("checked_total", 0)
        progress_ratio = float(runtime.get("progress_ratio", 0.0) or 0.0)
        self.run_progress_bar.setValue(max(2, round(progress_ratio * 100)))
        self.run_progress_note.setText(build_progress_note(runtime))

        self.hero_summary.setText(
            f"{format_source(runtime.get('source', 'houzz'))} run is {state}. "
            f"Checked {checked_total} profiles, saved {runtime.get('master_saved', 0)} "
            f"unique emails, and discovered {runtime.get('profiles_discovered', 0)} "
            "profile links so far."
        )
        self.hero_hint.setText(
            f"Current page: {runtime.get('current_page', 0)} | "
            f"Active workers: {runtime.get('active_profiles', 0)} | "
            f"Last profile: {runtime.get('last_profile_url', 'n/a')}"
        )

        self.metric_cards["checked"].set_metric(
            checked_total,
            f"Attempted {runtime.get('profiles_attempted', 0)} | "
            f"Skipped {runtime.get('profiles_skipped', 0)}",
        )
        self.metric_cards["active"].set_metric(
            runtime.get("active_profiles", 0),
            f"Page {runtime.get('current_page', 0)} | "
            f"{runtime.get('profiles_discovered', 0)} discovered",
        )
        self.metric_cards["processed"].set_metric(
            runtime.get("processed", 0),
            f"Historical total {summary.get('processed_count', 0)}",
        )
        self.metric_cards["no_email"].set_metric(
            runtime.get("no_email", 0),
            f"Historical total {summary.get('no_email_count', 0)}",
        )
        self.metric_cards["failed"].set_metric(
            runtime.get("failed", 0),
            f"Historical total {summary.get('failed_count', 0)}",
        )
        self.metric_cards["emails"].set_metric(
            runtime.get("master_saved", 0),
            f"Final export {runtime.get('final_export_count', 0)} | "
            f"Detail rows {runtime.get('detail_saved', 0)}",
        )

    def _apply_export_mode(self, summary: SummarySnapshotDict) -> None:
        self._set_status("Exporting final files", "export")
        self.hero_summary.setText(
            f"{format_source(self.current_source())} export is running. "
            f"Current source already holds {summary.get('master_count', 0)} master emails."
        )
        self.hero_hint.setText(
            "Export uses the selected quality filter and rewrites the final output files."
        )
        self.run_progress_bar.setValue(0)
        self.run_progress_note.setText("Export job does not use crawl progress bars.")
        self._set_cards_from_summary(summary)

    def _apply_idle_mode(self, summary: SummarySnapshotDict) -> None:
        self._set_status("Idle mode", "idle")
        self.hero_summary.setText(
            f"{format_source(self.current_source())} is selected. "
            f"{summary.get('master_count', 0)} master emails and "
            f"{summary.get('tracked_profiles', 0)} tracked profiles are available."
        )
        self.hero_hint.setText(
            f"Last update: {format_timestamp(summary.get('last_updated', ''))} | "
            f"Quality mix: H {summary.get('high_quality_count', 0)} / "
            f"M {summary.get('medium_quality_count', 0)} / "
            f"L {summary.get('low_quality_count', 0)} | "
            f"Duplicates {summary.get('duplicate_count', 0)}"
        )
        self.run_progress_bar.setValue(0)
        self.run_progress_note.setText("No active scrape session.")
        self._set_cards_from_summary(summary)

    def _set_status(self, text: str, state: str) -> None:
        color = {
            "running": COLORS["accent"],
            "paused": COLORS["warning"],
            "stopping": COLORS["danger"],
            "completed": COLORS["success"],
            "stopped": COLORS["warning"],
            "failed": COLORS["danger"],
            "export": COLORS["info"],
        }.get(state, COLORS["field"])
        text_color = "#07110c" if state in {"running", "completed", "export"} else COLORS["text"]
        style = (
            f"background: {color}; color: {text_color}; border: 1px solid {color}; "
            "border-radius: 8px; padding: 6px 10px; font-weight: 700;"
        )
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(style)
        self.sidebar_status.setText(text)
        self.sidebar_status.setStyleSheet(style)

    def _set_cards_from_summary(self, summary: SummarySnapshotDict) -> None:
        self.metric_cards["checked"].set_metric(
            summary.get("tracked_profiles", 0),
            "Profiles already tracked in the status file",
        )
        self.metric_cards["active"].set_metric(0, "No live browser workers")
        self.metric_cards["processed"].set_metric(
            summary.get("processed_count", 0),
            "Source-level processed profiles",
        )
        self.metric_cards["no_email"].set_metric(
            summary.get("no_email_count", 0),
            "Profiles completed without an email",
        )
        self.metric_cards["failed"].set_metric(
            summary.get("failed_count", 0),
            "Profiles needing attention or retry",
        )
        self.metric_cards["emails"].set_metric(
            summary.get("master_count", 0),
            f"Final export holds {summary.get('final_count', 0)} emails",
        )

    def _refresh_buttons(
        self,
        service_state: dict[str, Any],
        runtime: RuntimeSnapshotDict | None,
    ) -> None:
        busy = service_state.get("busy", False)
        mode = service_state.get("mode", "idle")
        running = busy and mode == "scrape"
        paused = runtime and runtime.get("run_state") == "paused"
        stopping = runtime and runtime.get("run_state") == "stopping"

        self.start_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.pause_button.setEnabled(bool(running and not paused and not stopping))
        self.resume_button.setEnabled(bool(running and paused))
        self.stop_button.setEnabled(bool(running))
        self.restart_button.setEnabled(mode != "export")
        self.source_combo.setEnabled(not busy)

    def _gather_config(self, require_url: bool = True) -> ScraperRunConfig:
        url = self.url_input.text().strip()
        if require_url and not url:
            raise ValueError("Search URL is required.")
        source = self.current_source()
        if url:
            self._validate_search_url(url, source)

        max_pages = self._parse_optional_integer(self.max_pages_input.text().strip(), "Max pages")
        max_profiles = self._parse_optional_integer(
            self.max_profiles_input.text().strip(), "Max profiles"
        )
        quality_filter = tuple(
            key
            for key, checkbox in {
                "high": self.high_quality_check,
                "medium": self.medium_quality_check,
                "low": self.low_quality_check,
            }.items()
            if checkbox.isChecked()
        )
        if not quality_filter:
            raise ValueError("Select at least one quality level.")

        return ScraperRunConfig(
            url=url,
            source=source,
            max_pages=max_pages,
            max_profiles=max_profiles,
            headless=self.headless_check.isChecked(),
            skip_facebook=self.skip_facebook_check.isChecked(),
            skip_google_fallback=self.skip_google_check.isChecked(),
            retry_no_email=self.retry_no_email_check.isChecked(),
            country=self.country_input.text().strip(),
            auto_export_final=self.auto_export_check.isChecked(),
            quality_filter=quality_filter,
            fresh_start=self.fresh_start_check.isChecked(),
        )

    def _validate_search_url(self, url: str, source: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Search URL must start with http:// or https://.")

        hostname = (parsed.hostname or "").lower()
        if source == "bbb":
            if not (hostname == "bbb.org" or hostname.endswith(".bbb.org")):
                raise ValueError("Selected source is BBB, but the URL is not a bbb.org URL.")
            return

        if "houzz." not in hostname:
            raise ValueError("Selected source is Houzz, but the URL is not a Houzz URL.")

    def _parse_optional_integer(self, raw_value: str, field_name: str) -> int | None:
        if not raw_value:
            return None
        value = safe_int(raw_value)
        if value is None or value <= 0:
            raise ValueError(f"{field_name} must be a positive integer.")
        return value

    def _start_run(self) -> None:
        try:
            config = self._gather_config(require_url=True)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Settings", str(exc))
            return

        if self.service.start_run(config):
            self.runtime_snapshot = None
            self._append_log("[SYSTEM] Scrape run started from the dashboard.")
            return
        QMessageBox.warning(self, "Busy", "A background task is already running.")

    def _pause_run(self) -> None:
        if not self.service.pause_run():
            QMessageBox.warning(self, "Unavailable", "There is no active scrape run to pause.")

    def _resume_run(self) -> None:
        if not self.service.resume_run():
            QMessageBox.warning(self, "Unavailable", "There is no paused run to resume.")

    def _stop_run(self) -> None:
        if not self.service.stop_run():
            QMessageBox.warning(self, "Unavailable", "There is no active scrape run to stop.")

    def _restart_run(self) -> None:
        try:
            config = self._gather_config(require_url=True)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Settings", str(exc))
            return

        if not self.service.restart_run(config):
            QMessageBox.warning(
                self,
                "Busy",
                "Current background task is exporting. Wait for it to finish before restarting.",
            )

    def _export_only(self) -> None:
        try:
            config = self._gather_config(require_url=False)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Settings", str(exc))
            return

        if not self.service.start_export(config.source, config.quality_filter):
            QMessageBox.warning(self, "Busy", "A background task is already running.")

    def _refresh_summary_only(self) -> None:
        summary = self.service.refresh_summary(self.current_source())
        self.summary_snapshot = summary.as_dict()
        self._append_log("[SYSTEM] Source totals refreshed from disk.")

    def _open_target(self, key: str) -> None:
        path = self.file_targets.get(key)
        if not path:
            QMessageBox.warning(self, "Missing Path", "No path is available for this source.")
            return
        try:
            self.service.open_system_path(path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _open_output_folder(self) -> None:
        path = self.file_targets.get("detail_output_file")
        if not path:
            QMessageBox.warning(self, "Missing Path", "Output folder path is not available.")
            return
        self._open_folder_for(path)

    def _open_final_folder(self) -> None:
        path = self.file_targets.get("final_output_file")
        if not path:
            QMessageBox.warning(self, "Missing Path", "Final folder path is not available.")
            return
        self._open_folder_for(path)

    def _open_folder_for(self, path: str) -> None:
        try:
            self.service.open_system_path(str(Path(path).resolve().parent))
        except (FileNotFoundError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _on_source_change(self, *_args: Any) -> None:
        if not self.service.get_state().get("busy"):
            self.runtime_snapshot = None
        self.summary_snapshot = build_source_summary(self.current_source()).as_dict()
        self._refresh_dashboard()

    def current_source(self) -> str:
        """Return the currently selected scraper source."""
        return "bbb" if self.source_combo.currentText().lower() == "bbb" else "houzz"

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
    owns_app = existing_app is None
    app = QApplication(sys.argv) if existing_app is None else cast(QApplication, existing_app)
    app.setStyle("Fusion")
    window = QtDashboardWindow()
    window.show()
    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
