"""Pro Tools-compatible marker export.

Import Session Data only accepts real Pro Tools sessions (.ptx / .pts).
It does **not** accept Session Info Text — that format is export-only from Pro Tools.

Reliable built-in route implemented here:
  • Type-0 MIDI (.mid) with marker meta-events
    → File → Import → MIDI → destination: Clip List

Also still writes:
  • Session Info–style .txt (reference / third-party converters)
  • Tab cue list for EdiMarker / Marker Converter → PTX workflows
"""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import (
    FrameRate,
    frame_to_seconds,
    frame_to_timecode,
    map_source_frame_to_session_frame,
    timecode_to_frame,
    validate_constant_mapping,
)
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata
from cutmarker.export.midi_markers import export_protools_midi_markers

__all__ = [
    "IMPORT_INSTRUCTIONS",
    "export_protools_midi_markers",
    "export_protools_session_text",
    "export_protools_tab",
]


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


def _tc_format_label(fps: FrameRate) -> str:
    mapping = {
        (24000, 1001): "23.976 Frame",
        (24, 1): "24 Frame",
        (25, 1): "25 Frame",
        (30000, 1001): "29.97 Frame" if not fps.drop_frame else "29.97 Drop Frame",
        (30, 1): "30 Frame",
        (50, 1): "50 Frame",
        (60000, 1001): "59.94 Frame" if not fps.drop_frame else "59.94 Drop Frame",
        (60, 1): "60 Frame",
    }
    key = (fps.rate.numerator, fps.rate.denominator)
    if key in mapping:
        return mapping[key]
    return f"{float(fps.rate):.3f} Frame"


def export_protools_session_text(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
    export: ExportSettings,
    *,
    source_start_timecode: str | None = None,
) -> Path:
    """Write a Session Info–style text file (reference / converters — not Import Session Data)."""
    path = Path(path)
    session_fps = _session_fps(export, video)
    source_fps = video.frame_rate if video and video.frame_rate else session_fps
    source_tc = (
        source_start_timecode or (video.start_timecode if video else None) or "00:00:00:00"
    )

    exact, warning = validate_constant_mapping(source_fps, session_fps)
    lines: list[str] = []
    lines.append(f"SESSION NAME:\t{export.session_name}")
    lines.append(f"SAMPLE RATE:\t{export.sample_rate:.6f}")
    lines.append(f"BIT DEPTH:\t{export.bit_depth}-bit")
    lines.append(f"SESSION START TIMECODE:\t{export.session_start_timecode}")
    lines.append(f"TIMECODE FORMAT:\t{_tc_format_label(session_fps)}")
    lines.append("# OF AUDIO TRACKS:\t0")
    lines.append("# OF AUDIO CLIPS:\t0")
    lines.append("# OF AUDIO FILES:\t0")
    lines.append("")
    lines.append(
        "# NOTE: Pro Tools cannot Import Session Data from this text file. "
        "Use CutMarker's MIDI (.mid) export, or convert this file with EdiMarker / "
        "Marker Converter to a .ptx first."
    )
    lines.append("")
    if not exact:
        lines.append(f"# WARNING: {warning}")
        lines.append("")
    if video and video.is_variable_frame_rate:
        lines.append(
            "# WARNING: Source is variable frame rate. Marker positions use "
            "presentation timestamps where available; verify against picture."
        )
        lines.append("")

    lines.append("M A R K E R S  L I S T I N G")
    lines.append(
        "#\tLOCATION\tTIME REFERENCE\tUNITS\tNAME\tTRACK NAME\tTRACK TYPE\tCOMMENTS"
    )

    session_origin = timecode_to_frame(export.session_start_timecode, session_fps)

    for cut in cuts:
        if video and video.is_variable_frame_rate and cut.pts_seconds is not None:
            session_frame = map_source_frame_to_session_frame(
                cut.frame_index,
                source_fps=source_fps,
                session_fps=session_fps,
                session_start_tc=export.session_start_timecode,
                source_start_tc=source_tc,
                vfr_pts_seconds=cut.pts_seconds,
            )
        else:
            session_frame = map_source_frame_to_session_frame(
                cut.frame_index,
                source_fps=source_fps,
                session_fps=session_fps,
                session_start_tc=export.session_start_timecode,
                source_start_tc="00:00:00:00",
            )

        location = frame_to_timecode(
            session_frame - session_origin,
            session_fps,
            start_timecode=export.session_start_timecode,
        )
        seconds = float(frame_to_seconds(session_frame - session_origin, session_fps))
        samples = int(round(seconds * export.sample_rate))
        name = cut.marker_name()
        comment = cut.notes or f"source_frame={cut.frame_index}"
        lines.append(
            f"{cut.scene_number}\t{location}\t{samples}\tSamples\t{name}\tMarkers\tRuler\t{comment}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_protools_tab(
    path: str | Path,
    cuts: CutList,
    video: VideoMetadata | None,
    export: ExportSettings,
) -> Path:
    """Tab-delimited Name / Timecode / Comments for EdiMarker-style tools."""
    path = Path(path)
    session_fps = _session_fps(export, video)
    source_fps = video.frame_rate if video and video.frame_rate else session_fps
    session_origin = timecode_to_frame(export.session_start_timecode, session_fps)

    lines = ["Name\tTimecode\tComments"]
    for cut in cuts:
        session_frame = map_source_frame_to_session_frame(
            cut.frame_index,
            source_fps=source_fps,
            session_fps=session_fps,
            session_start_tc=export.session_start_timecode,
        )
        tc = frame_to_timecode(
            session_frame - session_origin,
            session_fps,
            start_timecode=export.session_start_timecode,
        )
        comment = cut.notes or f"frame {cut.frame_index}"
        lines.append(f"{cut.marker_name()}\t{tc}\t{comment}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


IMPORT_INSTRUCTIONS = """
Pro Tools Absolute markers (recommended)
----------------------------------------
Use CutMarker’s “Send to Pro Tools” button. That creates real Memory Locations
(Absolute markers) in your open Pro Tools session via Avid PTSL — not MIDI.

1. Open your Pro Tools session.
2. Match CutMarker session start TC + frame rate to that session.
3. Click “Send to Pro Tools”.
4. SCENE 1, SCENE 2, … appear on the Marker ruler.

Requires Pro Tools 2023.6+ with scripting/PTSL enabled.

Note: File → Import → Session Data only opens real .ptx/.pts sessions.
A plain .txt marker list cannot be imported that way. Writing a full offline
.ptx from scratch is proprietary; live PTSL injection is the supported path
for real Absolute markers without a third-party PTX converter.
""".strip()
