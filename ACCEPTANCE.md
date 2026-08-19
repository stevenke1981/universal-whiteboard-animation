# 驗收條件

## A. Skill 結構

- [x] 根目錄有有效 `SKILL.md` front matter。
- [x] `agents/openai.yaml` 的 skill 名稱與預設提示一致。
- [x] `LICENSE` 與 `NOTICE.md` 保留原 MIT 來源。

## B. 主體可替換

- [x] `subject_profile.mode` 可設為 `none/single/ensemble/object/concept/adaptive`。
- [x] Demo 與文件未把猴子當成預設主角。
- [x] annotation 元素可用 `subjectIds` 綁定主體。
- [x] `set_subject.py` 可同步替換 project、scene bindings 與 annotation subjectIds。

## C. 字幕與分幕

- [x] 可解析逗號或句點毫秒格式的 SRT。
- [x] 可解析基本 WebVTT。
- [x] 優先在標點或字幕間隔處斷幕。
- [x] 場景不超過 `max-sec`，除非單一 cue 本身超長並明確警告。

## D. 標注

- [x] 圖片與 canvas 尺寸一致。
- [x] sequence 連續、ID 唯一、區域在畫布內。
- [x] 所有時間均在場景內，結尾停留符合設定。
- [x] 過度遮罩與時間重疊會產生警告。

## E. 渲染

- [x] 首幀為空白畫布。
- [x] grid 與 skeleton 均可完成 smoke render。
- [x] 未開始元素不提前露出。
- [x] 最後一幀包含全部已標注內容。
- [x] 輸出 MP4 非空且可由 OpenCV 或 ffprobe 讀取。

## F. 跨平台

- [x] 預覽圖不依賴單一 Windows 字型路徑。
- [x] 所有 Python 路徑使用 `pathlib`。
- [x] 無 ffmpeg 時仍能輸出基本 MP4，並回報缺少完稿能力。

## G. 自動驗收

```bash
python scripts/generate_demo_assets.py
pytest
python scripts/run_acceptance.py examples/demo/project.yaml
```

三個命令均應成功，且 `examples/demo/output/final.mp4` 存在。

## 實測結果（2026-08-15）

- `pytest -q`：7 tests passed。
- `run_acceptance.py`：9/9 checks passed。
- Demo 單幕：H.264、640×360、15 fps、各 6 秒。
- Demo 合併：H.264、180 frames、12 秒。
- `examples/demo/build/acceptance-report.json`：`valid: true`。

## 實測結果（2026-08-19 熱路徑優化）

- `pytest -q`：15 tests passed（含 wipe／grid／region clamp）。
