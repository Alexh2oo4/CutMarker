"""Scene numbering and manual cut adjustment tests."""

from __future__ import annotations

from cutmarker.core.cuts import CutList


def test_ensure_opening_and_numbering():
    cuts = CutList()
    cuts.set_from_frames([100, 250, 400], include_start=True)
    assert [c.frame_index for c in cuts] == [0, 100, 250, 400]
    assert [c.scene_number for c in cuts] == [1, 2, 3, 4]
    assert [c.marker_name() for c in cuts] == [
        "SCENE 1",
        "SCENE 2",
        "SCENE 3",
        "SCENE 4",
    ]


def test_add_delete_renumber():
    cuts = CutList()
    cuts.set_from_frames([0, 50, 100])
    cuts.add_cut(75)
    assert [c.frame_index for c in cuts] == [0, 50, 75, 100]
    assert [c.scene_number for c in cuts] == [1, 2, 3, 4]
    cuts.delete_cut(50)
    assert [c.frame_index for c in cuts] == [0, 75, 100]
    assert [c.scene_number for c in cuts] == [1, 2, 3]


def test_move_cut():
    cuts = CutList()
    cuts.set_from_frames([0, 100, 200])
    moved = cuts.move_cut(100, 120)
    assert moved is not None
    assert moved.frame_index == 120
    assert [c.frame_index for c in cuts] == [0, 120, 200]
    assert moved.source == "manual"


def test_nudge_and_collision():
    cuts = CutList()
    cuts.set_from_frames([0, 10, 20])
    # Moving 10 onto 20 replaces 20
    cuts.move_cut(10, 20)
    assert [c.frame_index for c in cuts] == [0, 20]


def test_prev_next():
    cuts = CutList()
    cuts.set_from_frames([0, 50, 100])
    assert cuts.next_cut(50).frame_index == 100
    assert cuts.previous_cut(50).frame_index == 0
    assert cuts.next_cut(100) is None
