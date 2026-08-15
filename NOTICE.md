# 第三方來源與改作說明

本 Skill 參考並改作自下列 MIT 專案的工作流概念：

- `geeklee/srt-whiteboard-animation`
- 原作者：江哥是老登啊
- 原授權：MIT License

保留的核心概念包括：SRT 驅動分幕、`annotation.json` 語意排序、區域遮罩、
`protectedRegions`、持久畫布、連續筆跡與多幕合併。

本改作版重新設計了 Skill 規則、設定格式、字幕分幕、跨平台標注預覽、驗證器、
批次流程、程序化筆尖、音訊／字幕完稿工具、測試與範例。它不預設猴子，也不綁定
任何固定角色或故事類型。

## 中文筆畫資料

中文字正確筆順功能可讀取 Hanzi Writer Data 或 Make Me a Hanzi 相容的逐字
`strokes`／`medians` 資料。本 repository **不內嵌完整第三方筆畫資料**；使用者需在
本機另外提供資料路徑。

這些資料不是本專案 MIT License 的一部分，並可能採用 Arphic Public License 或來源
repository 指定的其他授權。若將第三方筆畫資料連同應用程式重新散布，必須保留該資料
來源的授權文字、著作權與必要聲明。只提交本專案產生的場景圖、annotation 或影片，也
應依實際使用情境確認第三方資料授權要求。
