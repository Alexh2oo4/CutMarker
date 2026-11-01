"""Dark professional post-production theme."""

APP_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #e6e6e6;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1a1a1a;
}
QToolBar {
    background-color: #252526;
    border: none;
    border-bottom: 1px solid #333;
    spacing: 8px;
    padding: 6px 10px;
}
QToolBar QPushButton {
    background-color: #3c3c3c;
    color: #f0f0f0;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 6px 14px;
    font-weight: 600;
}
QToolBar QPushButton:hover {
    background-color: #4a4a4a;
    border-color: #777;
}
QToolBar QPushButton:pressed {
    background-color: #2d2d2d;
}
QToolBar QPushButton#primaryButton {
    background-color: #0e639c;
    border-color: #1177bb;
}
QToolBar QPushButton#primaryButton:hover {
    background-color: #1177bb;
}
QPushButton:checked {
    background-color: #0e639c;
    border-color: #1177bb;
    color: #ffffff;
}
QLabel#appTitle {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.5px;
    padding-right: 16px;
}
QLabel#timecodeLabel {
    font-family: "Consolas", "Courier New", monospace;
    font-size: 20px;
    font-weight: 600;
    color: #4ec9b0;
    background-color: #111;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 6px 12px;
}
QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
    color: #cccccc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px 6px;
    color: #eee;
    selection-background-color: #0e639c;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    selection-background-color: #0e639c;
}
QCheckBox {
    spacing: 8px;
}
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 6px 12px;
    color: #f0f0f0;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:disabled {
    color: #777;
    background-color: #2a2a2a;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #333;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4ec9b0;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #0e639c;
    border-radius: 3px;
}
QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #252526;
    gridline-color: #333;
    border: 1px solid #333;
    selection-background-color: #094771;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #bbb;
    padding: 6px;
    border: none;
    border-right: 1px solid #3a3a3a;
    border-bottom: 1px solid #3a3a3a;
    font-weight: 600;
}
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 3px;
    text-align: center;
    color: #ddd;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #0e639c;
}
QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}
QSplitter::handle {
    background-color: #333;
}
QLabel#videoSurface {
    background-color: #000000;
    border: 1px solid #333;
}
QFrame#panel {
    background-color: #252526;
    border-right: 1px solid #333;
}
"""
