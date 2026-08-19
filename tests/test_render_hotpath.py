from __future__ import annotations

import numpy as np

from render_whiteboard import _component_paths_from_grid, _wipe_mask, hand_path_from_element


def test_grid_paths_follow_ink_cells() -> None:
    binary = np.zeros((40, 40), dtype=bool)
    binary[4:8, 4:28] = True
    binary[8:28, 20:24] = True
    paths = _component_paths_from_grid(binary, edge=4)
    assert paths
    points = [point for path in paths for point in path]
    assert all(binary[y, x] or binary[max(0, y - 2): y + 3, max(0, x - 2): x + 3].any() for x, y in points)


def test_wipe_mask_axis_and_radial() -> None:
    allowed = np.zeros((80, 120), dtype=bool)
    allowed[10:70, 20:100] = True
    rect = (20, 10, 100, 70)

    empty, _ = _wipe_mask(allowed, "left_to_right", 0.0, rect)
    full, _ = _wipe_mask(allowed, "left_to_right", 1.0, rect)
    assert int(empty.sum()) < int(full.sum())
    assert not empty.any() or empty[:, :20].sum() == 0
    assert np.array_equal(full, allowed)

    mid, _ = _wipe_mask(allowed, "top_to_bottom", 0.5, rect)
    assert mid[10:40, 20:100].all()
    assert not mid[41:70, 20:100].any()

    radial, pointer = _wipe_mask(allowed, "radial", 0.4, rect)
    assert radial.any()
    assert not radial[0, 0]
    assert 0 <= pointer[0] < 120 and 0 <= pointer[1] < 80


def test_hand_path_from_element_prefers_centerline() -> None:
    element = {
        "handPath": {
            "kind": "stroke-centerline",
            "points": [[10, 20], [40, 22], [80, 21]],
            "contour": [[8, 16], [82, 16], [82, 26], [8, 26]],
            "start": [10, 20],
            "end": [80, 21],
        }
    }
    points, lifts = hand_path_from_element(element, 1.0, 1.0)
    assert lifts == set()
    assert points[0] == (10, 20)
    assert points[-1] == (80, 21)
    assert len(points) >= 3


def test_contour_centerline_follows_long_axis() -> None:
    from chinese_stroke_split import contour_centerline

    # wide rectangle-like stroke
    pts = [(0, 0), (80, 0), (80, 10), (0, 10)]
    line = contour_centerline(pts, horizontal=True)
    assert len(line) >= 2
    assert line[0][0] < line[-1][0]
    assert all(3 <= y <= 7 for _, y in line)
