# Universal Whiteboard Animation — Specification

## 1. 目標

將時間化文字與場景圖轉成可重現、可驗證、可替換主體的白板繪製影片。

## 2. 非目標

- 不負責訓練圖片或影片生成模型。
- 不保證任何第三方模型能百分之百維持角色身份。
- 不把單一案例角色、風格或品牌當成固定模板。

## 3. 資料來源

`project.yaml` 是專案層 source of truth；每幕 `*.annotation.json` 是渲染層 source of truth。
場景圖的像素尺寸必須與 annotation `canvas` 完全一致。

## 4. 主體替換

每幕元素可用 `subjectIds` 綁定零到多個主體。替換主體時，不改變字幕時間、區域順序與敘事角色；若新主體比例差異造成越界，必須重新標注區域。

## 5. 遮罩

- `subtract-later`：當前 region 扣除後續 region 與 protectedRegions。
- `explicit`：只扣除 protectedRegions。
- `none`：不自動扣除。

所有遮罩運算在輸出畫布座標執行，從原圖座標按比例縮放。

## 6. 時序

- `sequence` 為 1 起算連續整數。
- `startMs >= 0`、`durationMs > 0`。
- `startMs + durationMs <= sceneDurationMs`。
- 預設元素不重疊；重疊視為警告而非必然錯誤。
- `sceneDurationMs - lastEndMs >= finalHoldMs`。

## 7. 渲染

- 起始畫面為單色背景。
- ink stage 只揭示 ink mask。
- color stage 只揭示 content mask。
- 已揭示像素持久保留。
- 指標／筆尖只疊加在當前輸出幀，不寫入持久畫布。
- 可使用 grid 或 morphological skeleton 路徑。
- 若元素含 `handPath.points`，墨水路徑優先使用該中線；`handPath.contour` 作為精確允許遮罩。

## 8. 完稿

ffmpeg 可用時輸出 H.264、`yuv420p`、`faststart`。音訊預設 AAC；soft subtitle 在 MP4 使用 `mov_text`。

## 9. 錯誤處理

任何結構錯誤回傳非零 exit code。可恢復警告寫入 JSON report，但不阻止低解析度預覽；全清輸出前建議零錯誤。
