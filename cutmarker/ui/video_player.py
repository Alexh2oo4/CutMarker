"""Frame-accurate video preview using OpenCV decoding + Qt display."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate, frame_to_timecode
from cutmarker.core.video_metadata import VideoMetadata


class VideoPlayerWidget(QWidget):
    frameChanged = Signal(int)
    cutJumpRequested = Signal(int)  # unused externally; nav via methods

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cap = None
        self._meta: VideoMetadata | None = None
        self._fps: FrameRate = FrameRate.from_float(24.0)
        self._frame_index = 0
        self._total_frames = 0
        self._playing = False
        self._cuts = CutList()
        self._cut_frames: set[int] = set()

        self.surface = QLabel()
        self.surface.setObjectName("videoSurface")
        self.surface.setAlignment(Qt.AlignCenter)
        self.surface.setMinimumSize(480, 270)
        self.surface.setScaledContents(False)

        self.timecode_label = QLabel("00:00:00:00")
        self.timecode_label.setObjectName("timecodeLabel")
        self.timecode_label.setAlignment(Qt.AlignCenter)

        self.frame_label = QLabel("Frame 0 / 0")
        self.frame_label.setAlignment(Qt.AlignCenter)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self._slider_dragging = False

        self.btn_play = QPushButton("Play")
        self.btn_prev = QPushButton("⟨ Cut")
        self.btn_next = QPushButton("Cut ⟩")
        self.btn_frame_back = QPushButton("⟨ Frame")
        self.btn_frame_fwd = QPushButton("Frame ⟩")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_prev.clicked.connect(self.jump_prev_cut)
        self.btn_next.clicked.connect(self.jump_next_cut)
        self.btn_frame_back.clicked.connect(lambda: self.step_frames(-1))
        self.btn_frame_fwd.clicked.connect(lambda: self.step_frames(1))

        controls = QHBoxLayout()
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_frame_back)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_frame_fwd)
        controls.addWidget(self.btn_next)
        controls.addStretch(1)
        controls.addWidget(self.timecode_label)
        controls.addWidget(self.frame_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.surface, stretch=1)
        layout.addWidget(self.slider)
        layout.addLayout(controls)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    def load_video(self, meta: VideoMetadata) -> None:
        import cv2

        self.close_video()
        self._meta = meta
        self._fps = meta.frame_rate or FrameRate.from_float(24.0)
        self._cap = cv2.VideoCapture(meta.path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video for preview: {meta.path}")
        reported = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._total_frames = meta.total_frames or reported or 0
        self.slider.setMaximum(max(0, self._total_frames - 1))
        self.seek(0)

    def close_video(self) -> None:
        self.pause()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def set_cuts(self, cuts: CutList) -> None:
        self._cuts = cuts
        self._cut_frames = {c.frame_index for c in cuts}
        self._update_labels()

    def current_frame(self) -> int:
        return self._frame_index

    def seek(self, frame_index: int) -> None:
        if self._cap is None:
            return
        import cv2

        frame_index = int(max(0, min(frame_index, max(0, self._total_frames - 1))))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
        ok, bgr = self._cap.read()
        if not ok or bgr is None:
            return
        self._frame_index = frame_index
        self._show_bgr(bgr)
        if not self._slider_dragging:
            self.slider.blockSignals(True)
            self.slider.setValue(frame_index)
            self.slider.blockSignals(False)
        self._update_labels()
        self.frameChanged.emit(frame_index)

    def step_frames(self, delta: int) -> None:
        self.pause()
        self.seek(self._frame_index + delta)

    def toggle_play(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if self._cap is None:
            return
        self._playing = True
        self.btn_play.setText("Pause")
        interval = max(1, int(1000.0 / float(self._fps.rate)))
        self._timer.start(interval)

    def pause(self) -> None:
        self._playing = False
        self.btn_play.setText("Play")
        self._timer.stop()

    def jump_prev_cut(self) -> None:
        cut = self._cuts.previous_cut(self._frame_index)
        if cut:
            self.pause()
            self.seek(cut.frame_index)

    def jump_next_cut(self) -> None:
        cut = self._cuts.next_cut(self._frame_index)
        if cut:
            self.pause()
            self.seek(cut.frame_index)

    def _on_tick(self) -> None:
        if self._frame_index >= self._total_frames - 1:
            self.pause()
            return
        # Sequential read is faster/more accurate than seek-per-frame
        ok, bgr = self._cap.read() if self._cap else (False, None)
        if not ok or bgr is None:
            self.pause()
            return
        self._frame_index += 1
        self._show_bgr(bgr)
        self.slider.blockSignals(True)
        self.slider.setValue(self._frame_index)
        self.slider.blockSignals(False)
        self._update_labels()
        self.frameChanged.emit(self._frame_index)

    def _show_bgr(self, bgr: np.ndarray) -> None:
        import cv2

        # Show picture only — cut status is indicated in the frame/timecode labels
        # and timeline markers, not drawn over the video.
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(image)
        scaled = pix.scaled(
            self.surface.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.surface.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Re-render current frame to new size
        if self._cap is not None:
            idx = self._frame_index
            self.seek(idx)

    def _update_labels(self) -> None:
        start_tc = self._meta.start_timecode if self._meta else None
        tc = frame_to_timecode(self._frame_index, self._fps, start_timecode=start_tc)
        self.timecode_label.setText(tc)
        marker = " ● CUT" if self._frame_index in self._cut_frames else ""
        self.frame_label.setText(
            f"Frame {self._frame_index} / {max(0, self._total_frames - 1)}{marker}"
        )

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True
        self.pause()

    def _on_slider_released(self) -> None:
        self._slider_dragging = False
        self.seek(self.slider.value())

    def _on_slider_changed(self, value: int) -> None:
        if self._slider_dragging:
            self.seek(value)
