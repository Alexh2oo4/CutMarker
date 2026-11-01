"""Timeline ruler with cut markers and zoom."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from cutmarker.core.cuts import CutList


class TimelineWidget(QWidget):
    positionChanged = Signal(int)
    cutSelected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._total_frames = 0
        self._position = 0
        self._cuts = CutList()
        self._zoom = 1.0  # 1 = full film visible

        self.canvas = _TimelineCanvas()
        self.canvas.clickedFrame.connect(self._on_canvas_click)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(1)
        self.zoom_slider.setMaximum(50)
        self.zoom_slider.setValue(1)
        self.zoom_slider.valueChanged.connect(self._on_zoom)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Timeline zoom"))
        zoom_row.addWidget(self.zoom_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        layout.addLayout(zoom_row)

    def set_total_frames(self, total: int) -> None:
        self._total_frames = max(0, total)
        self.canvas.set_data(self._total_frames, self._position, self._cuts, self._zoom)

    def set_cuts(self, cuts: CutList) -> None:
        self._cuts = cuts
        self.canvas.set_data(self._total_frames, self._position, self._cuts, self._zoom)

    def set_position(self, frame: int) -> None:
        self._position = frame
        self.canvas.set_data(self._total_frames, self._position, self._cuts, self._zoom)

    def _on_zoom(self, value: int) -> None:
        self._zoom = float(value)
        self.canvas.set_data(self._total_frames, self._position, self._cuts, self._zoom)

    def _on_canvas_click(self, frame: int) -> None:
        self.positionChanged.emit(frame)
        cut = self._cuts.nearest_cut(frame)
        if cut and abs(cut.frame_index - frame) <= max(1, self._total_frames // 200):
            self.cutSelected.emit(cut.frame_index)


class _TimelineCanvas(QWidget):
    clickedFrame = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(56)
        self._total = 0
        self._pos = 0
        self._cuts = CutList()
        self._zoom = 1.0

    def set_data(self, total: int, pos: int, cuts: CutList, zoom: float) -> None:
        self._total = total
        self._pos = pos
        self._cuts = cuts
        self._zoom = max(1.0, zoom)
        self.update()

    def _visible_range(self) -> tuple[int, int]:
        if self._total <= 0:
            return 0, 0
        window = max(1, int(self._total / self._zoom))
        start = max(0, self._pos - window // 2)
        end = min(self._total, start + window)
        start = max(0, end - window)
        return start, end

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111111"))
        w = self.width()
        h = self.height()
        if self._total <= 0 or w <= 0:
            return

        start, end = self._visible_range()
        span = max(1, end - start)

        # Baseline
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.drawLine(0, h // 2, w, h // 2)

        # Cut markers
        painter.setPen(QPen(QColor("#ce9178"), 1))
        for cut in self._cuts:
            if cut.frame_index < start or cut.frame_index > end:
                continue
            x = int((cut.frame_index - start) / span * (w - 1))
            painter.drawLine(x, 8, x, h - 8)

        # Playhead
        if start <= self._pos <= end:
            x = int((self._pos - start) / span * (w - 1))
            painter.setPen(QPen(QColor("#4ec9b0"), 2))
            painter.drawLine(x, 0, x, h)

        painter.setPen(QColor("#888888"))
        painter.drawText(8, 14, f"{start} – {end}")

    def mousePressEvent(self, event) -> None:
        if self._total <= 0:
            return
        start, end = self._visible_range()
        span = max(1, end - start)
        ratio = event.position().x() / max(1, self.width() - 1)
        frame = int(start + ratio * span)
        self.clickedFrame.emit(frame)
