"""CutMarker project save / load (.cutmarker.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cutmarker import __version__
from cutmarker.core.cuts import CutList
from cutmarker.core.detection import DetectionSettings
from cutmarker.core.frame_timing import FrameRate
from cutmarker.core.video_metadata import VideoMetadata


@dataclass
class ExportSettings:
    session_frame_rate: FrameRate | None = None
    session_start_timecode: str = "00:00:00:00"
    session_drop_frame: bool = False
    sample_rate: int = 48000
    bit_depth: int = 24
    session_name: str = "CutMarker_Export"

    def to_dict(self) -> dict[str, Any]:
        fr = None
        if self.session_frame_rate:
            fr = {
                "num": self.session_frame_rate.rate.numerator,
                "den": self.session_frame_rate.rate.denominator,
                "drop_frame": self.session_frame_rate.drop_frame,
                "label": self.session_frame_rate.label,
            }
        return {
            "session_frame_rate": fr,
            "session_start_timecode": self.session_start_timecode,
            "session_drop_frame": self.session_drop_frame,
            "sample_rate": self.sample_rate,
            "bit_depth": self.bit_depth,
            "session_name": self.session_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExportSettings:
        settings = cls(
            session_start_timecode=data.get("session_start_timecode", "00:00:00:00"),
            session_drop_frame=bool(data.get("session_drop_frame")),
            sample_rate=int(data.get("sample_rate") or 48000),
            bit_depth=int(data.get("bit_depth") or 24),
            session_name=str(data.get("session_name") or "CutMarker_Export"),
        )
        fr = data.get("session_frame_rate")
        if isinstance(fr, dict):
            settings.session_frame_rate = FrameRate.from_ratio(
                fr["num"],
                fr["den"],
                drop_frame=fr.get("drop_frame", False),
                label=fr.get("label", ""),
            )
        return settings


@dataclass
class CutMarkerProject:
    video: VideoMetadata | None = None
    cuts: CutList = field(default_factory=CutList)
    detection_settings: DetectionSettings = field(default_factory=DetectionSettings)
    export_settings: ExportSettings = field(default_factory=ExportSettings)
    project_path: str | None = None
    created_at: str = ""
    modified_at: str = ""
    app_version: str = __version__
    notes: str = ""

    def touch(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        self.modified_at = now

    def sync_export_fps_from_video(self) -> None:
        if self.video and self.video.frame_rate and not self.export_settings.session_frame_rate:
            self.export_settings.session_frame_rate = self.video.frame_rate
        if self.video and self.video.start_timecode:
            # Do not override user session start; only seed if still default and source has TC
            pass

    def to_dict(self) -> dict[str, Any]:
        self.touch()
        return {
            "format": "cutmarker.project",
            "format_version": 1,
            "app_version": self.app_version,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "notes": self.notes,
            "video": self.video.to_dict() if self.video else None,
            "cuts": self.cuts.to_list(),
            "detection_settings": self.detection_settings.to_dict(),
            "export_settings": self.export_settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CutMarkerProject:
        if data.get("format") not in (None, "cutmarker.project"):
            raise ValueError("Not a CutMarker project file")
        video = None
        if data.get("video"):
            video = VideoMetadata.from_dict(data["video"])
        return cls(
            video=video,
            cuts=CutList.from_list(data.get("cuts") or []),
            detection_settings=DetectionSettings.from_dict(
                data.get("detection_settings") or {}
            ),
            export_settings=ExportSettings.from_dict(data.get("export_settings") or {}),
            created_at=str(data.get("created_at") or ""),
            modified_at=str(data.get("modified_at") or ""),
            app_version=str(data.get("app_version") or __version__),
            notes=str(data.get("notes") or ""),
        )

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path or self.project_path or "")
        if not path or str(path) == ".":
            raise ValueError("Project path required")
        if path.suffix.lower() not in {".json", ".cutmarker"}:
            path = path.with_suffix(".cutmarker.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.project_path = str(path.resolve())
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        return path

    @classmethod
    def load(cls, path: str | Path) -> CutMarkerProject:
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        project = cls.from_dict(data)
        project.project_path = str(path.resolve())
        return project
