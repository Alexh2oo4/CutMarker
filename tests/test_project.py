"""Project save/load tests."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.core.detection import DetectionSettings, SensitivityPreset
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.project import CutMarkerProject, ExportSettings
from cutmarker.core.video_metadata import VideoMetadata


def test_roundtrip(tmp_path: Path):
    fps = FrameRate.from_float(24)
    project = CutMarkerProject(
        video=VideoMetadata(
            path=str(tmp_path / "film.mov"),
            filename="film.mov",
            frame_rate=fps,
            total_frames=1000,
            width=1920,
            height=1080,
        ),
        cuts=CutList(),
        detection_settings=DetectionSettings.from_preset(SensitivityPreset.CONSERVATIVE),
        export_settings=ExportSettings(
            session_frame_rate=fps,
            session_start_timecode="01:00:00:00",
        ),
    )
    project.cuts.set_from_frames([0, 48, 96])
    path = project.save(tmp_path / "job.cutmarker.json")
    loaded = CutMarkerProject.load(path)
    assert loaded.video is not None
    assert loaded.video.filename == "film.mov"
    assert [c.frame_index for c in loaded.cuts] == [0, 48, 96]
    assert loaded.detection_settings.preset == SensitivityPreset.CONSERVATIVE
    assert loaded.export_settings.session_start_timecode == "01:00:00:00"
