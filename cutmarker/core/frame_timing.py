"""Frame-accurate timing, rational frame rates, and timecode conversion.

All conversions prefer integer frame indices and Fraction arithmetic to avoid
accumulated floating-point error. Decimal seconds are derived only when needed
for display or VFR PTS mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Iterable


# NTSC / common professional rates as exact rationals
KNOWN_RATES: dict[str, Fraction] = {
    "23.976": Fraction(24000, 1001),
    "23.98": Fraction(24000, 1001),
    "24": Fraction(24, 1),
    "25": Fraction(25, 1),
    "29.97": Fraction(30000, 1001),
    "30": Fraction(30, 1),
    "48": Fraction(48, 1),
    "50": Fraction(50, 1),
    "59.94": Fraction(60000, 1001),
    "60": Fraction(60, 1),
}


class TimecodeFormat(str, Enum):
    NON_DROP_FRAME = "ndf"
    DROP_FRAME = "df"


@dataclass(frozen=True, slots=True)
class FrameRate:
    """Rational frame rate with optional drop-frame timecode semantics."""

    rate: Fraction
    drop_frame: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("Frame rate must be positive")
        if self.drop_frame and not self.supports_drop_frame:
            object.__setattr__(self, "drop_frame", False)

    @property
    def supports_drop_frame(self) -> bool:
        # SMPTE drop-frame applies to 29.97 and 59.94 families
        return self.rate in (Fraction(30000, 1001), Fraction(60000, 1001))

    @property
    def fps_float(self) -> float:
        return float(self.rate)

    @property
    def nominal_fps(self) -> int:
        """Integer fps used by DF formulas (30 for 29.97, 60 for 59.94)."""
        return int(round(float(self.rate)))

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        for name, frac in KNOWN_RATES.items():
            if frac == self.rate:
                suffix = " DF" if self.drop_frame else ""
                return f"{name}{suffix}"
        return f"{float(self.rate):.6f}".rstrip("0").rstrip(".")

    @classmethod
    def from_float(
        cls,
        value: float,
        *,
        drop_frame: bool | None = None,
        tolerance: float = 0.02,
    ) -> FrameRate:
        if value <= 0:
            raise ValueError("Frame rate must be positive")

        # Prefer canonical professional rates within tolerance (e.g. 23.976 → 24000/1001)
        # rather than the nearest arbitrary Fraction of the float literal.
        best_name = ""
        best_frac: Fraction | None = None
        best_err = float("inf")
        for name, frac in KNOWN_RATES.items():
            err = abs(float(frac) - value)
            if err < best_err:
                best_err = err
                best_frac = frac
                best_name = name

        if best_frac is None or best_err > tolerance:
            best_frac = Fraction(value).limit_denominator(100000)
            best_name = f"{float(best_frac):.6f}".rstrip("0").rstrip(".")

        supports_df = best_frac in (Fraction(30000, 1001), Fraction(60000, 1001))
        use_df = bool(drop_frame) if drop_frame is not None else False
        if use_df and not supports_df:
            use_df = False
        return cls(rate=best_frac, drop_frame=use_df, label=best_name)

    @classmethod
    def from_ratio(
        cls,
        num: int,
        den: int,
        *,
        drop_frame: bool = False,
        label: str = "",
    ) -> FrameRate:
        return cls(rate=Fraction(num, den), drop_frame=drop_frame, label=label)

    def timecode_format(self) -> TimecodeFormat:
        return (
            TimecodeFormat.DROP_FRAME
            if self.drop_frame and self.supports_drop_frame
            else TimecodeFormat.NON_DROP_FRAME
        )


def frame_to_seconds(frame_index: int, fps: FrameRate | Fraction | float) -> Fraction:
    """Exact seconds from a zero-based frame index at constant frame rate."""
    if frame_index < 0:
        raise ValueError("frame_index must be >= 0")
    rate = fps.rate if isinstance(fps, FrameRate) else Fraction(fps).limit_denominator(1001)
    return Fraction(frame_index, 1) / rate


def seconds_to_frame(
    seconds: float | Fraction,
    fps: FrameRate | Fraction | float,
    *,
    mode: str = "round",
) -> int:
    """Convert a presentation timestamp to a nearest/floor/ceil frame index."""
    rate = fps.rate if isinstance(fps, FrameRate) else Fraction(fps).limit_denominator(1001)
    exact = Fraction(seconds) * rate
    if mode == "floor":
        return int(exact)
    if mode == "ceil":
        from math import ceil

        return int(ceil(exact))
    # banker's-avoiding half-up via integers
    return int(exact + Fraction(1, 2))


def _ndf_frame_to_hmsf(total_frames: int, fps_int: int) -> tuple[int, int, int, int]:
    if total_frames < 0:
        raise ValueError("total_frames must be >= 0")
    frames_per_minute = fps_int * 60
    frames_per_hour = frames_per_minute * 60
    hours = total_frames // frames_per_hour
    rem = total_frames % frames_per_hour
    minutes = rem // frames_per_minute
    rem %= frames_per_minute
    seconds = rem // fps_int
    frames = rem % fps_int
    return hours, minutes, seconds, frames


def _df_frame_to_hmsf(total_frames: int, nominal_fps: int) -> tuple[int, int, int, int]:
    """SMPTE drop-frame conversion for 29.97 (30) and 59.94 (60)."""
    if total_frames < 0:
        raise ValueError("total_frames must be >= 0")
    if nominal_fps not in (30, 60):
        raise ValueError("Drop-frame only defined for 30/60 nominal fps")

    drop_frames = 2 if nominal_fps == 30 else 4
    frames_per_min = nominal_fps * 60
    frames_per_10min = frames_per_min * 10 - drop_frames * 9
    frames_per_hour = frames_per_10min * 6

    hours = total_frames // frames_per_hour
    rem = total_frames % frames_per_hour

    tens = rem // frames_per_10min
    rem %= frames_per_10min

    # Within a 10-minute block the first minute has no drops; remaining minutes do.
    if rem < frames_per_min:
        minutes = tens * 10
        minute_rem = rem
    else:
        rem_after_first = rem - frames_per_min
        # After first minute, each minute effectively has (frames_per_min - drop_frames)
        adj = frames_per_min - drop_frames
        extra_mins = 1 + rem_after_first // adj
        minute_rem = rem_after_first % adj
        minutes = tens * 10 + extra_mins
        # Re-add dropped frames so display count includes the skipped numbers conceptually
        # Standard algorithm: add drop_frames for each minute (except every 10th)
        minute_rem += drop_frames

    seconds = minute_rem // nominal_fps
    frames = minute_rem % nominal_fps
    # Carry if minutes rolled (rare edge from remapping)
    if minutes >= 60:
        hours += minutes // 60
        minutes %= 60
    return hours % 24, minutes, seconds, frames


def _df_hmsf_to_frame(
    hours: int, minutes: int, seconds: int, frames: int, nominal_fps: int
) -> int:
    if nominal_fps not in (30, 60):
        raise ValueError("Drop-frame only defined for 30/60 nominal fps")
    drop_frames = 2 if nominal_fps == 30 else 4
    total_minutes = hours * 60 + minutes
    # Drop 2 (or 4) frames at the start of every minute except every 10th minute
    dropped = drop_frames * (total_minutes - total_minutes // 10)
    return (
        ((hours * 3600) + (minutes * 60) + seconds) * nominal_fps
        + frames
        - dropped
    )


def frame_to_timecode(
    frame_index: int,
    fps: FrameRate,
    *,
    start_timecode: str | None = None,
    start_frame: int = 0,
) -> str:
    """Format a zero-based source frame as timecode.

    ``start_timecode`` / ``start_frame`` shift the display origin (e.g. session
    or reel start). Separator is ``;`` for drop-frame, ``:`` otherwise.
    """
    if frame_index < 0:
        raise ValueError("frame_index must be >= 0")

    absolute = frame_index + start_frame
    if start_timecode:
        absolute = timecode_to_frame(start_timecode, fps) + frame_index

    nominal = fps.nominal_fps
    if fps.drop_frame and fps.supports_drop_frame:
        h, m, s, f = _df_frame_to_hmsf(absolute, nominal)
        return f"{h:02d}:{m:02d}:{s:02d};{f:02d}"
    h, m, s, f = _ndf_frame_to_hmsf(absolute, nominal)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def timecode_to_frame(timecode: str, fps: FrameRate) -> int:
    """Parse HH:MM:SS:FF or HH:MM:SS;FF into a zero-based frame count from midnight."""
    tc = timecode.strip()
    drop = ";" in tc
    parts = tc.replace(";", ":").split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode: {timecode!r}")
    hours, minutes, seconds, frames = (int(p) for p in parts)
    nominal = fps.nominal_fps
    if drop or (fps.drop_frame and fps.supports_drop_frame):
        return _df_hmsf_to_frame(hours, minutes, seconds, frames, nominal)
    return ((hours * 3600) + (minutes * 60) + seconds) * nominal + frames


def frames_between_timecodes(a: str, b: str, fps: FrameRate) -> int:
    return timecode_to_frame(b, fps) - timecode_to_frame(a, fps)


def map_source_frame_to_session_frame(
    source_frame: int,
    *,
    source_fps: FrameRate,
    session_fps: FrameRate,
    session_start_tc: str,
    source_start_tc: str = "00:00:00:00",
    vfr_pts_seconds: float | None = None,
) -> int:
    """Map a detected source frame to a Pro Tools session frame index.

    For CFR material, mapping uses exact rational seconds.
    For VFR, pass the presentation timestamp in ``vfr_pts_seconds``.
    """
    session_origin = timecode_to_frame(session_start_tc, session_fps)
    source_origin = timecode_to_frame(source_start_tc, source_fps)

    if vfr_pts_seconds is not None:
        # Relative PTS from start of media
        seconds = Fraction(vfr_pts_seconds)
    else:
        relative_source = source_frame  # already zero-based from media start
        seconds = frame_to_seconds(relative_source, source_fps)

    # Offset by difference between source TC origin and media zero if needed
    if source_origin:
        seconds = seconds + frame_to_seconds(source_origin, source_fps)

    session_relative = seconds_to_frame(seconds, session_fps, mode="round")
    return session_origin + session_relative


def validate_constant_mapping(
    source_fps: FrameRate, session_fps: FrameRate
) -> tuple[bool, str]:
    """Warn when source and session rates differ in ways that prevent 1:1 frames."""
    if source_fps.rate == session_fps.rate:
        return True, "Source and session frame rates match; frame mapping is exact."
    return (
        False,
        "Source frame rate differs from Pro Tools session frame rate. "
        "Markers are placed by converting through exact seconds then rounding to the "
        "nearest session frame. Verify critical cuts against picture.",
    )


def snap_known_rate(fps_value: float) -> FrameRate:
    return FrameRate.from_float(fps_value)


def iter_cut_timecodes(
    frames: Iterable[int],
    fps: FrameRate,
    *,
    start_timecode: str | None = None,
) -> list[str]:
    return [
        frame_to_timecode(f, fps, start_timecode=start_timecode) for f in frames
    ]
