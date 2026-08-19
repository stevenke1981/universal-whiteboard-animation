from __future__ import annotations

import numpy as np

from render_whiteboard import _component_paths_from_grid, _wipe_mask


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
