"""Build a standalone Windows app with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "scripts" / "cutmarker.spec"


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print("Build complete -> dist/CutMarker/")
    print("FFmpeg binaries are bundled under dist/CutMarker/ffmpeg/ when present in resources/bin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
