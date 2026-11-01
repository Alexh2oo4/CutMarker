"""Application bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path


def _resolve_icon_path() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / "resources" / "cutmarker.ico",
        Path(__file__).resolve().parents[1] / "assets" / "cutmarker.ico",
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.insert(0, Path(meipass) / "cutmarker" / "resources" / "cutmarker.ico")
        candidates.insert(
            0, Path(sys.executable).resolve().parent / "cutmarker" / "resources" / "cutmarker.ico"
        )
    for path in candidates:
        if path.is_file():
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from cutmarker import __app_name__
    from cutmarker.ui.main_window import MainWindow
    from cutmarker.ui.styles import APP_STYLE

    # High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("CutMarker")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    icon_path = _resolve_icon_path()
    if icon_path is not None:
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)

    window = MainWindow()
    if icon_path is not None:
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
