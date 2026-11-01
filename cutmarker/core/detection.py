"""Scene-cut detection engine built on PySceneDetect with flash suppression."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from cutmarker.core.cuts import CutList

logger = logging.getLogger(__name__)


class SensitivityPreset(str, Enum):
    SENSITIVE = "sensitive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    CUSTOM = "custom"


@dataclass(slots=True)
class DetectionSettings:
    """User-facing detection parameters."""

    preset: SensitivityPreset = SensitivityPreset.BALANCED
    # ContentDetector threshold (lower = more cuts)
    content_threshold: float = 27.0
    # AdaptiveDetector adaptive threshold
    adaptive_threshold: float = 3.0
    # Minimum scene length in frames (helps reject flashes)
    min_scene_len: int = 8
    # Detect fades/dissolves via ThresholdDetector / luma
    detect_fades: bool = True
    fade_threshold: float = 12.0
    # Flash / muzzle-flash suppression: reject cuts that revert quickly
    suppress_flashes: bool = True
    flash_max_duration_frames: int = 4
    # Downscale factor for analysis (1 = full resolution). 2–4 speeds up long films.
    # Accuracy note: hard cuts remain reliable at 2; fades prefer 1.
    downscale: int = 1
    # Use AdaptiveDetector (better for lighting changes) in addition to ContentDetector
    use_adaptive: bool = True
    use_content: bool = True

    def apply_preset(self, preset: SensitivityPreset) -> None:
        self.preset = preset
        if preset == SensitivityPreset.SENSITIVE:
            self.content_threshold = 22.0
            self.adaptive_threshold = 2.5
            self.min_scene_len = 6
            self.fade_threshold = 10.0
            self.flash_max_duration_frames = 3
        elif preset == SensitivityPreset.BALANCED:
            self.content_threshold = 27.0
            self.adaptive_threshold = 3.0
            self.min_scene_len = 8
            self.fade_threshold = 12.0
            self.flash_max_duration_frames = 4
        elif preset == SensitivityPreset.CONSERVATIVE:
            self.content_threshold = 35.0
            self.adaptive_threshold = 4.0
            self.min_scene_len = 12
            self.fade_threshold = 15.0
            self.flash_max_duration_frames = 5
        # CUSTOM leaves numeric fields as-is

    def to_dict(self) -> dict:
        # QComboBox / JSON may leave preset as a plain str; tolerate both.
        preset = (
            self.preset.value
            if isinstance(self.preset, SensitivityPreset)
            else str(self.preset)
        )
        return {
            "preset": preset,
            "content_threshold": self.content_threshold,
            "adaptive_threshold": self.adaptive_threshold,
            "min_scene_len": self.min_scene_len,
            "detect_fades": self.detect_fades,
            "fade_threshold": self.fade_threshold,
            "suppress_flashes": self.suppress_flashes,
            "flash_max_duration_frames": self.flash_max_duration_frames,
            "downscale": self.downscale,
            "use_adaptive": self.use_adaptive,
            "use_content": self.use_content,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DetectionSettings:
        settings = cls()
        preset = data.get("preset", SensitivityPreset.BALANCED.value)
        try:
            settings.preset = SensitivityPreset(preset)
        except ValueError:
            settings.preset = SensitivityPreset.CUSTOM
        for key in (
            "content_threshold",
            "adaptive_threshold",
            "min_scene_len",
            "detect_fades",
            "fade_threshold",
            "suppress_flashes",
            "flash_max_duration_frames",
            "downscale",
            "use_adaptive",
            "use_content",
        ):
            if key in data:
                setattr(settings, key, data[key])
        return settings

    @classmethod
    def from_preset(cls, preset: SensitivityPreset) -> DetectionSettings:
        s = cls()
        s.apply_preset(preset)
        return s


@dataclass(slots=True)
class DetectionProgress:
    current_frame: int = 0
    total_frames: int | None = None
    percent: float = 0.0
    message: str = ""
    cancelled: bool = False
    elapsed_seconds: float | None = None
    eta_seconds: float | None = None
    frames_per_second: float | None = None
    device: str = "CPU"


def format_duration(seconds: float | None) -> str:
    """Human-readable duration for ETA / elapsed display."""
    if seconds is None or seconds < 0 or seconds != seconds:  # NaN
        return "—"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


ProgressCallback = Callable[[DetectionProgress], None]
CancelCallback = Callable[[], bool]


@dataclass
class DetectionResult:
    cut_list: CutList
    raw_cut_frames: list[int] = field(default_factory=list)
    filtered_flash_frames: list[int] = field(default_factory=list)
    backend: str = "pyscenedetect"
    settings: DetectionSettings | None = None
    warnings: list[str] = field(default_factory=list)


def _suppress_flash_cuts(
    cut_frames: list[int],
    max_duration: int,
) -> tuple[list[int], list[int]]:
    """Remove pairs of cuts that bound an ultra-short 'scene' (likely a flash).

    If two consecutive cut points are closer than ``max_duration`` frames,
    drop the later cut (return-from-flash). The earlier cut is also dropped
    when the prior scene would also be abnormally short — both ends of a flash.
    """
    if max_duration <= 0 or len(cut_frames) < 2:
        return cut_frames, []

    frames = sorted(set(cut_frames))
    rejected: list[int] = []
    keep: list[int] = []
    i = 0
    while i < len(frames):
        if i + 1 < len(frames) and (frames[i + 1] - frames[i]) <= max_duration:
            # Flash pulse: drop both boundaries of the micro-scene
            rejected.extend([frames[i], frames[i + 1]])
            i += 2
            continue
        keep.append(frames[i])
        i += 1
    return keep, rejected


def detect_cuts(
    video_path: str | Path,
    settings: DetectionSettings | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
    start_in_scene: bool = True,
) -> DetectionResult:
    """Analyse ``video_path`` and return a renumbered CutList.

    Uses PySceneDetect ContentDetector and/or AdaptiveDetector. Frame indices
    are taken from PySceneDetect's FrameTimecode and refer to the first frame
    of each new scene (the cut frame itself).
    """
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import AdaptiveDetector, ContentDetector, ThresholdDetector

    video_path = Path(video_path)
    settings = settings or DetectionSettings.from_preset(SensitivityPreset.BALANCED)
    warnings: list[str] = []

    video = open_video(str(video_path))
    total_frames = None
    try:
        duration = video.duration
        if duration is not None:
            frame_num = getattr(duration, "frame_num", None)
            total_frames = int(
                frame_num if frame_num is not None else duration.get_frames()
            )
    except Exception:
        total_frames = None

    scene_manager = SceneManager()
    if settings.downscale and settings.downscale > 1:
        scene_manager.auto_downscale = False
        scene_manager.downscale = settings.downscale
    else:
        # Prefer full-resolution analysis for professional accuracy
        scene_manager.auto_downscale = False
        scene_manager.downscale = 1

    if settings.use_content:
        scene_manager.add_detector(
            ContentDetector(
                threshold=settings.content_threshold,
                min_scene_len=settings.min_scene_len,
            )
        )
    if settings.use_adaptive:
        scene_manager.add_detector(
            AdaptiveDetector(
                adaptive_threshold=settings.adaptive_threshold,
                min_scene_len=settings.min_scene_len,
            )
        )
    if settings.detect_fades:
        # ThresholdDetector catches fades to/from black
        scene_manager.add_detector(
            ThresholdDetector(
                threshold=settings.fade_threshold,
                min_scene_len=settings.min_scene_len,
            )
        )

    if not settings.use_content and not settings.use_adaptive and not settings.detect_fades:
        scene_manager.add_detector(
            ContentDetector(
                threshold=settings.content_threshold,
                min_scene_len=settings.min_scene_len,
            )
        )
        warnings.append("No detector enabled; fell back to ContentDetector.")

    cancelled = False
    # PySceneDetect + OpenCV decode/analyse on CPU in this build (no CUDA path).
    analysis_device = "CPU"
    started_at = time.perf_counter()
    last_emit_at = 0.0
    last_emit_frame = -1

    def _build_progress(
        current: int,
        *,
        percent: float,
        message: str,
        cancelled_flag: bool = False,
    ) -> DetectionProgress:
        # Elapsed display is owned by the UI wall-clock timer so it updates smoothly.
        # Here we only report frame position + rate-based ETA fields.
        elapsed = time.perf_counter() - started_at
        fps = (current / elapsed) if elapsed > 0.5 and current > 0 else None
        eta = None
        if fps and total_frames and current < total_frames:
            remaining = max(0, total_frames - current)
            eta = remaining / fps
        return DetectionProgress(
            current_frame=current,
            total_frames=total_frames,
            percent=percent,
            message=message,
            cancelled=cancelled_flag,
            elapsed_seconds=elapsed,
            eta_seconds=eta,
            frames_per_second=fps,
            device=analysis_device,
        )

    def _frame_callback(frame_img, frame_tc) -> None:
        nonlocal cancelled, last_emit_at, last_emit_frame
        current = int(getattr(frame_tc, "frame_num", 0))
        if cancel_callback and cancel_callback():
            cancelled = True
            try:
                scene_manager.stop()
            except Exception:
                pass
            if progress_callback:
                progress_callback(
                    _build_progress(
                        current,
                        percent=0.0,
                        message="Cancelling…",
                        cancelled_flag=True,
                    )
                )
            return
        if not progress_callback:
            return
        now = time.perf_counter()
        # Throttle UI updates (~4/sec or every 24 frames) to keep analysis responsive.
        if (
            current - last_emit_frame < 24
            and (now - last_emit_at) < 0.25
            and total_frames
            and current < total_frames - 1
        ):
            return
        last_emit_at = now
        last_emit_frame = current
        tot = total_frames
        pct = (100.0 * current / tot) if tot else 0.0
        progress_callback(
            _build_progress(
                current,
                percent=min(99.0, pct),
                message=f"Analysing frame {current}"
                + (f" / {tot}" if tot else ""),
            )
        )

    scene_manager.detect_scenes(
        video=video,
        callback=_frame_callback,
        show_progress=False,
    )

    if cancelled:
        warnings.append("Analysis was cancelled; results may be incomplete.")

    scene_list = scene_manager.get_scene_list(start_in_scene=start_in_scene)
    # Each scene is (start FrameTimecode, end FrameTimecode)
    # Cut frames = start frame of each scene
    raw_frames: list[int] = []
    for start, _end in scene_list:
        frame_num = getattr(start, "frame_num", None)
        if frame_num is None:
            frame_num = start.get_frames()
        raw_frames.append(int(frame_num))

    raw_frames = sorted(set(raw_frames))
    filtered_flash: list[int] = []
    frames = raw_frames
    if settings.suppress_flashes:
        frames, filtered_flash = _suppress_flash_cuts(
            raw_frames, settings.flash_max_duration_frames
        )
        if filtered_flash:
            warnings.append(
                f"Suppressed {len(filtered_flash)} flash-like cut(s) "
                f"(micro-scenes ≤ {settings.flash_max_duration_frames} frames)."
            )

    cut_list = CutList()
    cut_list.set_from_frames(frames, include_start=True, source="auto")

    if progress_callback:
        elapsed = time.perf_counter() - started_at
        progress_callback(
            DetectionProgress(
                current_frame=total_frames or 0,
                total_frames=total_frames,
                percent=100.0,
                message=(
                    f"Found {len(cut_list)} scene(s) in {format_duration(elapsed)} "
                    f"({analysis_device})"
                ),
                cancelled=cancelled,
                elapsed_seconds=elapsed,
                eta_seconds=0.0,
                frames_per_second=(
                    ((total_frames or 0) / elapsed) if elapsed > 0 else None
                ),
                device=analysis_device,
            )
        )

    return DetectionResult(
        cut_list=cut_list,
        raw_cut_frames=raw_frames,
        filtered_flash_frames=filtered_flash,
        backend="pyscenedetect",
        settings=settings,
        warnings=warnings,
    )
