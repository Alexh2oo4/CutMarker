"""Video metadata via FFprobe (preferred) with OpenCV fallback."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cutmarker.core.frame_timing import FrameRate, snap_known_rate
from cutmarker.utils.ffmpeg import get_ffmpeg_path, get_ffprobe_path


SUPPORTED_EXTENSIONS = {
    ".mov",
    ".mp4",
    ".m4v",
    ".mxf",
    ".avi",
    ".mkv",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".webm",
    ".prores",  # rare extension; ProRes usually lives in .mov
}


@dataclass(slots=True)
class AudioTrackInfo:
    index: int
    codec: str = ""
    sample_rate: int | None = None
    channels: int | None = None
    language: str = ""
    bit_rate: int | None = None


@dataclass(slots=True)
class VideoMetadata:
    path: str
    filename: str
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str = ""
    pixel_format: str = ""
    frame_rate: FrameRate | None = None
    avg_frame_rate: FrameRate | None = None
    total_frames: int | None = None
    is_variable_frame_rate: bool = False
    start_timecode: str | None = None
    start_pts: float = 0.0
    bit_rate: int | None = None
    audio_tracks: list[AudioTrackInfo] = field(default_factory=list)
    raw_format_name: str = ""
    warnings: list[str] = field(default_factory=list)
    probe_backend: str = ""

    @property
    def resolution_label(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "Unknown"

    @property
    def fps_label(self) -> str:
        if self.frame_rate:
            vfr = " (VFR)" if self.is_variable_frame_rate else " (CFR)"
            return f"{self.frame_rate.display_label}{vfr}"
        return "Unknown"

    @property
    def duration_label(self) -> str:
        if self.duration_seconds is None:
            return "Unknown"
        total = int(round(self.duration_seconds))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.frame_rate:
            data["frame_rate"] = {
                "num": self.frame_rate.rate.numerator,
                "den": self.frame_rate.rate.denominator,
                "drop_frame": self.frame_rate.drop_frame,
                "label": self.frame_rate.label,
            }
        if self.avg_frame_rate:
            data["avg_frame_rate"] = {
                "num": self.avg_frame_rate.rate.numerator,
                "den": self.avg_frame_rate.rate.denominator,
                "drop_frame": self.avg_frame_rate.drop_frame,
                "label": self.avg_frame_rate.label,
            }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoMetadata:
        fr = data.get("frame_rate")
        avg = data.get("avg_frame_rate")
        audio = [
            AudioTrackInfo(**a) if isinstance(a, dict) else a
            for a in data.get("audio_tracks", [])
        ]
        meta = cls(
            path=data["path"],
            filename=data["filename"],
            duration_seconds=data.get("duration_seconds"),
            width=data.get("width"),
            height=data.get("height"),
            video_codec=data.get("video_codec", ""),
            pixel_format=data.get("pixel_format", ""),
            total_frames=data.get("total_frames"),
            is_variable_frame_rate=bool(data.get("is_variable_frame_rate")),
            start_timecode=data.get("start_timecode"),
            start_pts=float(data.get("start_pts") or 0.0),
            bit_rate=data.get("bit_rate"),
            audio_tracks=audio,
            raw_format_name=data.get("raw_format_name", ""),
            warnings=list(data.get("warnings") or []),
            probe_backend=data.get("probe_backend", ""),
        )
        if isinstance(fr, dict):
            meta.frame_rate = FrameRate.from_ratio(
                fr["num"], fr["den"], drop_frame=fr.get("drop_frame", False), label=fr.get("label", "")
            )
        if isinstance(avg, dict):
            meta.avg_frame_rate = FrameRate.from_ratio(
                avg["num"],
                avg["den"],
                drop_frame=avg.get("drop_frame", False),
                label=avg.get("label", ""),
            )
        return meta


def _parse_rate(rate_str: str | None) -> FrameRate | None:
    if not rate_str or rate_str in ("0/0", "N/A"):
        return None
    if "/" in rate_str:
        num_s, den_s = rate_str.split("/", 1)
        num, den = int(num_s), int(den_s)
        if den == 0 or num == 0:
            return None
        return snap_known_rate(num / den)
    return snap_known_rate(float(rate_str))


def _run_ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def _timecode_from_streams(streams: list[dict[str, Any]], fmt: dict[str, Any]) -> str | None:
    for stream in streams:
        tags = stream.get("tags") or {}
        for key in ("timecode", "TIMECODE"):
            if key in tags and tags[key]:
                return str(tags[key])
    tags = fmt.get("tags") or {}
    for key in ("timecode", "TIMECODE"):
        if key in tags and tags[key]:
            return str(tags[key])
    return None


def probe_with_ffprobe(path: Path) -> VideoMetadata:
    data = _run_ffprobe(path)
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise ValueError("No video stream found in file")

    vs = video_streams[0]
    r_frame = _parse_rate(vs.get("r_frame_rate"))
    avg_frame = _parse_rate(vs.get("avg_frame_rate"))
    # Prefer avg for display when they diverge significantly → VFR signal
    is_vfr = False
    warnings: list[str] = []
    if r_frame and avg_frame and r_frame.rate != avg_frame.rate:
        diff = abs(float(r_frame.rate) - float(avg_frame.rate))
        if diff > 0.05:
            is_vfr = True
            warnings.append(
                "Variable frame rate detected (r_frame_rate differs from avg_frame_rate). "
                "Cut timing uses presentation timestamps where available."
            )

    duration = None
    if fmt.get("duration"):
        duration = float(fmt["duration"])
    elif vs.get("duration"):
        duration = float(vs["duration"])

    total_frames = None
    if vs.get("nb_frames") and str(vs["nb_frames"]).isdigit():
        total_frames = int(vs["nb_frames"])
    elif duration is not None and avg_frame is not None and not is_vfr:
        total_frames = int(round(duration * float(avg_frame.rate)))

    frame_rate = avg_frame or r_frame
    if is_vfr and avg_frame:
        frame_rate = avg_frame

    audio_tracks = []
    for i, a in enumerate(audio_streams):
        audio_tracks.append(
            AudioTrackInfo(
                index=int(a.get("index", i)),
                codec=str(a.get("codec_name") or ""),
                sample_rate=int(a["sample_rate"]) if a.get("sample_rate") else None,
                channels=int(a["channels"]) if a.get("channels") else None,
                language=str((a.get("tags") or {}).get("language") or ""),
                bit_rate=int(a["bit_rate"]) if a.get("bit_rate") else None,
            )
        )

    bit_rate = int(fmt["bit_rate"]) if fmt.get("bit_rate") else None
    start_pts = float(vs.get("start_time") or fmt.get("start_time") or 0.0)

    return VideoMetadata(
        path=str(path.resolve()),
        filename=path.name,
        duration_seconds=duration,
        width=int(vs["width"]) if vs.get("width") else None,
        height=int(vs["height"]) if vs.get("height") else None,
        video_codec=str(vs.get("codec_name") or ""),
        pixel_format=str(vs.get("pix_fmt") or ""),
        frame_rate=frame_rate,
        avg_frame_rate=avg_frame,
        total_frames=total_frames,
        is_variable_frame_rate=is_vfr,
        start_timecode=_timecode_from_streams(streams, fmt),
        start_pts=start_pts,
        bit_rate=bit_rate,
        audio_tracks=audio_tracks,
        raw_format_name=str(fmt.get("format_name") or ""),
        warnings=warnings,
        probe_backend="ffprobe",
    )


def probe_with_opencv(path: Path) -> VideoMetadata:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open {path}")
    try:
        fps_val = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or None
        frame_rate = snap_known_rate(fps_val) if fps_val > 0 else None
        duration = None
        if total and frame_rate:
            duration = float(total) / float(frame_rate.rate)
        return VideoMetadata(
            path=str(path.resolve()),
            filename=path.name,
            duration_seconds=duration,
            width=width,
            height=height,
            video_codec="",
            frame_rate=frame_rate,
            avg_frame_rate=frame_rate,
            total_frames=total,
            is_variable_frame_rate=False,
            warnings=["Metadata from OpenCV fallback; prefer FFprobe for accuracy."],
            probe_backend="opencv",
        )
    finally:
        cap.release()


def probe_video(path: str | Path) -> VideoMetadata:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        # Still attempt probe — FFmpeg may decode it
        pass

    try:
        return probe_with_ffprobe(path)
    except FileNotFoundError:
        meta = probe_with_opencv(path)
        meta.warnings.append("FFprobe unavailable; using OpenCV metadata.")
        return meta
    except Exception as exc:
        try:
            meta = probe_with_opencv(path)
            meta.warnings.append(f"FFprobe failed ({exc}); using OpenCV metadata.")
            return meta
        except Exception as cv_exc:
            raise RuntimeError(f"Unable to read video metadata: {exc}") from cv_exc


def extract_frame_bgr(
    path: str | Path,
    frame_index: int,
    *,
    fps: FrameRate | None = None,
) -> Any:
    """Extract a single BGR frame by index using OpenCV seek."""
    import cv2
    import numpy as np

    path = Path(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Failed to read frame {frame_index}")
        return frame
    finally:
        cap.release()


def ensure_decodable(path: str | Path) -> None:
    """Quick open check via ffmpeg."""
    path = Path(path)
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg could not decode video")
