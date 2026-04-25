"""Qt stylesheet and tokens for the professional desktop dashboard."""

COLORS = {
    "bg": "#101314",
    "panel": "#181d1f",
    "panel_alt": "#202628",
    "card": "#20282a",
    "field": "#111719",
    "border": "#3a4747",
    "border_soft": "#2b3636",
    "text": "#f5f7f3",
    "muted": "#abb4af",
    "muted_soft": "#7f8a86",
    "accent": "#34b978",
    "accent_hover": "#2ea66b",
    "button": "rgba(255, 255, 255, 0.055)",
    "button_hover": "rgba(52, 185, 120, 0.16)",
    "button_pressed": "rgba(52, 185, 120, 0.24)",
    "button_disabled": "rgba(255, 255, 255, 0.03)",
    "success": "#42bf76",
    "warning": "#d7a13f",
    "danger": "#e16666",
    "info": "#6aa6ff",
}


APP_STYLE = f"""
QWidget {{
    background: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-family: "Segoe UI", Arial, Tahoma, sans-serif;
    font-size: 13px;
}}

QLabel {{
    background: transparent;
}}

QFrame#Panel,
QFrame#Card {{
    background: {COLORS["panel"]};
    border: 1px solid {COLORS["border_soft"]};
    border-radius: 6px;
}}

QFrame#MetricCard {{
    background: {COLORS["card"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
}}

QFrame#MetricCard:hover,
QFrame#Panel:hover {{
    border-color: {COLORS["border"]};
}}

QLabel#Title {{
    font-size: 18px;
    font-weight: 700;
}}

QLabel#SidebarTitle {{
    font-size: 24px;
    font-weight: 700;
}}

QLabel#SectionTitle {{
    font-size: 14px;
    font-weight: 700;
}}

QLabel#MetricValue {{
    font-size: 18px;
    font-weight: 700;
}}

QLabel#Muted,
QLabel#MetricLabel,
QLabel#MetricMeta {{
    color: {COLORS["muted"]};
    font-size: 11px;
}}

QLabel#InputLabel {{
    color: #d5e2dc;
    font-size: 12px;
    font-weight: 700;
    min-width: 120px;
}}

QFrame#InputSection {{
    background: rgba(255, 255, 255, 0.030);
    border: 1px solid rgba(255, 255, 255, 0.075);
    border-radius: 7px;
}}

QLabel#Badge {{
    background: {COLORS["field"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 700;
}}

QLineEdit,
QComboBox {{
    background: {COLORS["button"]};
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px;
    padding: 8px 11px;
    min-height: 26px;
    selection-background-color: {COLORS["accent"]};
}}

QLineEdit#TargetUrlInput,
QComboBox#OutputFilenameInput,
QLineEdit#OutputFilenameEditor {{
    background: rgba(255, 255, 255, 0.050);
    border: 1px solid rgba(255, 255, 255, 0.105);
    border-radius: 6px;
    padding: 9px 12px;
    font-size: 13px;
    font-weight: 600;
}}

QLineEdit#TargetUrlInput:hover,
QComboBox#OutputFilenameInput:hover,
QLineEdit#OutputFilenameEditor:hover {{
    background: rgba(255, 255, 255, 0.075);
    border-color: rgba(52, 185, 120, 0.44);
}}

QLineEdit#TargetUrlInput:focus,
QComboBox#OutputFilenameInput:focus,
QLineEdit#OutputFilenameEditor:focus {{
    border-color: {COLORS["accent"]};
    background: rgba(52, 185, 120, 0.080);
}}

QLineEdit:hover,
QComboBox:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: {COLORS["border"]};
}}

QLineEdit:focus,
QComboBox:focus {{
    border-color: {COLORS["accent"]};
}}

QComboBox::drop-down {{
    border: 0;
    width: 28px;
}}

QComboBox QAbstractItemView {{
    background: {COLORS["panel_alt"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["accent"]};
    outline: 0;
}}

QCheckBox {{
    background: transparent;
    spacing: 8px;
    color: {COLORS["text"]};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {COLORS["border"]};
    background: {COLORS["field"]};
}}

QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}

QPushButton {{
    background: {COLORS["button"]};
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px;
    padding: 8px 10px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

QPushButton:hover {{
    background: {COLORS["button_hover"]};
    border-color: {COLORS["accent"]};
}}

QPushButton:pressed {{
    background: {COLORS["button_pressed"]};
    border-color: {COLORS["accent_hover"]};
}}

QPushButton:focus {{
    border-color: {COLORS["accent"]};
}}

QPushButton:disabled {{
    color: {COLORS["muted_soft"]};
    background: {COLORS["button_disabled"]};
    border-color: rgba(255, 255, 255, 0.06);
}}

QPushButton#PrimaryButton {{
    background: rgba(52, 185, 120, 0.18);
    border-color: rgba(52, 185, 120, 0.48);
    color: {COLORS["text"]};
}}

QPushButton#PrimaryButton:hover {{
    background: rgba(52, 185, 120, 0.26);
    border-color: {COLORS["accent"]};
}}

QPushButton#PrimaryButton:pressed {{
    background: rgba(52, 185, 120, 0.34);
    border-color: {COLORS["accent_hover"]};
}}

QPushButton#StopButton {{
    background: rgba(255, 255, 255, 0.042);
    border-color: rgba(255, 255, 255, 0.085);
    color: {COLORS["text"]};
}}

QPushButton#StopButton:hover {{
    background: rgba(225, 102, 102, 0.14);
    border-color: {COLORS["danger"]};
}}

QPushButton#StopButton:disabled {{
    color: {COLORS["muted_soft"]};
    background: rgba(255, 255, 255, 0.026);
    border-color: rgba(255, 255, 255, 0.055);
}}

QPushButton#DangerButton {{
    background: {COLORS["button"]};
    border-color: rgba(255, 255, 255, 0.10);
    color: {COLORS["text"]};
}}

QPushButton#DangerButton:hover {{
    background: rgba(223, 91, 100, 0.14);
    border-color: {COLORS["danger"]};
}}

QPushButton#WarningButton {{
    background: {COLORS["button"]};
    border-color: rgba(255, 255, 255, 0.10);
    color: {COLORS["text"]};
}}

QPushButton#WarningButton:hover {{
    background: rgba(217, 154, 43, 0.14);
    border-color: {COLORS["warning"]};
}}

QPushButton#NavButton {{
    background: transparent;
    border: 0;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    color: {COLORS["muted"]};
}}

QPushButton#NavButton:hover {{
    background: {COLORS["button_hover"]};
    color: {COLORS["text"]};
}}

QPushButton#NavButton:checked {{
    background: {COLORS["button_pressed"]};
    color: {COLORS["accent"]};
    border-left: 3px solid {COLORS["accent"]};
    border-radius: 2px 6px 6px 2px;
}}

QPlainTextEdit {{
    background: rgba(7, 10, 10, 0.60);
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 10px;
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 12px;
    selection-background-color: {COLORS["accent"]};
}}

QPlainTextEdit#LogConsole {{
    color: #e8eef6;
}}

QPlainTextEdit#DataConsole {{
    color: #dce7f2;
}}

QProgressBar {{
    background: {COLORS["field"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {COLORS["accent"]};
    border-radius: 5px;
}}

QScrollArea {{
    border: 0;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["muted_soft"]};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    border: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS["border"]};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS["muted_soft"]};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    border: 0;
}}

QSplitter::handle {{
    background: {COLORS["bg"]};
    width: 6px;
}}

QSplitter::handle:hover {{
    background: {COLORS["border_soft"]};
}}

QToolTip {{
    background: {COLORS["panel_alt"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 8px;
}}
"""
