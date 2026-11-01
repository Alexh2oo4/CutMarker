"""Integration test against synthetic video with known cut frames.

Skipped automatically if the test asset / FFmpeg is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "test_cuts_24fps.mp4"


def _ensure_asset() -> Path:
    if ASSET.is_file():
        return ASSET
    pytest.importorskip("cv2")
    try:
        from scripts.create_test_video import generate

        generate(ASSET)
    except Exception as exc:
        pytest.skip(f"Could not create test video: {exc}")
    return ASSET


def test_detects_known_hard_cuts():
    asset = _ensure_asset()
    from cutmarker.core.detection import DetectionSettings, SensitivityPreset, detect_cuts

    settings = DetectionSettings.from_preset(SensitivityPreset.SENSITIVE)
    settings.min_scene_len = 4
    settings.suppress_flashes = False
    settings.detect_fades = False
    settings.use_adaptive = False
    settings.use_content = True
    settings.content_threshold = 15.0

    result = detect_cuts(asset, settings)
    detected = [c.frame_index for c in result.cut_list]
    expected = [0, 24, 48, 72, 96]

    # Allow ±1 frame tolerance for decoder / detector edge alignment
    for exp in expected:
        assert any(abs(d - exp) <= 1 for d in detected), (
            f"Expected cut near frame {exp}, got {detected}"
        )
