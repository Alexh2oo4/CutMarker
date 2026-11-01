"""Download FFmpeg essentials (ffmpeg.exe + ffprobe.exe) into resources/bin."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlopen

URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEST = Path(__file__).resolve().parents[1] / "cutmarker" / "resources" / "bin"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL} …")
    data = urlopen(URL, timeout=600).read()
    print(f"Extracting into {DEST} …")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            lower = name.lower().replace("\\", "/")
            if lower.endswith("/ffmpeg.exe") or lower.endswith("ffmpeg.exe"):
                if lower.count("/") >= 1 and not lower.endswith("/"):
                    target = DEST / "ffmpeg.exe"
                    target.write_bytes(zf.read(name))
                    print("Wrote", target)
            if lower.endswith("/ffprobe.exe") or lower.endswith("ffprobe.exe"):
                if lower.count("/") >= 1 and not lower.endswith("/"):
                    target = DEST / "ffprobe.exe"
                    target.write_bytes(zf.read(name))
                    print("Wrote", target)
    if not (DEST / "ffmpeg.exe").is_file() or not (DEST / "ffprobe.exe").is_file():
        raise SystemExit("Failed to extract ffmpeg.exe / ffprobe.exe")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
