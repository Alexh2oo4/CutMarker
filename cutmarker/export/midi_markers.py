"""Write a Type-0 Standard MIDI File with marker meta-events.

Pro Tools can import these via File → Import → MIDI (destination: Clip List).
This is the reliable built-in route without writing proprietary .ptx files.

Session Info Text cannot be opened with Import Session Data — that dialog
expects a real Pro Tools session (.ptx / .pts).
"""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import (
    FrameRate,
    frame_to_seconds,
    map_source_frame_to_session_frame,
    timecode_to_frame,
)
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata

# At 60 BPM, one quarter-note = one second; ticks ≈ milliseconds with PPQN=1000
PPQN = 1000
TEMPO_BPM = 60.0


def vlq_encode(value: int) -> bytes:
    """Encode a non-negative integer as a MIDI variable-length quantity."""
    if value < 0:
        raise ValueError("VLQ value must be >= 0")
    pieces = [value & 0x7F]
    value >>= 7
    while value:
        pieces.append(0x80 | (value & 0x7F))
        value >>= 7
    pieces.reverse()
    return bytes(pieces)


def _marker_event(name: str) -> bytes:
    text = name.encode("ascii", errors="replace")[:127]
    return bytes([0xFF, 0x06]) + vlq_encode(len(text)) + text


def _tempo_event(bpm: float = TEMPO_BPM) -> bytes:
    us_per_beat = int(round(60_000_000 / bpm))
    return bytes(
        [
            0xFF,
            0x51,
            0x03,
            (us_per_beat >> 16) & 0xFF,
            (us_per_beat >> 8) & 0xFF,
            us_per_beat & 0xFF,
        ]
    )


def _seconds_to_ticks(seconds: float) -> int:
    return max(0, int(round(seconds * PPQN)))


def _session_fps(export: ExportSettings, video: VideoMetadata | None) -> FrameRate:
    if export.session_frame_rate:
        fps = export.session_frame_rate
    elif video and video.frame_rate:
        fps = video.frame_rate
    else:
        fps = FrameRate.from_float(24.0)
    if export.session_drop_frame and fps.supports_drop_frame:
        return FrameRate(rate=fps.rate, drop_frame=True, label=fps.label)
    return fps


def export_protools_midi_markers(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
    export: ExportSettings,
) -> Path:
    """Export a Type-0 .mid with one marker per cut for Pro Tools MIDI import."""
    path = Path(path)
    if path.suffix.lower() != ".mid":
        path = path.with_suffix(".mid")

    session_fps = _session_fps(export, video)
    source_fps = video.frame_rate if video and video.frame_rate else session_fps
    session_origin = timecode_to_frame(export.session_start_timecode, session_fps)

    events: list[tuple[int, str]] = []
    for cut in cuts:
        if video and video.is_variable_frame_rate and cut.pts_seconds is not None:
            session_frame = map_source_frame_to_session_frame(
                cut.frame_index,
                source_fps=source_fps,
                session_fps=session_fps,
                session_start_tc=export.session_start_timecode,
                vfr_pts_seconds=cut.pts_seconds,
            )
        else:
            session_frame = map_source_frame_to_session_frame(
                cut.frame_index,
                source_fps=source_fps,
                session_fps=session_fps,
                session_start_tc=export.session_start_timecode,
            )
        rel_frames = max(0, session_frame - session_origin)
        seconds = float(frame_to_seconds(rel_frames, session_fps))
        events.append((_seconds_to_ticks(seconds), cut.marker_name()))

    events.sort(key=lambda item: item[0])

    track = bytearray()
    track += vlq_encode(0)
    track += _tempo_event(TEMPO_BPM)
    track += vlq_encode(0)
    track += bytes([0xFF, 0x58, 0x04, 0x04, 0x02, 0x18, 0x08])  # 4/4

    last_tick = 0
    for tick, name in events:
        delta = max(0, tick - last_tick)
        track += vlq_encode(delta)
        track += _marker_event(name)
        last_tick = tick

    track += vlq_encode(0)
    track += bytes([0xFF, 0x2F, 0x00])

    header = (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")  # format 0
        + (1).to_bytes(2, "big")  # one track
        + int(PPQN).to_bytes(2, "big")
    )
    track_chunk = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + track_chunk)
    return path
