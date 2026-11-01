"""CMX 3600-style EDL export of cut points as single-frame events."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate, frame_to_timecode, timecode_to_frame
from cutmarker.core.video_metadata import VideoMetadata


def export_edl(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
    *,
    title: str = "CutMarker",
    start_timecode: str | None = None,
) -> Path:
    """Export an EDL where each event marks a cut (1-frame source/record)."""
    path = Path(path)
    fps = video.frame_rate if video and video.frame_rate else FrameRate.from_float(24.0)
    source_tc = start_timecode or (video.start_timecode if video else None) or "00:00:00:00"
    origin = timecode_to_frame(source_tc, fps) if source_tc else 0

    lines = [
        f"TITLE: {title}",
        f"FCM: {'DROP FRAME' if fps.drop_frame else 'NON-DROP FRAME'}",
        "",
    ]

    for i, cut in enumerate(cuts, start=1):
        abs_frame = origin + cut.frame_index
        tc_in = frame_to_timecode(abs_frame, fps)
        tc_out = frame_to_timecode(abs_frame + 1, fps)
        event = f"{i:03d}  AX       V     C        {tc_in} {tc_out} {tc_in} {tc_out}"
        lines.append(event)
        lines.append(f"* FROM CLIP NAME: {cut.marker_name()}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
