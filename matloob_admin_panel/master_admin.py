"""
ADMIN BILLING & ACCESS CONTROL (PRIVATE)

Standalone admin dashboard for approving, blocking, and resuming licensed users.
Keep this file out of the user-facing EXE build.
"""

import importlib
import os
import sys
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Add parent dir to path for imports when the admin file is run directly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
mongo_module = importlib.import_module("scraper.storage.mongodb_storage")
db_manager = mongo_module.db_manager
ACCESS_APPROVED = mongo_module.ACCESS_APPROVED
ACCESS_BLOCKED = mongo_module.ACCESS_BLOCKED
ACCESS_PENDING = mongo_module.ACCESS_PENDING


class AdminBillingApp(QMainWindow):
    """Private admin app for user approval, blocking, and billing review."""

    COLUMNS = (
        "Computer",
        "Device ID",
        "Status",
        "Emails",
        "Bill PKR",
        "Sessions",
        "Last Active",
        "Actions",
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MATLOOB - Master Admin Access Controller")
        self.setMinimumSize(1200, 720)
        self._rows: list[dict[str, Any]] = []

        self.setStyleSheet(
            """
            QMainWindow { background-color: #0f172a; }
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel#Title { font-size: 24px; font-weight: bold; color: #38bdf8; }
            QLabel#Muted { color: #94a3b8; }
            QTableWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                gridline-color: #334155;
                selection-background-color: #2563eb;
            }
            QHeaderView::section {
                background-color: #111827;
                color: #e5e7eb;
                border: 0;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton#ApproveButton { background-color: #10b981; }
            QPushButton#BlockButton { background-color: #ef4444; }
            QPushButton#PendingButton { background-color: #f59e0b; }
            QPushButton#ResumeButton { background-color: #22c55e; }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Master Access Control Dashboard")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.notice_label = QLabel(
            "Only approved users can scrape or export. Pending users appear first."
        )
        self.notice_label.setObjectName("Muted")
        layout.addWidget(self.notice_label)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("Muted")
        footer.addWidget(self.summary_label, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_stats)
        footer.addWidget(refresh_btn)
        layout.addLayout(footer)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_stats)
        self.refresh_timer.start(15000)

        self.refresh_stats()

    def refresh_stats(self):
        if not db_manager.connect() or db_manager.db is None:
            self.table.setRowCount(0)
            self.notice_label.setText("MongoDB is not reachable. Check internet/DNS/settings.")
            self.summary_label.setText("")
            return

        self._rows = db_manager.get_admin_dashboard_stats()
        self.table.setRowCount(len(self._rows))

        pending_count = 0
        blocked_count = 0
        total_bill = 0.0

        for row_index, row in enumerate(self._rows):
            status = str(row.get("access_status") or "pending").upper()
            pending_count += int(status == "PENDING")
            blocked_count += int(status == "BLOCKED")
            total_bill += float(row.get("bill_pkr") or 0.0)

            values = [
                row.get("computer_name") or row.get("_id") or "Unknown",
                row.get("license_key") or "",
                status,
                str(int(row.get("total_emails") or 0)),
                f"{float(row.get('bill_pkr') or 0.0):.2f}",
                str(int(row.get("total_sessions") or 0)),
                self._format_time(row.get("last_active") or row.get("last_request_at")),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row_index, col_index, item)

            self.table.setCellWidget(row_index, 7, self._build_action_widget(row))

        self.notice_label.setText(
            "Only approved users can scrape or export. Pending users appear first."
        )
        self.summary_label.setText(
            f"Users: {len(self._rows)} | Pending: {pending_count} | "
            f"Blocked: {blocked_count} | Total bill: {total_bill:.2f} PKR"
        )

    def _build_action_widget(self, row):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        approve_btn = QPushButton("Approve")
        approve_btn.setObjectName("ApproveButton")
        approve_btn.clicked.connect(partial(self._set_status, row, ACCESS_APPROVED))
        layout.addWidget(approve_btn)

        block_btn = QPushButton("Block")
        block_btn.setObjectName("BlockButton")
        block_btn.clicked.connect(partial(self._set_status, row, ACCESS_BLOCKED))
        layout.addWidget(block_btn)

        pending_btn = QPushButton("Pending")
        pending_btn.setObjectName("PendingButton")
        pending_btn.clicked.connect(partial(self._set_status, row, ACCESS_PENDING))
        layout.addWidget(pending_btn)

        resume_btn = QPushButton("Resume")
        resume_btn.setObjectName("ResumeButton")
        resume_btn.clicked.connect(partial(self._set_status, row, ACCESS_APPROVED))
        layout.addWidget(resume_btn)

        layout.addStretch(1)
        return widget

    def _set_status(self, row, status):
        computer_name = str(row.get("computer_name") or row.get("_id") or "").strip()
        license_key = str(row.get("license_key") or "").strip()
        if not computer_name or not license_key:
            QMessageBox.warning(self, "Missing User", "Computer name or device ID is missing.")
            return

        if db_manager.set_user_access_status(computer_name, license_key, status):
            QMessageBox.information(
                self,
                "Updated",
                f"{computer_name} / {license_key} is now {status.upper()}.",
            )
            self.refresh_stats()
        else:
            QMessageBox.critical(
                self,
                "Update Failed",
                "Could not update this user. Check MongoDB connection.",
            )

    def _format_time(self, value):
        if not value:
            return "Never"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M")
        return str(value)


def main():
    app = QApplication(sys.argv)
    window = AdminBillingApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
