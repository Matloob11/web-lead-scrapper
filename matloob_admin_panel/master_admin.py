"""
ADMIN BILLING & ACCESS CONTROL (PRIVATE)
This script allows you to view bills AND block/unblock users remotely.
"""

import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QPlainTextEdit, QPushButton, QLabel, QHBoxLayout,
    QLineEdit, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QTimer

# Add parent dir to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.storage.mongodb_storage import db_manager

class AdminBillingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MATLOOB - Master Admin Access Controller")
        self.setMinimumSize(1000, 700)
        
        # Style
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', sans-serif; }
            QPlainTextEdit { 
                background-color: #1e293b; 
                border: 1px solid #334155; 
                border-radius: 8px; 
                padding: 10px;
                color: #38bdf8;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white; border: none; padding: 10px 15px; border-radius: 6px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; }
            QLineEdit {
                background-color: #1e293b; border: 1px solid #334155; padding: 8px; border-radius: 6px; color: white;
            }
            QLabel#Title { font-size: 24px; font-weight: bold; color: #38bdf8; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 30, 30, 30)

        # Header
        title = QLabel("Master Access Control Dashboard")
        title.setObjectName("Title")
        layout.addWidget(title)

        # Stats Console
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        # Control Panel
        control_box = QHBoxLayout()
        
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Enter Computer Name to Block/Unblock...")
        control_box.addWidget(self.target_input, 2)

        self.block_btn = QPushButton("BLOCK USER")
        self.block_btn.setStyleSheet("background-color: #ef4444;")
        self.block_btn.clicked.connect(self.block_user)
        control_box.addWidget(self.block_btn)

        self.unblock_btn = QPushButton("UNBLOCK USER")
        self.unblock_btn.setStyleSheet("background-color: #10b981;")
        self.unblock_btn.clicked.connect(self.unblock_user)
        control_box.addWidget(self.unblock_btn)
        
        layout.addLayout(control_box)

        # Refresh
        self.refresh_btn = QPushButton("Refresh Stats")
        self.refresh_btn.clicked.connect(self.refresh_stats)
        layout.addWidget(self.refresh_btn)

        db_manager.connect()
        self.refresh_stats()

    def refresh_stats(self):
        stats = db_manager.get_admin_dashboard_stats()
        # Fetch block statuses
        users_col = db_manager.db.users
        blocked_users = {u['computer_name'] for u in users_col.find({"is_blocked": True})}

        lines = [
            f"{'COMPUTER NAME':<25} {'EMAILS':<10} {'BILL (PKR)':<15} {'STATUS':<15} {'LAST ACTIVE':<20}",
            "=" * 90
        ]
        
        for user in stats:
            name = user.get("_id", "Unknown")
            emails = user.get("total_emails", 0)
            bill = user.get("bill_pkr", 0.0)
            last = user.get("last_active", "")
            
            status = "BLOCKED" if name in blocked_users else "ACTIVE"
            last_str = last.strftime("%Y-%m-%d %H:%M") if last else "Never"
            
            lines.append(f"{name:<25} {emails:<10} {bill:<15.2f} {status:<15} {last_str:<20}")
            
        self.console.setPlainText("\n".join(lines))

    def block_user(self):
        name = self.target_input.text().strip()
        if not name: return
        if db_manager.toggle_block_status(name, True):
            QMessageBox.information(self, "Success", f"Computer '{name}' has been BLOCKED.")
            self.refresh_stats()

    def unblock_user(self):
        name = self.target_input.text().strip()
        if not name: return
        if db_manager.toggle_block_status(name, False):
            QMessageBox.information(self, "Success", f"Computer '{name}' has been UNBLOCKED.")
            self.refresh_stats()

def main():
    app = QApplication(sys.argv)
    window = AdminBillingApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
