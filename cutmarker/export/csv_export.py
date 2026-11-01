"""CSV marker export."""

from __future__ import annotations

import csv
from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate, frame_to_timecode
from cutmarker.core.video_metadata import VideoMetadata


def export_csv(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
    *,
    start_timecode: str | None = None,
) -> Path:
    path = Path(path)
    fps = video.frame_rate if video and video.frame_rate else FrameRate.from_float(24.0)
    source_tc = start_timecode or (video.start_timecode if video else None)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "Scene Number",
                "Marker Name",
                "Frame Number",
                "Source Timecode",
                "Timestamp",
                "Frame Rate",
            ]
        )
        for cut in cuts:
            writer.writerow(
                [
                    cut.scene_number,
                    cut.marker_name(),
                    cut.frame_index,
                    cut.timecode(fps, start_timecode=source_tc),
                    f"{cut.timestamp_seconds(fps):.6f}",
                    fps.display_label,
                ]
            )
    return path
