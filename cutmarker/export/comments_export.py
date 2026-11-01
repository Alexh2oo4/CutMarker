"""Export scene Notes / comments to text files."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList, DetectedCut


def _quoted(text: str) -> str:
    # Escape embedded quotes for a simple SCENE N "..." line format
    return text.replace('"', '\\"')


def format_scene_comment_line(cut: DetectedCut) -> str:
    return f'{cut.marker_name()} "{_quoted(cut.notes)}"'


def export_all_comments(
    path: str | Path,
    cuts: CutList,
    *,
    only_with_notes: bool = False,
) -> Path:
    """Write every scene comment into one .txt (one SCENE N \"…\" per line)."""
    path = Path(path)
    if path.suffix.lower() != ".txt":
        path = path.with_suffix(".txt")
    lines: list[str] = []
    for cut in cuts:
        if only_with_notes and not cut.notes.strip():
            continue
        lines.append(format_scene_comment_line(cut))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def export_selected_comment(path: str | Path, cut: DetectedCut) -> Path:
    """Write a single scene's comment to one .txt."""
    path = Path(path)
    if path.suffix.lower() != ".txt":
        path = path.with_suffix(".txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_scene_comment_line(cut) + "\n", encoding="utf-8")
    return path


def export_individual_comments(
    directory: str | Path,
    cuts: CutList,
    *,
    only_with_notes: bool = False,
) -> list[Path]:
    """Write one .txt per scene into ``directory`` (SCENE_1.txt, SCENE_2.txt, …)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cut in cuts:
        if only_with_notes and not cut.notes.strip():
            continue
        out = directory / f"SCENE_{cut.scene_number}.txt"
        out.write_text(format_scene_comment_line(cut) + "\n", encoding="utf-8")
        written.append(out)
    return written
