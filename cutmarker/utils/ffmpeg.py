"""Locate bundled or system FFmpeg / FFprobe binaries."""

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path


def _bundled_bin_dir() -> Path | None:
    """Directory for FFmpeg shipped beside a PyInstaller build or resources/bin."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "ffmpeg")
            candidates.append(Path(meipass))
        candidates.append(Path(sys.executable).resolve().parent / "ffmpeg")
        candidates.append(Path(sys.executable).resolve().parent)
    pkg_root = Path(__file__).resolve().parents[1]
    candidates.append(pkg_root / "resources" / "bin")
    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root / "ffmpeg")
    candidates.append(project_root / "resources" / "bin")
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _imageio_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_ffmpeg_path() -> str:
    env = os.environ.get("CUTMARKER_FFMPEG") or os.environ.get("FFMPEG_BINARY")
    if env and Path(env).is_file():
        return str(Path(env).resolve())

    bin_dir = _bundled_bin_dir()
    if bin_dir:
        for name in ("ffmpeg.exe", "ffmpeg"):
            candidate = bin_dir / name
            if candidate.is_file():
                return str(candidate.resolve())

    which = shutil.which("ffmpeg")
    if which:
        return which

    imageio = _imageio_ffmpeg_exe()
    if imageio and Path(imageio).is_file():
        return imageio

    raise FileNotFoundError(
        "FFmpeg was not found. Install FFmpeg, place ffmpeg.exe in resources/bin, "
        "or set CUTMARKER_FFMPEG to the executable path."
    )


@lru_cache(maxsize=1)
def get_ffprobe_path() -> str:
    env = os.environ.get("CUTMARKER_FFPROBE") or os.environ.get("FFPROBE_BINARY")
    if env and Path(env).is_file():
        return str(Path(env).resolve())

    bin_dir = _bundled_bin_dir()
    if bin_dir:
        for name in ("ffprobe.exe", "ffprobe"):
            candidate = bin_dir / name
            if candidate.is_file():
                return str(candidate.resolve())

    which = shutil.which("ffprobe")
    if which:
        return which

    # imageio-ffmpeg typically ships ffmpeg only; derive sibling ffprobe if present
    try:
        ffmpeg = get_ffmpeg_path()
        sibling = Path(ffmpeg).with_name(
            "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
        )
        if sibling.is_file():
            return str(sibling.resolve())
    except FileNotFoundError:
        pass

    raise FileNotFoundError(
        "FFprobe was not found. Install FFmpeg (includes ffprobe), place ffprobe.exe "
        "in resources/bin, or set CUTMARKER_FFPROBE."
    )


def ensure_ffmpeg() -> tuple[str, str | None]:
    """Return (ffmpeg_path, ffprobe_path_or_None). Raises if ffmpeg missing."""
    ffmpeg = get_ffmpeg_path()
    try:
        ffprobe = get_ffprobe_path()
    except FileNotFoundError:
        ffprobe = None
    return ffmpeg, ffprobe
