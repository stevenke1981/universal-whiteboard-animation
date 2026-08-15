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

## F. 中文正確筆順書寫

- [x] 可讀取 Hanzi Writer Data 逐字 JSON 目錄。
- [x] 可讀取 Make Me a Hanzi `graphics.txt`／JSONL。
- [x] `strokes` 與 `medians` 數量不一致時拒絕資料。
- [x] `strokes` 陣列順序直接成為 element 順序，不以 contour 幾何重新排序。
- [x] `handPath.points` 保留 median 起點至終點，不為最短路徑反向。
- [x] 每一筆輸出獨立 `strokeMask`，交叉筆畫不洩漏後續筆畫專屬區域。
- [x] 複合筆畫在同一 element 內不中途抬筆。
- [x] 簡繁體與異體字依輸入 Unicode 查資料，不自動替換。
- [x] `--strict-stroke-order` 缺少任一漢字資料時以非零狀態失敗。
- [x] fallback 明確標記 `strokeOrderConfidence: approximate` 並輸出 warning。
- [x] 權威 element 缺少 mask 或 median 時，驗證器回報 error。

交叉筆畫抽幀驗收以「十」為基準：

1. 第一筆完成時，只看得到橫畫；豎畫上、下段仍為背景。
2. 第二筆依 median 從上往下寫入。
3. 最後一幀完整顯示兩筆。

## G. 跨平台

- [x] 預覽圖不依賴單一 Windows 字型路徑。
- [x] 所有 Python 路徑使用 `pathlib`。
- [x] 字型 fallback 可由 `--font`、`WHITEBOARD_FONT` 或跨平台候選字型指定。
- [x] 無 ffmpeg 時仍能輸出基本 MP4，並回報缺少完稿能力。

## H. 自動驗收

```bash
python -m compileall scripts tests
pytest -q
python scripts/run_acceptance.py examples/demo/project.yaml
```

三個命令均應成功，且 `examples/demo/output/final.mp4` 存在。

## 本次實測結果（2026-08-15）

- `python -m compileall -q scripts tests`：通過。
- `pytest -q`：14 tests passed。
- 既有 Demo 驗收：通過。
- 中文 synthetic「十」：strict validation 0 errors、0 warnings。
- 中文 synthetic「十」：第一筆完成幀未顯示豎畫專屬區域。
- 官方逐字 JSON「十」：SVG path／median 解析、驗證與 H.264 smoke render 通過。
