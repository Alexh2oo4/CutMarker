"""Main application window."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cutmarker import __app_name__, __version__
from cutmarker.core.cuts import CutList
from cutmarker.core.detection import DetectionProgress, DetectionResult, format_duration
from cutmarker.core.project import CutMarkerProject
from cutmarker.core.video_metadata import SUPPORTED_EXTENSIONS, probe_video
from cutmarker.export.comments_export import (
    export_all_comments,
    export_individual_comments,
    export_selected_comment,
)
from cutmarker.export.csv_export import export_csv
from cutmarker.export.edl_export import export_edl
from cutmarker.export.midi_markers import export_protools_midi_markers
from cutmarker.export.protools import IMPORT_INSTRUCTIONS, export_protools_session_text, export_protools_tab
from cutmarker.export.ptsl_markers import PTSL_INSTRUCTIONS, push_markers_to_pro_tools
from cutmarker.export.text_export import export_text_report
from cutmarker.ui.scene_list import SceneListWidget
from cutmarker.ui.settings_panel import SettingsPanel
from cutmarker.ui.timeline import TimelineWidget
from cutmarker.ui.video_player import VideoPlayerWidget
from cutmarker.ui.workers import AnalysisWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        self.project = CutMarkerProject()
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._analysis_started_at: float | None = None
        self._last_progress: DetectionProgress | None = None
        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(250)
        self._eta_timer.timeout.connect(self._refresh_analysis_status)

        self._build_toolbar()
        self._build_body()
        self._build_status()
        self._set_busy(False)

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        title = QLabel(__app_name__.upper())
        title.setObjectName("appTitle")
        tb.addWidget(title)

        self.btn_import = QPushButton("Import Video")
        self.btn_analyse = QPushButton("Analyse")
        self.btn_analyse.setObjectName("primaryButton")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_export = QPushButton("Export")
        self.btn_send_pt = QPushButton("Send to Pro Tools")
        self.btn_send_pt.setObjectName("primaryButton")
        self.btn_export_comments = QPushButton("Export Comments")
        self.btn_save = QPushButton("Save Project")
        self.btn_open = QPushButton("Open Project")

        self.btn_import.clicked.connect(self.import_video)
        self.btn_analyse.clicked.connect(self.analyse)
        self.btn_cancel.clicked.connect(self.cancel_analysis)
        self.btn_export.clicked.connect(self.export_markers)
        self.btn_send_pt.clicked.connect(self.send_to_pro_tools)
        self.btn_export_comments.clicked.connect(self.export_comments)
        self.btn_save.clicked.connect(self.save_project)
        self.btn_open.clicked.connect(self.open_project)

        for b in (
            self.btn_import,
            self.btn_analyse,
            self.btn_cancel,
            self.btn_send_pt,
            self.btn_export,
            self.btn_export_comments,
            self.btn_save,
            self.btn_open,
        ):
            tb.addWidget(b)

        # Menus / shortcuts
        open_act = QAction("Import Video", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self.import_video)
        self.addAction(open_act)

    def _build_body(self) -> None:
        self.settings_panel = SettingsPanel()
        self.player = VideoPlayerWidget()
        self.timeline = TimelineWidget()
        self.scene_list = SceneListWidget()

        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(4, 4, 4, 4)
        centre_layout.addWidget(self.player, stretch=3)
        centre_layout.addWidget(self.timeline)
        centre_layout.addWidget(self.scene_list, stretch=2)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.settings_panel)
        splitter.addWidget(centre)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.player.frameChanged.connect(self.timeline.set_position)
        self.timeline.positionChanged.connect(self.player.seek)
        self.timeline.cutSelected.connect(self._select_cut)
        self.scene_list.sceneSelected.connect(self._select_cut)
        self.scene_list.addCutRequested.connect(self._add_cut_at_playhead)
        self.scene_list.deleteCutRequested.connect(self._delete_cut)
        self.scene_list.nudgeRequested.connect(self._nudge_cut)
        self.scene_list.reviewToggled.connect(self._toggle_review)
        self.scene_list.notesChanged.connect(self._set_notes)

    def _build_status(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.progress = QProgressBar()
        self.progress.setMinimumWidth(160)
        self.progress.setMaximumWidth(200)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        self.status_label = QLabel("Import a video to begin.")
        status.addWidget(self.status_label, stretch=1)
        status.addPermanentWidget(self.progress)

    # --------------------------------------------------------------- Import
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS or path.is_file():
                self.load_video(path)
                break

    def import_video(self) -> None:
        filters = (
            "Video files (*.mov *.mp4 *.m4v *.mxf *.avi *.mkv *.mpg *.mpeg *.wmv *.webm);;"
            "All files (*.*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Import Video", "", filters)
        if path:
            self.load_video(Path(path))

    def load_video(self, path: Path) -> None:
        try:
            meta = probe_video(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        self.project = CutMarkerProject(video=meta)
        self.project.sync_export_fps_from_video()
        self.settings_panel.set_video_info(meta)
        if self.project.export_settings:
            self.settings_panel.set_export_settings(self.project.export_settings)

        try:
            self.player.load_video(meta)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Preview warning",
                f"Video metadata loaded but preview failed:\n{exc}",
            )

        self.scene_list.set_video(meta)
        self.timeline.set_total_frames(meta.total_frames or 0)
        self.project.cuts = CutList()
        self._refresh_cuts()

        warn = ""
        if meta.warnings:
            warn = "\n".join(meta.warnings)
            QMessageBox.information(self, "Import notes", warn)
        self.status_label.setText(f"Loaded {meta.filename} — ready to analyse.")
        self.btn_analyse.setEnabled(True)

    # ------------------------------------------------------------- Analyse
    def analyse(self) -> None:
        if not self.project.video:
            QMessageBox.information(self, "Analyse", "Import a video first.")
            return
        if self._analysis_thread and self._analysis_thread.isRunning():
            return

        settings = self.settings_panel.detection_settings()
        self.project.detection_settings = settings
        self._set_busy(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self._analysis_started_at = time.perf_counter()
        self._last_progress = None
        self.status_label.setText(
            "Analysing cuts on CPU… estimating time after the first second…"
        )
        self._eta_timer.start()

        self._analysis_thread = QThread(self)
        self._analysis_worker = AnalysisWorker(self.project.video.path, settings)
        self._analysis_worker.moveToThread(self._analysis_thread)
        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.progress.connect(self._on_progress)
        self._analysis_worker.finished.connect(self._on_analysis_done)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.finished.connect(self._analysis_thread.quit)
        self._analysis_worker.error.connect(self._analysis_thread.quit)
        self._analysis_thread.finished.connect(self._cleanup_analysis)
        self._analysis_thread.start()

    def cancel_analysis(self) -> None:
        if self._analysis_worker:
            self._analysis_worker.cancel()
            self.status_label.setText("Cancelling analysis…")

    def _on_progress(self, progress: DetectionProgress) -> None:
        self._last_progress = progress
        self.progress.setValue(int(progress.percent))
        self.progress.setFormat("%p%")
        self._refresh_analysis_status()

    def _refresh_analysis_status(self) -> None:
        """Update status using wall-clock elapsed (not only on frame callbacks)."""
        if self._analysis_started_at is None:
            return
        elapsed = time.perf_counter() - self._analysis_started_at
        progress = self._last_progress
        if progress is None:
            self.status_label.setText(
                f"Analysing on CPU… elapsed {format_duration(elapsed)}"
            )
            return
        if progress.cancelled:
            self.status_label.setText(
                f"Cancelling… elapsed {format_duration(elapsed)}"
            )
            return
        if progress.percent >= 100:
            return

        parts = [progress.message or "Analysing"]
        if progress.frames_per_second is not None:
            parts.append(f"{progress.frames_per_second:.0f} fps")
        if progress.eta_seconds is not None:
            parts.append(f"~{format_duration(progress.eta_seconds)} remaining")
        parts.append(f"elapsed {format_duration(elapsed)}")
        parts.append(progress.device or "CPU")
        self.status_label.setText(" — ".join(parts[:1] + [", ".join(parts[1:])]))

    def _stop_analysis_timer(self) -> None:
        self._eta_timer.stop()
        self._analysis_started_at = None
        self._last_progress = None
        self.progress.setFormat("%p%")

    def _on_analysis_done(self, result: DetectionResult) -> None:
        self._stop_analysis_timer()
        self.project.cuts = result.cut_list
        self._refresh_cuts()
        self._set_busy(False)
        self.progress.setVisible(False)
        msg = f"Analysis complete — {len(result.cut_list)} scene(s)."
        if result.warnings:
            msg += " " + " ".join(result.warnings)
            QMessageBox.information(self, "Analysis notes", "\n".join(result.warnings))
        self.status_label.setText(msg)

    def _on_analysis_error(self, message: str) -> None:
        self._stop_analysis_timer()
        self._set_busy(False)
        self.progress.setVisible(False)
        self.status_label.setText("Analysis failed.")
        QMessageBox.critical(self, "Analysis failed", message)

    def _cleanup_analysis(self) -> None:
        if self._analysis_worker:
            self._analysis_worker.deleteLater()
            self._analysis_worker = None
        if self._analysis_thread:
            self._analysis_thread.deleteLater()
            self._analysis_thread = None

    def _set_busy(self, busy: bool) -> None:
        self.btn_analyse.setEnabled(not busy and self.project.video is not None)
        self.btn_cancel.setEnabled(busy)
        self.btn_import.setEnabled(not busy)
        has_cuts = len(self.project.cuts) > 0
        self.btn_export.setEnabled(not busy and has_cuts)
        self.btn_send_pt.setEnabled(not busy and has_cuts)
        self.btn_export_comments.setEnabled(not busy and has_cuts)

    # -------------------------------------------------------- Cut editing
    def _refresh_cuts(self) -> None:
        cuts = self.project.cuts
        self.player.set_cuts(cuts)
        self.timeline.set_cuts(cuts)
        self.scene_list.set_cuts(cuts)
        has_cuts = len(cuts) > 0
        self.btn_export.setEnabled(has_cuts)
        self.btn_send_pt.setEnabled(has_cuts)
        self.btn_export_comments.setEnabled(has_cuts)

    def _select_cut(self, frame_index: int) -> None:
        self.player.pause()
        self.player.seek(frame_index)
        self.scene_list.select_frame(frame_index)

    def _add_cut_at_playhead(self) -> None:
        frame = self.player.current_frame()
        self.project.cuts.add_cut(frame)
        self._refresh_cuts()
        self._select_cut(frame)
        self.status_label.setText(f"Added cut at frame {frame}.")

    def _delete_cut(self, frame_index: int) -> None:
        if frame_index == 0:
            answer = QMessageBox.question(
                self,
                "Delete SCENE 1?",
                "Delete the opening scene marker at frame 0?",
            )
            if answer != QMessageBox.Yes:
                return
        self.project.cuts.delete_cut(frame_index)
        self._refresh_cuts()
        self.status_label.setText(f"Deleted cut at frame {frame_index}.")

    def _nudge_cut(self, frame_index: int, delta: int) -> None:
        moved = self.project.cuts.nudge_cut(frame_index, delta)
        self._refresh_cuts()
        if moved:
            self._select_cut(moved.frame_index)
            self.status_label.setText(
                f"Moved cut to frame {moved.frame_index}."
            )

    def _toggle_review(self, frame_index: int, reviewed: bool) -> None:
        self.project.cuts.mark_reviewed(frame_index, reviewed)
        self._refresh_cuts()
        self.scene_list.select_frame(frame_index)

    def _set_notes(self, frame_index: int, notes: str) -> None:
        self.project.cuts.set_notes(frame_index, notes)
        # Refresh table Notes column without losing selection / playhead
        self._refresh_cuts()
        self.scene_list.select_frame(frame_index)
        self.status_label.setText(f"Updated notes for frame {frame_index}.")

    # ------------------------------------------------------------- Export
    def send_to_pro_tools(self) -> None:
        """Create Absolute Memory Locations in the open Pro Tools session."""
        if not self.project.cuts:
            QMessageBox.information(self, "Send to Pro Tools", "No scenes to send.")
            return

        self.project.export_settings = self.settings_panel.export_settings()
        reply = QMessageBox.question(
            self,
            "Send to Pro Tools",
            "This will create Absolute Memory Location markers "
            f"({len(self.project.cuts)} scenes) in the currently open "
            "Pro Tools session.\n\n"
            "Make sure Pro Tools is running with your session open, and that "
            "CutMarker’s session start TC / frame rate match that session.\n\n"
            "Continue?",
        )
        if reply != QMessageBox.Yes:
            return

        self.status_label.setText("Sending Absolute markers to Pro Tools…")
        try:
            result = push_markers_to_pro_tools(
                self.project.cuts,
                self.project.video,
                self.project.export_settings,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Send to Pro Tools failed", str(exc))
            self.status_label.setText("Pro Tools send failed.")
            return

        msg = (
            f"Created {result.created} Absolute marker(s) in session "
            f"“{result.session_name}”."
        )
        if result.skipped:
            msg += f"\n{result.skipped} skipped."
        if result.errors:
            msg += "\n\n" + "\n".join(result.errors[:12])
            if len(result.errors) > 12:
                msg += f"\n… and {len(result.errors) - 12} more."
        QMessageBox.information(self, "Send to Pro Tools", msg + f"\n\n{PTSL_INSTRUCTIONS}")
        self.status_label.setText(
            f"Sent {result.created} Absolute marker(s) to Pro Tools."
        )

    def export_comments(self) -> None:
        if not self.project.cuts:
            QMessageBox.information(self, "Export Comments", "No scenes to export.")
            return

        choice = QMessageBox(self)
        choice.setWindowTitle("Export Comments")
        choice.setText("How do you want to export scene Notes?")
        choice.setInformativeText(
            'Format: SCENE 1 "comment text"\n\n'
            "• All comments — one .txt with every scene\n"
            "• Individual — one .txt per scene in a folder\n"
            "• Selected — only the cut selected in the list"
        )
        btn_all = choice.addButton("All in one file", QMessageBox.AcceptRole)
        btn_each = choice.addButton("Individual files", QMessageBox.AcceptRole)
        btn_sel = choice.addButton("Selected scene", QMessageBox.AcceptRole)
        choice.addButton(QMessageBox.Cancel)
        choice.exec()
        clicked = choice.clickedButton()

        cuts = self.project.cuts
        try:
            if clicked is btn_all:
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Export All Scene Comments",
                    "scene_comments.txt",
                    "Text (*.txt)",
                )
                if not path:
                    return
                out = export_all_comments(path, cuts)
                self.status_label.setText(f"Exported all comments → {out.name}")
                QMessageBox.information(self, "Export complete", f"Saved:\n{out}")
            elif clicked is btn_each:
                folder = QFileDialog.getExistingDirectory(
                    self, "Choose folder for individual scene comment files"
                )
                if not folder:
                    return
                written = export_individual_comments(folder, cuts)
                self.status_label.setText(
                    f"Exported {len(written)} comment file(s)."
                )
                QMessageBox.information(
                    self,
                    "Export complete",
                    f"Wrote {len(written)} file(s) to:\n{folder}",
                )
            elif clicked is btn_sel:
                frame = self.scene_list.selected_frame()
                if frame is None:
                    QMessageBox.information(
                        self,
                        "Export Comments",
                        "Select a scene in the list first.",
                    )
                    return
                cut = next(c for c in cuts if c.frame_index == frame)
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Export Selected Scene Comment",
                    f"SCENE_{cut.scene_number}.txt",
                    "Text (*.txt)",
                )
                if not path:
                    return
                out = export_selected_comment(path, cut)
                self.status_label.setText(
                    f"Exported {cut.marker_name()} comment → {out.name}"
                )
                QMessageBox.information(self, "Export complete", f"Saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def export_markers(self) -> None:
        if not self.project.cuts:
            QMessageBox.information(self, "Export", "No cuts to export.")
            return

        self.project.export_settings = self.settings_panel.export_settings()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Markers",
            "cutmarker_markers.csv",
            ";;".join(
                [
                    "CSV (*.csv)",
                    "EDL (*.edl)",
                    "Text Report (*.txt)",
                    "Tab Cue List for PTX converters (*.txt)",
                    "Session Info Text reference only (*.txt)",
                    "MIDI markers fallback not Absolute (*.mid)",
                ]
            ),
        )
        if not path:
            return

        path = Path(path)
        video = self.project.video
        cuts = self.project.cuts
        export = self.project.export_settings

        try:
            if "MIDI" in selected_filter:
                path = export_protools_midi_markers(path, cuts, video, export)
            elif "CSV" in selected_filter:
                if path.suffix.lower() != ".csv":
                    path = path.with_suffix(".csv")
                export_csv(path, cuts, video)
            elif "EDL" in selected_filter:
                if path.suffix.lower() != ".edl":
                    path = path.with_suffix(".edl")
                export_edl(path, cuts, video, title=export.session_name)
            elif "Tab Cue" in selected_filter:
                export_protools_tab(path, cuts, video, export)
            elif "Report" in selected_filter:
                export_text_report(path, cuts, video)
            elif "Session Info" in selected_filter:
                export_protools_session_text(path, cuts, video, export)
            else:
                if path.suffix.lower() != ".csv":
                    path = path.with_suffix(".csv")
                export_csv(path, cuts, video)

            if video and video.is_variable_frame_rate:
                QMessageBox.warning(
                    self,
                    "Variable frame rate",
                    "Source appears to be variable frame rate. Verify marker "
                    "positions against picture in Pro Tools.",
                )
            if (
                video
                and video.frame_rate
                and export.session_frame_rate
                and video.frame_rate.rate != export.session_frame_rate.rate
            ):
                QMessageBox.warning(
                    self,
                    "Frame rate mismatch",
                    "Source and Pro Tools session frame rates differ. Markers "
                    "were converted through exact seconds then rounded to the "
                    "nearest session frame.",
                )

            QMessageBox.information(
                self,
                "Export complete",
                f"Saved:\n{path}\n\n{IMPORT_INSTRUCTIONS}",
            )
            self.status_label.setText(f"Exported {len(cuts)} markers → {path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    # ----------------------------------------------------- Project I/O
    def save_project(self) -> None:
        if not self.project.video and not self.project.cuts:
            QMessageBox.information(self, "Save", "Nothing to save yet.")
            return
        self.project.detection_settings = self.settings_panel.detection_settings()
        self.project.export_settings = self.settings_panel.export_settings()
        path = self.project.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Project",
                "project.cutmarker.json",
                "CutMarker Project (*.cutmarker.json *.json)",
            )
            if not path:
                return
        try:
            saved = self.project.save(path)
            self.status_label.setText(f"Project saved: {saved}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "CutMarker Project (*.cutmarker.json *.json)",
        )
        if not path:
            return
        try:
            self.project = CutMarkerProject.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.settings_panel.set_detection_settings(self.project.detection_settings)
        self.settings_panel.set_export_settings(self.project.export_settings)
        if self.project.video:
            self.settings_panel.set_video_info(self.project.video)
            self.scene_list.set_video(self.project.video)
            video_path = Path(self.project.video.path)
            if video_path.is_file():
                try:
                    self.player.load_video(self.project.video)
                except Exception as exc:
                    QMessageBox.warning(self, "Preview", str(exc))
                self.timeline.set_total_frames(self.project.video.total_frames or 0)
            else:
                QMessageBox.warning(
                    self,
                    "Missing media",
                    f"Video file not found:\n{video_path}\n"
                    "Cut data was loaded; re-link the media to preview.",
                )
        self._refresh_cuts()
        self.status_label.setText(f"Opened project: {path}")
        self.btn_analyse.setEnabled(self.project.video is not None)

    def closeEvent(self, event) -> None:
        self.cancel_analysis()
        self.player.close_video()
        super().closeEvent(event)
