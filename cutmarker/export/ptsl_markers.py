"""Push Absolute Pro Tools Memory Location markers into a live session via PTSL.

This creates real Pro Tools markers (not MIDI). Requires:
  - Pro Tools running (2023.6+ with scripting / PTSL enabled)
  - A session open
  - py-ptsl installed
"""

from __future__ import annotations

from dataclasses import dataclass

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import (
    FrameRate,
    frame_to_timecode,
    map_source_frame_to_session_frame,
    timecode_to_frame,
)
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata


@dataclass(slots=True)
class PtslPushResult:
    created: int
    skipped: int
    session_name: str
    errors: list[str]


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


def _cut_session_timecode(
    cut_frame: int,
    *,
    video: VideoMetadata | None,
    export: ExportSettings,
) -> str:
    session_fps = _session_fps(export, video)
    source_fps = video.frame_rate if video and video.frame_rate else session_fps
    session_origin = timecode_to_frame(export.session_start_timecode, session_fps)
    if video and video.is_variable_frame_rate:
        # Without PTS, fall back to CFR mapping
        pass
    session_frame = map_source_frame_to_session_frame(
        cut_frame,
        source_fps=source_fps,
        session_fps=session_fps,
        session_start_tc=export.session_start_timecode,
    )
    return frame_to_timecode(
        session_frame - session_origin,
        session_fps,
        start_timecode=export.session_start_timecode,
    )


def push_markers_to_pro_tools(
    cuts: CutList,
    video: VideoMetadata | None,
    export: ExportSettings,
    *,
    company_name: str = "CutMarker",
    application_name: str = "CutMarker",
) -> PtslPushResult:
    """Create Absolute Memory Location markers in the currently open PT session."""
    try:
        from ptsl import open_engine
        from ptsl.PTSL_pb2 import (
            MemoryLocationProperties,
            MemoryLocationReference,
            TimeProperties,
        )
    except ImportError as exc:
        raise RuntimeError(
            "py-ptsl is not installed. Run: pip install py-ptsl"
        ) from exc

    errors: list[str] = []
    created = 0
    skipped = 0

    try:
        with open_engine(
            company_name=company_name, application_name=application_name
        ) as engine:
            try:
                session_name = engine.session_name() or "(untitled)"
            except Exception:
                session_name = "(unknown)"

            props = MemoryLocationProperties(
                zoom_settings=False,
                pre_post_roll_times=False,
                track_visibility=False,
                track_heights=False,
                group_enables=False,
                window_configuration=False,
            )

            for cut in cuts:
                tc = _cut_session_timecode(
                    cut.frame_index, video=video, export=export
                )
                try:
                    engine.create_memory_location(
                        start_time=tc,
                        end_time=tc,
                        memory_number=cut.scene_number,
                        name=cut.marker_name(),
                        time_properties=TimeProperties.TP_Marker,
                        reference=MemoryLocationReference.MLR_Absolute,
                        general_properties=props,
                        comments=cut.notes or "",
                        color_index=((cut.scene_number - 1) % 16) + 1,
                        location="MLC_MainRuler",
                    )
                    created += 1
                except Exception as exc:
                    # Older SDK builds may not accept location=
                    try:
                        engine.create_memory_location(
                            start_time=tc,
                            end_time=tc,
                            memory_number=cut.scene_number,
                            name=cut.marker_name(),
                            time_properties=TimeProperties.TP_Marker,
                            reference=MemoryLocationReference.MLR_Absolute,
                            general_properties=props,
                            comments=cut.notes or "",
                            color_index=((cut.scene_number - 1) % 16) + 1,
                        )
                        created += 1
                    except Exception as exc2:
                        skipped += 1
                        errors.append(f"{cut.marker_name()} @ {tc}: {exc2}")

            return PtslPushResult(
                created=created,
                skipped=skipped,
                session_name=session_name,
                errors=errors,
            )
    except Exception as exc:
        raise RuntimeError(
            "Could not connect to Pro Tools via PTSL.\n\n"
            "Check that:\n"
            "• Pro Tools is running (2023.6 or newer)\n"
            "• A session is open\n"
            "• Scripting / PTSL is enabled in Pro Tools preferences\n\n"
            f"Details: {exc}"
        ) from exc


PTSL_INSTRUCTIONS = """
Send Absolute markers to Pro Tools (recommended)
------------------------------------------------
CutMarker can create real Pro Tools Memory Locations (Absolute markers) in your
open session using Avid’s PTSL scripting interface — not MIDI.

1. Open your Pro Tools session.
2. Match CutMarker’s session start TC + frame rate to that session.
3. In CutMarker click “Send to Pro Tools”.
4. Markers appear on the Marker ruler as SCENE 1, SCENE 2, …

Requires Pro Tools 2023.6+ with PTSL/scripting enabled, and py-ptsl installed.
""".strip()
