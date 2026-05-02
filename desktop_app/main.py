"""Application entrypoint for the desktop dashboard."""

from desktop_app.qt_ui.app import main as run_qt_dashboard
from scraper.access_control import require_app_access


def main() -> int:
    """Check remote access first, then launch the PySide6 dashboard."""
    require_app_access()
    return run_qt_dashboard()

if __name__ == "__main__":
    raise SystemExit(main())
