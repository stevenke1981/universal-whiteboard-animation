---
name: universal-whiteboard-animation
description: 將 SRT、VTT、逐字稿或短影音文案轉成可替換人物／動物／物件／產品／抽象概念的白板手繪動畫，並可依權威筆畫資料與正確筆順逐筆寫中文字。流程包含語意分幕、主體設定、像素級標注、遮罩防洩漏、連續筆跡、中文 stroke mask／median 運筆、驗收、音訊與字幕完稿。當使用者要求「SRT 做白板動畫」「字幕轉手繪動畫」「逐字稿做解說動畫」「寫中文字」「中文筆順動畫」「製作白板短片」時觸發。
---

# 通用 SRT 白板動畫 Skill

把字幕或文案轉成「依敘事順序逐步畫出」的白板動畫。**不得預設猴子或任何固定主角**；主體可為單一角色、多人、動物、商品、機械、場景、圖表、流程、歷史人物或抽象概念，也可完全沒有固定主角。

## 核心原則

1. **字幕驅動，不是座標驅動。** 先讀懂事件與論述，再決定繪製順序；不可只依畫面由左到右排序。
2. **主體是設定，不是模板常數。** 從 `project.yaml.subject_profile` 與每幕 `subjectBindings` 取得主體；未指定時依內容推導，並標記為可替換。
3. **一幕一個核心意思。** 每幕應有清楚的前提、關鍵主體／物件、變化或動作、結果；知識型內容可改用「問題 → 原理 → 方法 → 結果」。
4. **未開始的內容不可提前露出。** 每個元素的允許遮罩由 `region`、後續元素與 `protectedRegions` 共同決定。
5. **持久畫布與連續筆跡。** 已完成的內容保留；筆尖沿 grid 或 skeleton 路徑移動，先落墨、再添彩。
6. **可驗收。** 每幕在渲染前必須通過結構、座標、順序、時序、遮罩與結尾停留檢查。
7. **中文筆順不可只靠字型輪廓猜測。** 正確模式以逐字 `strokes` 陣列決定筆順、`medians` 決定起筆與運筆方向；缺資料時只能明確標記為近似。

## 支援輸入

- SRT / WebVTT 字幕
- 純文字逐字稿或腳本
- 已完成的分鏡表
- 使用者提供的線稿／插畫
- 選用：旁白音訊、背景音樂、既有角色參考圖

輸入不足時採用保守預設並寫入 `assumptions`；不要因可合理推導的小缺項中斷整體任務。

## 主體模型

`subject_profile.mode` 可用：

- `none`：無固定主角，以圖示、流程、物件或場景表達。
- `single`：單一固定角色，跨幕鎖定身份特徵。
- `ensemble`：多人／多角色，為每個角色建立獨立 ID。
- `object`：產品、工具、車輛、機器或其他物件為主體。
- `concept`：抽象概念擬人化或符號化。
- `adaptive`：依每幕內容自動選擇，預設模式。

每個主體可包含：`id`、`kind`、`name`、`appearance`、`identity_lock`、`replaceable`、`negative_constraints`。角色參考圖是身份約束，不可被故事範例覆蓋。

替換既有主體時，使用 `scripts/set_subject.py` 同步更新 `project.yaml` 的 `subject_profile`、每幕 `subject_bindings` 與 annotation 的 `subjectIds`，避免只改角色名稱卻留下舊綁定：

```bash
python scripts/set_subject.py project.yaml \
  --replace-id old-character --id new-character \
  --kind human --name "新角色" --set-default --backup
```

使用 `--dry-run` 可先查看影響範圍；替換後仍須重新檢查圖片比例、region 與遮罩。

## 工作模式

由 `project.yaml.workflow.mode` 控制：

- `auto`：代理可從規劃一路執行到驗收；遇到缺少必要檔案或不可恢復錯誤才停止。
- `checkpoint`：在「分幕策略」「線稿」「標注預覽」「成片」四個高成本節點等待確認。
- `plan-only`：只輸出分幕、主體與視覺策略，不生成圖片或影片。
- `validate-only`：只檢查現有專案與標注，不改內容。

除非使用者指定 `checkpoint`，不得把每個小步驟都設成強制等待。

## 標準流程

### 1. 正規化與分幕

執行：

```bash
python scripts/parse_srt.py <字幕.srt> \
  --target-sec 22 --min-sec 8 --max-sec 35 \
  --prefer-punctuation --gap-sec 1.2 \
  --output build/parsed-scenes.json
```

