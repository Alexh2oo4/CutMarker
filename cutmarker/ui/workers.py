"""Background workers for analysis and thumbnail generation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from cutmarker.core.detection import DetectionProgress, DetectionResult, DetectionSettings, detect_cuts


class AnalysisWorker(QObject):
    progress = Signal(object)  # DetectionProgress
    finished = Signal(object)  # DetectionResult
    error = Signal(str)

    def __init__(self, video_path: str, settings: DetectionSettings) -> None:
        super().__init__()
        self.video_path = video_path
        self.settings = settings
        self._cancel = False

    @Slot()
    def run(self) -> None:
        try:
            result = detect_cuts(
                self.video_path,
                self.settings,
                progress_callback=self._on_progress,
                cancel_callback=lambda: self._cancel,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, progress: DetectionProgress) -> None:
        self.progress.emit(progress)

    def cancel(self) -> None:
        self._cancel = True


class ThumbnailWorker(QObject):
    """Load before/after thumbnails for a cut frame."""

    finished = Signal(int, object, object)  # frame_index, before_rgb, after_rgb
    error = Signal(str)

    def __init__(self, video_path: str, frame_index: int) -> None:
        super().__init__()
        self.video_path = video_path
        self.frame_index = frame_index

    @Slot()
    def run(self) -> None:
        try:
            import cv2

            from cutmarker.core.video_metadata import extract_frame_bgr

            after = extract_frame_bgr(self.video_path, self.frame_index)
            before = None
            if self.frame_index > 0:
                before = extract_frame_bgr(self.video_path, self.frame_index - 1)
            else:
                before = after.copy()

            def to_rgb(bgr):
                return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            self.finished.emit(self.frame_index, to_rgb(before), to_rgb(after))
        except Exception as exc:
            self.error.emit(str(exc))


def start_worker(worker: QObject, thread: QThread) -> None:
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.start()
