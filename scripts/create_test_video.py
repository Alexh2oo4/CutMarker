"""Create a short synthetic test video with known hard cuts at known frames.

Requires FFmpeg (system or imageio-ffmpeg).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Known cut frames (first frame of each new shot), including 0
KNOWN_CUT_FRAMES = [0, 24, 48, 72, 96]
FPS = 24
WIDTH = 320
HEIGHT = 240
TOTAL_FRAMES = 120


def _ffmpeg() -> str:
    from cutmarker.utils.ffmpeg import get_ffmpeg_path

    return get_ffmpeg_path()


def generate(output: Path) -> list[int]:
    """Write an MP4 with solid-colour shots changing at KNOWN_CUT_FRAMES."""
    import cv2

    colors = [
        (0, 0, 255),  # red
        (0, 255, 0),  # green
        (255, 0, 0),  # blue
        (0, 255, 255),  # yellow
        (255, 0, 255),  # magenta
    ]

    # Determine colour per frame from cut list
    def colour_for_frame(f: int) -> tuple[int, int, int]:
        shot = 0
        for i, cut in enumerate(KNOWN_CUT_FRAMES):
            if f >= cut:
                shot = i
        return colors[shot % len(colors)]

    with tempfile.TemporaryDirectory() as tmp:
        pattern = Path(tmp) / "frame_%05d.png"
        for f in range(TOTAL_FRAMES):
            img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            img[:, :] = colour_for_frame(f)
            # Frame number overlay for visual QA
            cv2.putText(
                img,
                f"F{f}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
            )
            cv2.imwrite(str(Path(tmp) / f"frame_{f:05d}.png"), img)

        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            _ffmpeg(),
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(Path(tmp) / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            str(output),
        ]
        subprocess.run(cmd, check=True)
    return list(KNOWN_CUT_FRAMES)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/test_cuts_24fps.mp4")
    cuts = generate(out)
    print(f"Wrote {out}")
    print(f"Known cut frames: {cuts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
