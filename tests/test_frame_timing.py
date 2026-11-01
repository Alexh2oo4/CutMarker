"""Frame rate and timecode conversion tests."""

from __future__ import annotations

from fractions import Fraction

import pytest

from cutmarker.core.frame_timing import (
    FrameRate,
    frame_to_seconds,
    frame_to_timecode,
    map_source_frame_to_session_frame,
    seconds_to_frame,
    timecode_to_frame,
)


def test_known_rates_snap():
    assert FrameRate.from_float(23.976).rate == Fraction(24000, 1001)
    assert FrameRate.from_float(29.97).rate == Fraction(30000, 1001)
    assert FrameRate.from_float(25.0).rate == Fraction(25, 1)
    assert FrameRate.from_float(24.0).rate == Fraction(24, 1)


def test_frame_125_at_25fps():
    fps = FrameRate.from_float(25)
    assert frame_to_timecode(125, fps) == "00:00:05:00"
    assert float(frame_to_seconds(125, fps)) == 5.0
    assert seconds_to_frame(5.0, fps) == 125


def test_frame_250_at_25fps():
    fps = FrameRate.from_float(25)
    assert frame_to_timecode(250, fps) == "00:00:10:00"
    assert timecode_to_frame("00:00:10:00", fps) == 250


def test_23976_exact_fraction():
    fps = FrameRate.from_float(23.976)
    # 24000 frames @ 24000/1001 ≈ 1001 seconds exactly
    secs = frame_to_seconds(24000, fps)
    assert secs == Fraction(1001, 1)
    assert seconds_to_frame(secs, fps) == 24000


def test_ndf_roundtrip_30():
    fps = FrameRate.from_float(30)
    for frame in (0, 1, 29, 30, 59, 1799, 1800, 3600, 108000):
        tc = frame_to_timecode(frame, fps)
        assert timecode_to_frame(tc, fps) == frame


def test_drop_frame_29_97_known_values():
    fps = FrameRate.from_float(29.97, drop_frame=True)
    assert frame_to_timecode(0, fps) == "00:00:00;00"
    # First minute: no drops in counting until we hit 00:01:00
    assert frame_to_timecode(1799, fps) == "00:00:59;29"
    assert frame_to_timecode(1800, fps) == "00:01:00;02"
    assert timecode_to_frame("00:01:00;02", fps) == 1800


def test_drop_frame_roundtrip_samples():
    fps = FrameRate.from_float(29.97, drop_frame=True)
    samples = [0, 30, 1800, 17982, 30000, 100000]
    for frame in samples:
        tc = frame_to_timecode(frame, fps)
        assert timecode_to_frame(tc, fps) == frame


def test_session_mapping_matching_rates():
    src = FrameRate.from_float(25)
    sess = FrameRate.from_float(25)
    # source frame 0 → session 01:00:00:00 → frame index of that TC
    mapped = map_source_frame_to_session_frame(
        0,
        source_fps=src,
        session_fps=sess,
        session_start_tc="01:00:00:00",
    )
    assert mapped == timecode_to_frame("01:00:00:00", sess)

    mapped_125 = map_source_frame_to_session_frame(
        125,
        source_fps=src,
        session_fps=sess,
        session_start_tc="01:00:00:00",
    )
    assert mapped_125 == timecode_to_frame("01:00:05:00", sess)


def test_start_timecode_offset_display():
    fps = FrameRate.from_float(24)
    tc = frame_to_timecode(24, fps, start_timecode="01:00:00:00")
    assert tc == "01:00:01:00"


def test_no_float_accumulation_long_film():
    fps = FrameRate.from_float(23.976)
    # 3-hour film ≈ 258508 frames at 23.976
    frame = 258508
    secs = frame_to_seconds(frame, fps)
    back = seconds_to_frame(secs, fps)
    assert back == frame
