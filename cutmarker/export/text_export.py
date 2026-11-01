"""Plain-text analysis report."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.video_metadata import VideoMetadata
from cutmarker.export.protools import IMPORT_INSTRUCTIONS


def export_text_report(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
) -> Path:
    path = Path(path)
    fps = video.frame_rate if video and video.frame_rate else FrameRate.from_float(24.0)
    source_tc = video.start_timecode if video else None

    lines: list[str] = []
    lines.append("CutMarker Analysis Report")
    lines.append("=" * 40)
    if video:
        lines.append(f"File:           {video.filename}")
        lines.append(f"Path:           {video.path}")
        lines.append(f"Duration:       {video.duration_label}")
        lines.append(f"Resolution:     {video.resolution_label}")
        lines.append(f"Codec:          {video.video_codec}")
        lines.append(f"Frame rate:     {video.fps_label}")
        lines.append(f"Total frames:   {video.total_frames}")
        lines.append(f"Start timecode: {video.start_timecode or 'n/a'}")
        if video.warnings:
            lines.append("Warnings:")
            for w in video.warnings:
                lines.append(f"  - {w}")
    lines.append("")
    lines.append(f"Detected scenes: {len(cuts)}")
    lines.append("-" * 40)
    lines.append(f"{'#':>5}  {'Frame':>10}  {'Timecode':>14}  {'Source':>8}  Name")
    for cut in cuts:
        lines.append(
            f"{cut.scene_number:5d}  {cut.frame_index:10d}  "
            f"{cut.timecode(fps, start_timecode=source_tc):>14}  "
            f"{cut.source:>8}  {cut.marker_name()}"
        )
    lines.append("")
    lines.append(IMPORT_INSTRUCTIONS)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