分幕優先考慮句號、問號、驚嘆號、段落轉折與字幕空檔；只有超過上限時才強制切斷。對短影音可用 6–15 秒；課程與知識解說可用 18–35 秒。

### 2. 建立場景策略

每幕至少輸出：

- `sceneId`
- 字幕範圍與 `sceneDurationMs`
- `coreMessage`
- `narrativePattern`
- `subjectBindings`
- `visualMetaphor`
- `composition`
- `elements` 建議清單
- `imagePrompt`
- `negativePrompt`

角色故事不是唯一模式；可依內容選用：

- 故事型：場景 → 主體 → 動作／衝突 → 反應／結果
- 教學型：問題 → 原理 → 步驟 → 完成狀態
- 商業型：痛點 → 方案 → 證據 → 行動
- 歷史型：背景 → 人物／事件 → 轉折 → 影響
- 技術型：輸入 → 元件 → 資料流 → 輸出／限制

### 3. 產生或接受場景圖

預設 16:9，背景與視覺由 `visual.preset` 控制。可用預設：

- `minimal-paper`：暖米黃紙張、深灰線條、少量紅橙藍點綴。
- `classroom-marker`：白板底、藍黑麥克筆、簡單箭頭。
- `cute-story`：圓潤人物與物件、低飽和配色。
- `technical-diagram`：乾淨節點、連線、裝置輪廓。
- `brand-custom`：依 `visual` 自訂色與材質。

圖片必須保留足夠留白與元素間距。預設不在一般插畫源圖內生成文字；需要「逐筆寫中文字」時，改用第 7 節產生獨立 `strokeMask` 與 `handPath.points`，不可把 AI 圖片中的字當成可驗證筆順。

### 4. 建立像素級標注

圖片與標注同名：

```text
scene-01-idea.png
scene-01-idea.annotation.json
```

每個元素必須包含：

- `id`、`label`、`sequence`、`type`
- `narrativeRole`、`subtitle`
- `subjectIds`
- `region`：原圖整數像素座標
- `reveal.startMs`、`durationMs`、`direction`
- `reveal.protectedRegions`
- 選用：`maskPolicy`、`zIndex`、`handPath`

不得只憑字幕猜座標；標注前必須實際查看圖片並取得原圖尺寸。

### 5. 驗證

```bash
python scripts/validate_annotation.py \
  scene.png scene.annotation.json \
  --report build/scene-validation.json
```

錯誤必須修正：畫布尺寸不符、區域越界、ID 重複、sequence 不連續、負時長、元素結束超過場景、未保留結尾畫面。

警告應評估：時間重疊、區域被後續遮罩扣除過多、主體沒有對應字幕、元素密度過高。

### 6. 產生區域檢查圖與預覽

```bash
python scripts/render_annotation_preview.py \
  scene.png scene.annotation.json build/scene-regions.png
```

或開啟：

```text
assets/preview.html
```

預覽台可載入資料夾或單一圖像／標注，調整區域、順序、時序、方向、字幕與主體綁定，並保存／下載 JSON。

### 7. 依正確筆順逐筆寫中文字

需要逐筆寫中文字時，使用 `scripts/chinese_stroke_split.py`。**不可把字型 contour
數量或矩形位置排序當成正確筆順。** TTF/TTC 只保存字面外框，正式模式必須使用含
`strokes` 與 `medians` 的逐字資料：

```bash
python scripts/chinese_stroke_split.py \
  --text "日日是好日" \
  --stroke-data /path/to/hanzi-writer-data \
  --strict-stroke-order \
  --size 250 --width 1920 --height 1080 \
  --scene-id scene-01-strokes --out-dir .
```

也可用 `--stroke-source data`。嚴格模式下，任何漢字缺少資料都必須失敗，不可靜默
改用猜測。`--stroke-source auto` 可資料優先並允許 fallback，但所有 fallback element
必須標記：

```json
{
  "strokeOrderConfidence": "approximate",
  "strokeSource": "font-glyph-fallback"
}
```

正確中文書寫遵守下列不變條件：

1. 原字依輸入 Unicode 使用，不自動簡繁轉換或替換異體字。
2. 文字依原字序由左至右排版。
3. 單字依 `strokes` 陣列順序逐筆書寫；資料順序優先於通用筆順口訣。
4. 每筆依對應 `medians` 第一點走到最後一點，不得為縮短路徑而反向。
5. 橫折、豎鉤、撇折等複合筆畫在同一 element 內連續書寫，中途不抬筆。
6. 每一筆使用獨立 `strokeMask`，交叉時只揭示當前筆畫，不可洩漏後續筆畫。
7. 「先上後下、先左後右、先橫後豎、先撇後捺、先外後內再封口、先中間後兩邊」只作人工驗收提示，不可取代逐字資料。
8. 權威 element 必須同時有 `strokeMask`、`handPath.points` 與 `strokeOrderConfidence: authoritative`。

