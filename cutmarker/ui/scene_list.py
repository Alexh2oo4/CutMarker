"""Detected scene table with notes and review status."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.video_metadata import VideoMetadata


class SceneListWidget(QWidget):
    sceneSelected = Signal(int)  # frame_index
    addCutRequested = Signal()
    deleteCutRequested = Signal(int)
    nudgeRequested = Signal(int, int)  # frame_index, delta
    reviewToggled = Signal(int, bool)
    notesChanged = Signal(int, str)  # frame_index, notes

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cuts = CutList()
        self._fps = FrameRate.from_float(24.0)
        self._start_tc: str | None = None
        self._selected_frame: int | None = None
        self._updating_notes = False

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Scene", "Frame", "Timecode", "Source", "Reviewed", "Notes"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(self._on_double)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("Notes for selected cut:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText(
            "Select a cut, then type a note (saved with the project / export comments)"
        )
        self.notes_edit.setEnabled(False)
        self.notes_edit.editingFinished.connect(self._commit_notes)
        notes_row.addWidget(self.notes_edit, stretch=1)

        self.btn_add = QPushButton("Add cut at playhead")
        self.btn_delete = QPushButton("Delete selected")
        self.btn_earlier = QPushButton("Move −1 frame")
        self.btn_later = QPushButton("Move +1 frame")
        self.btn_review = QPushButton("Toggle reviewed")
        self.btn_add.clicked.connect(self.addCutRequested.emit)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_earlier.clicked.connect(lambda: self._nudge(-1))
        self.btn_later.clicked.connect(lambda: self._nudge(1))
        self.btn_review.clicked.connect(self._toggle_review)

        btns = QHBoxLayout()
        for b in (
            self.btn_add,
            self.btn_delete,
            self.btn_earlier,
            self.btn_later,
            self.btn_review,
        ):
            btns.addWidget(b)
        btns.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(notes_row)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btns)

    def set_video(self, video: VideoMetadata | None) -> None:
        if video and video.frame_rate:
            self._fps = video.frame_rate
        self._start_tc = video.start_timecode if video else None

    def set_cuts(self, cuts: CutList) -> None:
        prev = self._selected_frame
        self._cuts = cuts
        self.table.setRowCount(0)
        for cut in cuts:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                str(cut.scene_number),
                str(cut.frame_index),
                cut.timecode(self._fps, start_timecode=self._start_tc),
                cut.source,
                "Yes" if cut.reviewed else "No",
                cut.notes,
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.UserRole, cut.frame_index)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        if prev is not None:
            self.select_frame(prev)
            self._load_notes_for(prev)

    def selected_frame(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return None
        return int(item.data(Qt.UserRole))

    def select_frame(self, frame_index: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.data(Qt.UserRole)) == frame_index:
                self.table.blockSignals(True)
                self.table.selectRow(row)
                self.table.blockSignals(False)
                self._selected_frame = frame_index
                self._load_notes_for(frame_index)
                return

    def _load_notes_for(self, frame_index: int) -> None:
        cut = next((c for c in self._cuts if c.frame_index == frame_index), None)
        self._updating_notes = True
        self.notes_edit.setEnabled(cut is not None)
        self.notes_edit.setText(cut.notes if cut else "")
        self._updating_notes = False

    def _commit_notes(self) -> None:
        if self._updating_notes:
            return
        frame = self._selected_frame
        if frame is None:
            return
        self.notesChanged.emit(frame, self.notes_edit.text())

    def _on_select(self) -> None:
        frame = self.selected_frame()
        self._selected_frame = frame
        if frame is not None:
            self._load_notes_for(frame)
            self.sceneSelected.emit(frame)
        else:
            self.notes_edit.setEnabled(False)
            self.notes_edit.clear()

    def _on_double(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item:
            self.sceneSelected.emit(int(item.data(Qt.UserRole)))

    def _delete(self) -> None:
        frame = self.selected_frame()
        if frame is not None:
            self.deleteCutRequested.emit(frame)

    def _nudge(self, delta: int) -> None:
        frame = self.selected_frame()
        if frame is not None:
            self.nudgeRequested.emit(frame, delta)

    def _toggle_review(self) -> None:
        frame = self.selected_frame()
        if frame is None:
            return
        cut = next((c for c in self._cuts if c.frame_index == frame), None)
        if cut:
            self.reviewToggled.emit(frame, not cut.reviewed)
