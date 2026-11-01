"""Left panel: video info, detection settings, export timing."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cutmarker.core.detection import DetectionSettings, SensitivityPreset
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata


COMMON_RATES = [
    ("23.976", FrameRate.from_float(23.976)),
    ("24", FrameRate.from_float(24)),
    ("25", FrameRate.from_float(25)),
    ("29.97", FrameRate.from_float(29.97)),
    ("29.97 DF", FrameRate.from_float(29.97, drop_frame=True)),
    ("30", FrameRate.from_float(30)),
    ("50", FrameRate.from_float(50)),
    ("59.94", FrameRate.from_float(59.94)),
    ("59.94 DF", FrameRate.from_float(59.94, drop_frame=True)),
    ("60", FrameRate.from_float(60)),
]

# Hover help shown when the "?" toggle is active (Detection + Pro Tools panels).
HELP_TEXTS: dict[str, str] = {
    "preset": (
        "Quick sensitivity profile. Sensitive finds more cuts (more false positives). "
        "Balanced is the default. Conservative finds fewer cuts (may miss soft transitions). "
        "Custom is set automatically when you change any value below."
    ),
    "content_threshold": (
        "How large a visual jump must be to count as a hard cut. "
        "Lower = more cuts detected. Higher = only stronger / clearer cuts."
    ),
    "adaptive_threshold": (
        "Adaptive detector sensitivity for lighting / camera changes that are not edits. "
        "Lower = more sensitive. Higher = stricter (fewer lighting false cuts)."
    ),
    "min_scene_len": (
        "Minimum length of a shot in frames. Cuts closer together than this are ignored. "
        "Helps reject flash frames and tiny blips."
    ),
    "downscale": (
        "Analysis resolution scale. 1 = full resolution (most accurate). "
        "2–8 = faster on long films, with slightly less precision on soft transitions."
    ),
    "use_content": (
        "Enables the content detector for abrupt hard cuts — the primary cut type "
        "for most dialogue and picture editorial."
    ),
    "use_adaptive": (
        "Extra detector that handles cuts involving lighting changes. Useful, but can "
        "add extra markers on heavy VFX or strobing."
    ),
    "detect_fades": (
        "Attempts to detect fades and dissolves, not only hard cuts. "
        "Less reliable than hard-cut detection; review results carefully."
    ),
    "suppress_flashes": (
        "Removes pairs of ultra-short ‘scenes’ typical of muzzle flashes, explosions, "
        "or intentional flash frames so they do not become SCENE markers."
    ),
    "session_name": (
        "Name written into the Pro Tools Session Info export header. "
        "Does not rename your existing Pro Tools session."
    ),
    "session_start": (
        "Timecode where picture / frame 0 of the video should land in Pro Tools. "
        "Defaults to 00:00:00:00. Change this if your session start differs."
    ),
    "session_fps": (
        "Must match your Pro Tools session frame rate (including DF vs NDF). "
        "Wrong rate places markers on the wrong frames."
    ),
    "sample_rate": (
        "Pro Tools session sample rate (usually 48000). Used for sample-position "
        "fields in the text export. Match your session."
    ),
    "warn": (
        "Before exporting, confirm session start timecode and frame rate match "
        "Pro Tools, or markers will not line up with picture."
    ),
}


class SettingsPanel(QWidget):
    settingsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)
        self._help_on = False
        self._help_targets: list[tuple[QWidget, str]] = []

        # --- Video info ---
        self.info_labels: dict[str, QLabel] = {}
        info_box = QGroupBox("Video information")
        info_form = QFormLayout(info_box)
        for key, title in [
            ("filename", "Filename"),
            ("duration", "Duration"),
            ("resolution", "Resolution"),
            ("codec", "Codec"),
            ("fps", "Frame rate"),
            ("frames", "Total frames"),
            ("vfr", "Rate mode"),
            ("start_tc", "Source TC"),
            ("audio", "Audio"),
        ]:
            lab = QLabel("—")
            lab.setWordWrap(True)
            self.info_labels[key] = lab
            info_form.addRow(title, lab)

        # --- Detection ---
        det_box = QGroupBox("Detection settings")
        det_form = QFormLayout(det_box)

        self.preset = QComboBox()
        # Store plain strings — Qt can coerce str-Enums to str via userData.
        self.preset.addItem("Sensitive", SensitivityPreset.SENSITIVE.value)
        self.preset.addItem("Balanced", SensitivityPreset.BALANCED.value)
        self.preset.addItem("Conservative", SensitivityPreset.CONSERVATIVE.value)
        self.preset.addItem("Custom", SensitivityPreset.CUSTOM.value)
        self.preset.setCurrentIndex(1)
        self.preset.currentIndexChanged.connect(self._on_preset)

        self.content_threshold = QDoubleSpinBox()
        self.content_threshold.setRange(5.0, 80.0)
        self.content_threshold.setSingleStep(0.5)
        self.content_threshold.setValue(27.0)

        self.adaptive_threshold = QDoubleSpinBox()
        self.adaptive_threshold.setRange(0.5, 20.0)
        self.adaptive_threshold.setSingleStep(0.1)
        self.adaptive_threshold.setValue(3.0)

        self.min_scene_len = QSpinBox()
        self.min_scene_len.setRange(1, 120)
        self.min_scene_len.setValue(8)

        self.downscale = QSpinBox()
        self.downscale.setRange(1, 8)
        self.downscale.setValue(1)

        self.detect_fades = QCheckBox("Detect fades / dissolves")
        self.detect_fades.setChecked(True)
        self.suppress_flashes = QCheckBox("Suppress flash-like cuts")
        self.suppress_flashes.setChecked(True)
        self.use_content = QCheckBox("Content detector (hard cuts)")
        self.use_content.setChecked(True)
        self.use_adaptive = QCheckBox("Adaptive detector (lighting)")
        self.use_adaptive.setChecked(True)

        for w in (
            self.content_threshold,
            self.adaptive_threshold,
            self.min_scene_len,
            self.downscale,
        ):
            w.valueChanged.connect(self._mark_custom)
        for w in (
            self.detect_fades,
            self.suppress_flashes,
            self.use_content,
            self.use_adaptive,
        ):
            w.toggled.connect(self._mark_custom)

        self._preset_label = QLabel("Preset")
        self._content_label = QLabel("Content threshold")
        self._adaptive_label = QLabel("Adaptive threshold")
        self._min_len_label = QLabel("Min scene length")
        self._downscale_label = QLabel("Downscale")

        det_form.addRow(self._preset_label, self.preset)
        det_form.addRow(self._content_label, self.content_threshold)
        det_form.addRow(self._adaptive_label, self.adaptive_threshold)
        det_form.addRow(self._min_len_label, self.min_scene_len)
        det_form.addRow(self._downscale_label, self.downscale)
        det_form.addRow(self.use_content)
        det_form.addRow(self.use_adaptive)
        det_form.addRow(self.detect_fades)
        det_form.addRow(self.suppress_flashes)

        # --- Export / session ---
        exp_box = QGroupBox("Pro Tools session")
        exp_form = QFormLayout(exp_box)
        self.session_name = QLineEdit("CutMarker_Export")
        self.session_start = QLineEdit("00:00:00:00")
        self.session_fps = QComboBox()
        for label, _fr in COMMON_RATES:
            self.session_fps.addItem(label)
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["48000", "44100", "96000"])

        self._session_name_label = QLabel("Session name")
        self._session_start_label = QLabel("Session start TC")
        self._session_fps_label = QLabel("Session frame rate")
        self._sample_rate_label = QLabel("Sample rate")

        exp_form.addRow(self._session_name_label, self.session_name)
        exp_form.addRow(self._session_start_label, self.session_start)
        exp_form.addRow(self._session_fps_label, self.session_fps)
        exp_form.addRow(self._sample_rate_label, self.sample_rate)

        self.warn = QLabel(
            "Match session start and frame rate to your Pro Tools session "
            "before exporting markers."
        )
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet("color:#ce9178;")
        exp_form.addRow(self.warn)

        self._register_help()

        # Help toggle
        help_row = QHBoxLayout()
        self.btn_help = QPushButton("?")
        self.btn_help.setCheckable(True)
        self.btn_help.setFixedWidth(36)
        self.btn_help.setToolTip(
            "Toggle help mode. When on, hover over Detection and Pro Tools "
            "controls for explanations."
        )
        self.btn_help.toggled.connect(self._on_help_toggled)
        self.help_status = QLabel("Help off — click ? to enable hover tips")
        self.help_status.setStyleSheet("color:#888;")
        help_row.addWidget(self.btn_help)
        help_row.addWidget(self.help_status, stretch=1)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.addLayout(help_row)
        inner_layout.addWidget(info_box)
        inner_layout.addWidget(det_box)
        inner_layout.addWidget(exp_box)
        inner_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _register_help(self) -> None:
        pairs = [
            (self.preset, "preset"),
            (self._preset_label, "preset"),
            (self.content_threshold, "content_threshold"),
            (self._content_label, "content_threshold"),
            (self.adaptive_threshold, "adaptive_threshold"),
            (self._adaptive_label, "adaptive_threshold"),
            (self.min_scene_len, "min_scene_len"),
            (self._min_len_label, "min_scene_len"),
            (self.downscale, "downscale"),
            (self._downscale_label, "downscale"),
            (self.use_content, "use_content"),
            (self.use_adaptive, "use_adaptive"),
            (self.detect_fades, "detect_fades"),
            (self.suppress_flashes, "suppress_flashes"),
            (self.session_name, "session_name"),
            (self._session_name_label, "session_name"),
            (self.session_start, "session_start"),
            (self._session_start_label, "session_start"),
            (self.session_fps, "session_fps"),
            (self._session_fps_label, "session_fps"),
            (self.sample_rate, "sample_rate"),
            (self._sample_rate_label, "sample_rate"),
            (self.warn, "warn"),
        ]
        self._help_targets = [(w, HELP_TEXTS[key]) for w, key in pairs]

    def _on_help_toggled(self, on: bool) -> None:
        self._help_on = on
        if on:
            self.help_status.setText("Help on — hover a setting for its explanation")
            self.help_status.setStyleSheet("color:#4ec9b0;")
            for widget, text in self._help_targets:
                widget.setToolTip(text)
        else:
            self.help_status.setText("Help off — click ? to enable hover tips")
            self.help_status.setStyleSheet("color:#888;")
            for widget, _text in self._help_targets:
                widget.setToolTip("")

    def set_video_info(self, video: VideoMetadata | None) -> None:
        if not video:
            for lab in self.info_labels.values():
                lab.setText("—")
            return
        audio = "None"
        if video.audio_tracks:
            parts = []
            for a in video.audio_tracks:
                ch = f"{a.channels}ch" if a.channels else "?"
                sr = f"{a.sample_rate} Hz" if a.sample_rate else ""
                parts.append(f"{a.codec} {ch} {sr}".strip())
            audio = "; ".join(parts)
        self.info_labels["filename"].setText(video.filename)
        self.info_labels["duration"].setText(video.duration_label)
        self.info_labels["resolution"].setText(video.resolution_label)
        self.info_labels["codec"].setText(video.video_codec or "—")
        self.info_labels["fps"].setText(video.fps_label)
        self.info_labels["frames"].setText(
            str(video.total_frames) if video.total_frames is not None else "—"
        )
        self.info_labels["vfr"].setText(
            "Variable" if video.is_variable_frame_rate else "Constant"
        )
        self.info_labels["start_tc"].setText(video.start_timecode or "00:00:00:00")
        self.info_labels["audio"].setText(audio)

        if video.frame_rate:
            target = video.frame_rate.display_label
            for i in range(self.session_fps.count()):
                if self.session_fps.itemText(i).startswith(target.split()[0]):
                    self.session_fps.setCurrentIndex(i)
                    break

    def _current_preset(self) -> SensitivityPreset:
        raw = self.preset.currentData()
        if isinstance(raw, SensitivityPreset):
            return raw
        try:
            return SensitivityPreset(str(raw))
        except ValueError:
            return SensitivityPreset.CUSTOM

    def detection_settings(self) -> DetectionSettings:
        return DetectionSettings(
            preset=self._current_preset(),
            content_threshold=self.content_threshold.value(),
            adaptive_threshold=self.adaptive_threshold.value(),
            min_scene_len=self.min_scene_len.value(),
            detect_fades=self.detect_fades.isChecked(),
            suppress_flashes=self.suppress_flashes.isChecked(),
            downscale=self.downscale.value(),
            use_content=self.use_content.isChecked(),
            use_adaptive=self.use_adaptive.isChecked(),
        )

    def set_detection_settings(self, settings: DetectionSettings) -> None:
        key = (
            settings.preset.value
            if isinstance(settings.preset, SensitivityPreset)
            else str(settings.preset)
        )
        idx = self.preset.findData(key)
        if idx >= 0:
            self.preset.setCurrentIndex(idx)
        self.content_threshold.setValue(settings.content_threshold)
        self.adaptive_threshold.setValue(settings.adaptive_threshold)
        self.min_scene_len.setValue(settings.min_scene_len)
        self.downscale.setValue(settings.downscale)
        self.detect_fades.setChecked(settings.detect_fades)
        self.suppress_flashes.setChecked(settings.suppress_flashes)
        self.use_content.setChecked(settings.use_content)
        self.use_adaptive.setChecked(settings.use_adaptive)

    def export_settings(self) -> ExportSettings:
        label = self.session_fps.currentText()
        fps = FrameRate.from_float(24.0)
        for name, fr in COMMON_RATES:
            if name == label:
                fps = fr
                break
        return ExportSettings(
            session_frame_rate=fps,
            session_start_timecode=self.session_start.text().strip() or "00:00:00:00",
            session_drop_frame=fps.drop_frame,
            sample_rate=int(self.sample_rate.currentText()),
            session_name=self.session_name.text().strip() or "CutMarker_Export",
        )

    def set_export_settings(self, settings: ExportSettings) -> None:
        self.session_name.setText(settings.session_name)
        self.session_start.setText(settings.session_start_timecode)
        if settings.session_frame_rate:
            label = settings.session_frame_rate.display_label
            if settings.session_frame_rate.drop_frame and "DF" not in label:
                label = f"{label} DF"
            for i in range(self.session_fps.count()):
                if self.session_fps.itemText(i) == label or self.session_fps.itemText(i).startswith(
                    settings.session_frame_rate.label
                ):
                    self.session_fps.setCurrentIndex(i)
                    break
        idx = self.sample_rate.findText(str(settings.sample_rate))
        if idx >= 0:
            self.sample_rate.setCurrentIndex(idx)

    def _on_preset(self) -> None:
        preset = self._current_preset()
        if preset == SensitivityPreset.CUSTOM:
            return
        settings = DetectionSettings.from_preset(preset)
        self.content_threshold.blockSignals(True)
        self.adaptive_threshold.blockSignals(True)
        self.min_scene_len.blockSignals(True)
        self.content_threshold.setValue(settings.content_threshold)
        self.adaptive_threshold.setValue(settings.adaptive_threshold)
        self.min_scene_len.setValue(settings.min_scene_len)
        self.detect_fades.setChecked(settings.detect_fades)
        self.suppress_flashes.setChecked(settings.suppress_flashes)
        self.content_threshold.blockSignals(False)
        self.adaptive_threshold.blockSignals(False)
        self.min_scene_len.blockSignals(False)
        self.settingsChanged.emit()

    def _mark_custom(self, *_args) -> None:
        if self._current_preset() != SensitivityPreset.CUSTOM:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(
                self.preset.findData(SensitivityPreset.CUSTOM.value)
            )
            self.preset.blockSignals(False)
        self.settingsChanged.emit()