輸出：

```text
scenes/<scene-id>.png
scenes/<scene-id>.annotation.json
build/strokes/<scene-id>-stroke-NNN.png
```

渲染器在 `reveal.mode: write` 或 `type: text-stroke` 時，會把全部時長用於沿 median
書寫，不再執行一般插畫的 `ink → color` 兩階段。驗證器會檢查 mask 是否存在、尺寸
是否與 canvas 一致、可見像素是否在 region 內，以及 median 是否至少有兩個畫布內點。

筆畫資料不隨本 Skill 重新散布；若使用 Hanzi Writer Data 或 Make Me a Hanzi 資料，
必須遵守並保留其各自授權。完整說明見 `docs/CHINESE_WRITING.md`。

### 8. 渲染單幕

```bash
python scripts/render_whiteboard.py \
  scene.png scene.annotation.json output/scene.mp4 \
  --ink-path skeleton \
  --color-fill wipe \
  --pointer pen
```

低成本預覽可加：

```bash
--fps 15 --cap-long-edge 640
```

全清成片建議 30 fps。`cap_long_edge` 必須大於等於畫布長邊才會保留原解析度：1920×1080 設 1920、1280×720 設 1280，`0` 表示不縮放；低成本預覽可設 640。線稿不清楚時用 `grid`；輪廓清楚時用 `skeleton`。中文字權威筆畫會優先使用 `handPath.points`，不受 grid／skeleton 的反向排序影響。

### 9. 批次與完稿

```bash
python scripts/batch_render.py project.yaml
python scripts/finalize_video.py \
  --inputs output/scene-*.mp4 \
  --output output/final.mp4 \
  --audio narration.wav \
  --subtitles story.srt --subtitle-mode soft
```

若系統有 ffmpeg，優先輸出 H.264/yuv420p 並支援音訊與字幕；沒有 ffmpeg 時保留 OpenCV 可播放輸出並清楚回報限制。

## 遮罩規則

預設 `maskPolicy: subtract-later`：

```text
允許遮罩 = 當前 region
         − 所有後續元素 region
         − 當前元素 protectedRegions
```

可改用：

- `explicit`：只扣除 `protectedRegions`，適合大範圍背景與前景重疊。
- `none`：不扣除後續區域，僅適合不重疊元素。

當後續矩形扣除目前區域超過 80%，驗證器應發出警告，避免大矩形造成過度遮罩。

## 時序規則

- `sceneDurationMs` 以該幕字幕跨度為基礎。
- 預設一支筆依序作畫；元素時間不重疊。
- 每元素 `ink:color` 預設 2:1，可由專案覆寫。
- 最後元素完成後至少保留 `finalHoldMs`，預設 700ms。
- 一般插畫的 `direction` 主要控制上色與預覽代理；真實落墨由 grid／skeleton 路徑決定。
- 中文 `text-stroke` 的順序由 `sequence/strokeIndex`，方向由 `handPath.points` 第一點至最後一點決定；不得反向。

## 自動驗收

成片至少檢查：

1. 首幀只有設定的畫布底色，沒有未開始元素。
2. 任選一個重疊區域的中段幀，後續元素不可洩漏。
3. 筆尖與目前落墨位置距離合理。
4. 每幕最後完整顯示已標注內容，且停留時間符合設定。
5. 多幕順序與字幕分幕一致。
6. 有音訊時，輸出時長差不得超過 250ms；字幕時間不得超過輸出總長。
7. 中文字至少抽查一個交叉筆畫：前一筆完成時，後一筆的專屬區域仍須保持背景；每筆運動方向符合 median。

執行整包驗收：

```bash
python scripts/run_acceptance.py examples/demo/project.yaml
```

## 產出規範

預設建立：

```text
<專案>/
├── project.yaml
├── input/
├── scenes/
│   ├── scene-01-*.png
│   └── scene-01-*.annotation.json
├── build/
│   ├── parsed-scenes.json
│   ├── validation/
│   └── previews/
└── output/
    ├── scene-01.mp4
    └── final.mp4
```

所有回報使用繁體中文與台灣用語；技術名詞、CLI、JSON 欄位與程式碼可保留英文。
