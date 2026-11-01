"""Scene comments export tests."""

from __future__ import annotations

from pathlib import Path

from cutmarker.core.cuts import CutList
from cutmarker.export.comments_export import (
    export_all_comments,
    export_individual_comments,
    export_selected_comment,
)


def test_all_and_individual(tmp_path: Path):
    cuts = CutList()
    cuts.set_from_frames([0, 10, 20])
    cuts.set_notes(0, "open")
    cuts.set_notes(10, 'say "hi"')
    out = export_all_comments(tmp_path / "all.txt", cuts)
    text = out.read_text(encoding="utf-8")
    assert 'SCENE 1 "open"' in text
    assert 'SCENE 2 "say \\"hi\\""' in text
    assert 'SCENE 3 ""' in text

    files = export_individual_comments(tmp_path / "each", cuts)
    assert len(files) == 3
    assert (tmp_path / "each" / "SCENE_2.txt").read_text(encoding="utf-8").startswith(
        'SCENE 2 "'
    )

    one = export_selected_comment(tmp_path / "one.txt", cuts[0])
    assert one.read_text(encoding="utf-8").strip() == 'SCENE 1 "open"'
