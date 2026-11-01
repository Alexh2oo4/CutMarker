"""Detected cut model and manual correction operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from cutmarker.core.frame_timing import FrameRate, frame_to_seconds, frame_to_timecode


@dataclass(slots=True)
class DetectedCut:
    """A camera cut at the first frame of a new shot (zero-based frame index)."""

    frame_index: int
    scene_number: int = 0
    pts_seconds: float | None = None
    confidence: float | None = None
    source: str = "auto"  # auto | manual
    reviewed: bool = False
    notes: str = ""

    def marker_name(self) -> str:
        return f"SCENE {self.scene_number}"

    def timecode(self, fps: FrameRate, start_timecode: str | None = None) -> str:
        return frame_to_timecode(
            self.frame_index, fps, start_timecode=start_timecode
        )

    def timestamp_seconds(self, fps: FrameRate) -> float:
        if self.pts_seconds is not None:
            return float(self.pts_seconds)
        return float(frame_to_seconds(self.frame_index, fps))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectedCut:
        return cls(
            frame_index=int(data["frame_index"]),
            scene_number=int(data.get("scene_number") or 0),
            pts_seconds=data.get("pts_seconds"),
            confidence=data.get("confidence"),
            source=str(data.get("source") or "auto"),
            reviewed=bool(data.get("reviewed")),
            notes=str(data.get("notes") or ""),
        )


class CutList:
    """Ordered, unique cut list with automatic sequential scene numbering.

    Scene 1 is always the first frame of the film (frame 0) unless the user
    deletes it. Every subsequent camera cut increments the scene number.
    """

    def __init__(self, cuts: Iterable[DetectedCut] | None = None) -> None:
        self._cuts: list[DetectedCut] = []
        if cuts:
            for cut in cuts:
                self._cuts.append(cut)
            self._normalize()

    def __len__(self) -> int:
        return len(self._cuts)

    def __iter__(self):
        return iter(self._cuts)

    def __getitem__(self, index: int) -> DetectedCut:
        return self._cuts[index]

    @property
    def cuts(self) -> list[DetectedCut]:
        return list(self._cuts)

    def _normalize(self) -> None:
        # Unique by frame, sort ascending, renumber scenes 1..N
        by_frame: dict[int, DetectedCut] = {}
        for cut in self._cuts:
            if cut.frame_index < 0:
                continue
            existing = by_frame.get(cut.frame_index)
            if existing is None or cut.source == "manual":
                by_frame[cut.frame_index] = cut
        ordered = [by_frame[f] for f in sorted(by_frame)]
        for i, cut in enumerate(ordered, start=1):
            cut.scene_number = i
        self._cuts = ordered

    def ensure_opening_scene(self) -> None:
        """Guarantee SCENE 1 at frame 0 (first shot of the film)."""
        if not self._cuts or self._cuts[0].frame_index != 0:
            self._cuts.insert(
                0,
                DetectedCut(frame_index=0, source="auto", notes="Film start"),
            )
        self._normalize()

    def set_from_frames(
        self,
        frames: Iterable[int],
        *,
        include_start: bool = True,
        pts_map: dict[int, float] | None = None,
        source: str = "auto",
    ) -> None:
        pts_map = pts_map or {}
        cuts = [
            DetectedCut(
                frame_index=int(f),
                pts_seconds=pts_map.get(int(f)),
                source=source,
            )
            for f in frames
            if int(f) >= 0
        ]
        self._cuts = cuts
        if include_start:
            self.ensure_opening_scene()
        else:
            self._normalize()

    def add_cut(self, frame_index: int, *, pts_seconds: float | None = None) -> DetectedCut:
        cut = DetectedCut(
            frame_index=int(frame_index),
            pts_seconds=pts_seconds,
            source="manual",
        )
        self._cuts.append(cut)
        self._normalize()
        for c in self._cuts:
            if c.frame_index == frame_index:
                return c
        return cut

    def delete_cut(self, frame_index: int) -> bool:
        before = len(self._cuts)
        self._cuts = [c for c in self._cuts if c.frame_index != frame_index]
        self._normalize()
        return len(self._cuts) < before

    def delete_by_scene(self, scene_number: int) -> bool:
        target = next((c for c in self._cuts if c.scene_number == scene_number), None)
        if not target:
            return False
        return self.delete_cut(target.frame_index)

    def move_cut(self, frame_index: int, new_frame_index: int) -> DetectedCut | None:
        cut = next((c for c in self._cuts if c.frame_index == frame_index), None)
        if cut is None:
            return None
        # Avoid collision: remove any cut already at destination
        self._cuts = [
            c
            for c in self._cuts
            if c.frame_index != frame_index and c.frame_index != new_frame_index
        ]
        moved = DetectedCut(
            frame_index=int(new_frame_index),
            pts_seconds=None,
            confidence=cut.confidence,
            source="manual",
            reviewed=cut.reviewed,
            notes=cut.notes,
        )
        self._cuts.append(moved)
        self._normalize()
        return next(c for c in self._cuts if c.frame_index == new_frame_index)

    def nudge_cut(self, frame_index: int, delta_frames: int) -> DetectedCut | None:
        return self.move_cut(frame_index, frame_index + delta_frames)

    def mark_reviewed(self, frame_index: int, reviewed: bool = True) -> None:
        for cut in self._cuts:
            if cut.frame_index == frame_index:
                cut.reviewed = reviewed
                return

    def set_notes(self, frame_index: int, notes: str) -> None:
        for cut in self._cuts:
            if cut.frame_index == frame_index:
                cut.notes = notes
                return

    def nearest_cut(self, frame_index: int) -> DetectedCut | None:
        if not self._cuts:
            return None
        return min(self._cuts, key=lambda c: abs(c.frame_index - frame_index))

    def previous_cut(self, frame_index: int) -> DetectedCut | None:
        earlier = [c for c in self._cuts if c.frame_index < frame_index]
        return earlier[-1] if earlier else None

    def next_cut(self, frame_index: int) -> DetectedCut | None:
        later = [c for c in self._cuts if c.frame_index > frame_index]
        return later[0] if later else None

    def to_list(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._cuts]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> CutList:
        return cls(DetectedCut.from_dict(d) for d in data)
