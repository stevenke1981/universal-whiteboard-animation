from __future__ import annotations

from pathlib import Path

import pytest

from chinese_stroke_split import DEFAULT_FONT
from run_pipeline import run_pipeline

needs_kaiu = pytest.mark.skipif(not Path(DEFAULT_FONT).exists(), reason="需要 Windows 標楷體 kaiu.ttf")


@needs_kaiu
def test_pipeline_writes_final_from_text(tmp_path: Path) -> None:
    report = run_pipeline(
        source=None,
        text="日日是好日！",
        out_dir=tmp_path,
        font=Path(DEFAULT_FONT),
        width=640,
        height=360,
        size=100,
        fps=12,
        audio=None,
        low_res=True,
        pointer="none",
        write_stroke_previews=False,
    )
    assert report["valid"]
    assert report["scenes"]
    assert all(scene["strokes"] >= 1 for scene in report["scenes"])
    final = Path(report["output"])
    assert final.exists() and final.stat().st_size > 0
