"""Marker export format tests."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.frame_timing import FrameRate, timecode_to_frame
from cutmarker.core.project import ExportSettings
from cutmarker.core.video_metadata import VideoMetadata
from cutmarker.export.csv_export import export_csv
from cutmarker.export.edl_export import export_edl
from cutmarker.export.protools import export_protools_session_text
from cutmarker.export.text_export import export_text_report


def _sample_project():
    fps = FrameRate.from_float(25)
    video = VideoMetadata(
        path="dummy.mov",
        filename="dummy.mov",
        duration_seconds=20.0,
        width=1920,
        height=1080,
        video_codec="prores",
        frame_rate=fps,
        avg_frame_rate=fps,
        total_frames=500,
    )
    cuts = CutList()
    cuts.set_from_frames([0, 125, 250])
    export = ExportSettings(
        session_frame_rate=fps,
        session_start_timecode="01:00:00:00",
        sample_rate=48000,
        session_name="UnitTest",
    )
    return video, cuts, export


def test_protools_session_text(tmp_path: Path):
    video, cuts, export = _sample_project()
    out = tmp_path / "markers.txt"
    export_protools_session_text(out, cuts, video, export)
    text = out.read_text(encoding="utf-8")
    assert "SESSION NAME:\tUnitTest" in text
    assert "TIMECODE FORMAT:\t25 Frame" in text
    assert "SESSION START TIMECODE:\t01:00:00:00" in text
    assert "SCENE 1" in text
    assert "SCENE 2" in text
    assert "SCENE 3" in text
    assert "01:00:00:00" in text
    assert "01:00:05:00" in text
    assert "01:00:10:00" in text
    assert "M A R K E R S  L I S T I N G" in text


def test_csv_columns(tmp_path: Path):
    video, cuts, _export = _sample_project()
    out = tmp_path / "markers.csv"
    export_csv(out, cuts, video)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("Scene Number,Marker Name,Frame Number")
    assert "SCENE 2" in lines[2]
    assert ",125," in lines[2]


def test_edl_and_report(tmp_path: Path):
    video, cuts, export = _sample_project()
    edl = tmp_path / "cuts.edl"
    report = tmp_path / "report.txt"
    export_edl(edl, cuts, video, title=export.session_name)
    export_text_report(report, cuts, video)
    assert "TITLE: UnitTest" in edl.read_text(encoding="utf-8")
    assert "Detected scenes: 3" in report.read_text(encoding="utf-8")


def test_session_frame_mapping_values():
    video, cuts, export = _sample_project()
    fps = export.session_frame_rate
    assert fps is not None
    # Frame 125 @ 25fps from 01:00:00:00 → 01:00:05:00
    expected = timecode_to_frame("01:00:05:00", fps)
    origin = timecode_to_frame("01:00:00:00", fps)
    assert expected - origin == 125
