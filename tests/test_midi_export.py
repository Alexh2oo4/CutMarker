"""MIDI marker export smoke tests."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata
from cutmarker.export.midi_markers import export_protools_midi_markers, vlq_encode


def test_vlq():
    assert vlq_encode(0) == b"\x00"
    assert vlq_encode(127) == b"\x7f"
    assert vlq_encode(128) == b"\x81\x00"


def test_midi_file_header_and_markers(tmp_path: Path):
    fps = FrameRate.from_float(25)
    video = VideoMetadata(
        path="x.mov",
        filename="x.mov",
        frame_rate=fps,
        total_frames=500,
    )
    cuts = CutList()
    cuts.set_from_frames([0, 125, 250])
    export = ExportSettings(
        session_frame_rate=fps,
        session_start_timecode="01:00:00:00",
    )
    out = export_protools_midi_markers(tmp_path / "m.mid", cuts, video, export)
    data = out.read_bytes()
    assert data.startswith(b"MThd")
    assert b"MTrk" in data
    assert b"SCENE 1" in data
    assert b"SCENE 2" in data
    assert b"SCENE 3" in data
