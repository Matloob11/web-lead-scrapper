"""Qt stylesheet and tokens for the professional desktop dashboard."""

COLORS = {
    "bg": "#111821",
    "panel": "#18212b",
    "panel_alt": "#202b36",
    "card": "#212c38",
    "field": "#151d26",
    "border": "#394656",
    "border_soft": "#2c3744",
    "text": "#f4f6f8",
    "muted": "#a8b0bc",
    "muted_soft": "#7d8795",
    "accent": "#2fb47c",
    "accent_hover": "#289d6c",
    "button": "rgba(255, 255, 255, 0.045)",
    "button_hover": "rgba(47, 180, 124, 0.16)",
    "button_pressed": "rgba(47, 180, 124, 0.24)",
    "button_disabled": "rgba(255, 255, 255, 0.025)",
    "success": "#37b26c",
    "warning": "#d99a2b",
    "danger": "#df5b64",
    "info": "#4f8be8",
}


APP_STYLE = f"""
QWidget {{
    background: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-family: "Segoe UI";
    font-size: 13px;
}}

QLabel {{
    background: transparent;
}}

QFrame#Panel,
QFrame#Card {{
    background: {COLORS["panel"]};
    border: 1px solid {COLORS["border_soft"]};
    border-radius: 8px;
}}

QFrame#MetricCard {{
    background: {COLORS["card"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}

QFrame#MetricCard:hover,
QFrame#Panel:hover {{
    border-color: {COLORS["border"]};
}}

QLabel#Title {{
    font-size: 22px;
    font-weight: 700;
}}

QLabel#SidebarTitle {{
    font-size: 24px;
    font-weight: 700;
}}

QLabel#SectionTitle {{
    font-size: 16px;
    font-weight: 700;
}}

QLabel#MetricValue {{
    font-size: 22px;
    font-weight: 700;
}}

QLabel#Muted,
QLabel#MetricLabel,
QLabel#MetricMeta {{
    color: {COLORS["muted"]};
}}

QLabel#Badge {{
    background: {COLORS["field"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 6px 10px;
    font-weight: 700;
}}

QLineEdit,
QComboBox {{
    background: {COLORS["field"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 22px;
    selection-background-color: {COLORS["accent"]};
}}

QLineEdit:focus,
QComboBox:focus {{
    border-color: {COLORS["accent"]};
}}

QComboBox::drop-down {{
    border: 0;
    width: 28px;
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
    border-radius: 8px;
    padding: 8px 12px;
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
    background: {COLORS["button"]};
    border-color: rgba(255, 255, 255, 0.10);
    color: {COLORS["text"]};
}}

QPushButton#PrimaryButton:hover {{
    background: {COLORS["button_hover"]};
    border-color: {COLORS["accent"]};
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

QPlainTextEdit {{
    background: rgba(10, 14, 20, 0.58);
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px;
    font-family: "Cascadia Mono", Consolas, monospace;
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

QSplitter::handle {{
    background: {COLORS["bg"]};
    width: 6px;
}}
"""
