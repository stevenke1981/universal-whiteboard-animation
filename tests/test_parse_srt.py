from __future__ import annotations

from parse_srt import group_scenes, parse_plain_text, parse_timed_text


def test_parse_srt_and_natural_breaks() -> None:
    source = """1
00:00:00,000 --> 00:00:02,000
第一個完整句子。

2
00:00:02,000 --> 00:00:04,000
接著補充一個重點。

3
00:00:05,200 --> 00:00:07,200
新的段落從明顯停頓開始。
"""
    cues, fmt, warnings = parse_timed_text(source)
    assert fmt == "srt"
    assert not warnings
    assert [cue["text"] for cue in cues] == [
        "第一個完整句子。",
        "接著補充一個重點。",
        "新的段落從明顯停頓開始。",
    ]

    scenes, scene_warnings = group_scenes(
        cues,
        target_sec=4,
        min_sec=2,
        max_sec=7,
        prefer_punctuation=True,
        gap_sec=0.8,
    )
    assert not scene_warnings
    assert len(scenes) == 2
    assert scenes[0]["cueRange"] == [1, 2]
    assert scenes[0]["breakReason"] in {"subtitle-gap", "sentence-boundary"}
    assert scenes[1]["cueRange"] == [3, 3]


def test_parse_webvtt_and_plain_text() -> None:
    webvtt = """WEBVTT

00:00.000 --> 00:01.500
<b>概念</b>先出現。

00:01.500 --> 00:03.000
再形成結果。
"""
    cues, fmt, warnings = parse_timed_text(webvtt)
    assert fmt == "webvtt"
    assert not warnings
    assert cues[0]["text"] == "概念先出現。"

    plain, plain_warnings = parse_plain_text("先提出問題。再說明方法！最後做出結論。", chars_per_second=5)
    assert len(plain) == 3
    assert all(cue["estimatedTiming"] for cue in plain)
    assert plain_warnings
