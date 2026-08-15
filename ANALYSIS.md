# 原專案分析與轉換報告

## 結論

原專案的真正價值不是「猴子山搶香蕉」故事，而是以下五個技術組合：

1. 用 SRT 的時間軸控制場景總長與內容順序。
2. 用語意事件建立 `sequence`，避免只按畫面座標機械揭示。
3. 用 `region`、後續區域與 `protectedRegions` 防止未開始物件提前出現。
4. 在同一張持久畫布上，以連續路徑先落墨再添彩。
5. 先做標注預覽，再逐幕輸出與合併。

因此，猴子只是案例素材，不應成為 Skill 的角色預設或資料模型。

## 原版優點

- 工作流從字幕到 MP4 相對完整。
- `annotation.json` 把敘事、時間、區域與遮罩放在同一份資料中。
- `protectedRegions` 解決矩形分區容易洩漏後續物件的問題。
- grid 與 skeleton 兩種路徑兼顧穩定與貼線。
- 本機 HTML 預覽台降低修改 JSON 的門檻。
- 採用 MIT，可合法修改與再散布，但必須保留授權聲明。

## 原版限制

1. 說明、範例與預設高度集中在猴子故事，容易讓代理把案例誤認成硬規則。
2. 視覺風格固定為暖米黃 Notion 式草圖，缺少品牌、技術圖、課堂白板等設定。
3. 每一步都強制停下等待確認，不適合 Codex 的長任務或批次模式。
4. `render_annotation_preview.py` 把字型寫死為 `C:/Windows/Fonts/msyh.ttc`，macOS/Linux 直接失敗。
5. 字幕分幕主要依時間，可能在句子或論述中間切斷。
6. 沒有正式 JSON Schema 與結構驗證器，錯誤通常到渲染時才發現。
7. 依賴沒有版本範圍，跨時間重建環境的可重現性較差。
8. 多幕 PyAV 回退只處理影像，沒有完整音訊／字幕完稿流程。
9. 缺少測試與自動成片驗收。
10. 主要 stream 核心過大，功能耦合較高，不利於替換路徑或指標。

## 本版轉換決策

- 新增 `subject_profile`、`subjectBindings` 與 `set_subject.py`，主體不再硬編碼，且可同步替換場景與標注綁定。
- 新增四種 workflow mode，兼顧代理自動化與人工審核。
- 分幕加入標點、字幕間隔與最大時長判斷。
- 建立 Project / Annotation Schema 與驗證報告。
- 重寫跨平台預覽圖與 HTML 預覽台。
- 改用程序化筆尖作預設，避免固定素材、浮水印與授權混淆。
- 加入 batch render、finalize、soft/burn subtitles 與音訊 mux。
- 加入 demo、pytest 與 end-to-end acceptance。

## 相容性

本版仍接受原版常見的 annotation 欄位：

- `sceneId`
- `canvas.width` / `canvas.height`
- `storyBasis`
- `sceneDurationMs`
- `elements[].sequence`
- `elements[].region`
- `elements[].reveal.startMs`
- `elements[].reveal.durationMs`
- `elements[].reveal.direction`
- `elements[].reveal.protectedRegions`
- `elements[].handPath`

新增欄位皆有預設，因此原版標注通常可直接送入驗證器與渲染器。
