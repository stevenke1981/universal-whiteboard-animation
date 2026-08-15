# 場景圖提示詞模板

請依下列資料建立一張白板動畫來源圖。主體不是固定猴子，必須使用場景提供的
`subjectBindings` 與 `subject_profile`。

## 變數

- 專案風格：`{{visual_preset}}`
- 畫布：`{{width}}x{{height}}`，`{{aspect_ratio}}`
- 場景核心：`{{core_message}}`
- 敘事模式：`{{narrative_pattern}}`
- 主體：`{{subject_bindings}}`
- 必要元素：`{{elements}}`
- 構圖：`{{composition}}`
- 背景色：`{{background}}`
- 線條色：`{{line_color}}`
- 點綴色：`{{accent_colors}}`

## 正向提示

極簡、清楚、可分區的白板手繪插圖；每個必要元素之間保留足夠留白；視覺層級
符合敘事順序；主體身份與參考設定一致；線條乾淨；背景簡潔；適合依區域逐步繪製。

## 負向提示

不要加入未要求的猴子、猩猩或固定吉祥物；不要文字、字母、數字、浮水印、logo；
不要攝影、寫實皮膚、3D、複雜材質、密集背景、過度重疊、裁切主體、額外肢體、
身份漂移、高飽和度雜色。
