# 實作與擴充計畫

## 已完成

- 通用 Skill 規則與主體設定。
- SRT / VTT 解析與自然斷點分幕。
- Project / Annotation Schema。
- 跨平台標注預覽。
- grid / skeleton 單幕渲染。
- 批次渲染、合併、音訊與字幕完稿。
- HTML 預覽台。
- Demo、單元測試與端到端驗收。

## 建議下一階段

1. 以影像分割模型自動建立元素 mask，取代矩形區域。
2. 以視覺模型從圖片與字幕自動草擬 annotation，再由人調整。
3. 加入角色 reference sheet 與跨幕 identity score。
4. 支援 SVG 路徑與真正筆畫順序，提升 logo、文字與技術圖品質。
5. 建立 Web UI：專案管理、字幕時間軸、角色庫、批次重算與 GPU 遠端佇列。
6. 加入 Whisper/Qwen ASR，直接從音訊產生時間戳字幕。

## 2026-08-19 熱路徑優化

- 渲染 wipe 不再對整張畫布呼叫 `np.indices`；grid 路徑改為 ink-pixel 索引。
- 中文拆筆快取 FreeType face，region 強制夾在畫布內，檢查圖改裁切輸出。
- `requirements.txt` 補上 `freetype-py` / `fonttools`。
- 中文拆筆寫入 `handPath.contour` 與掃描線中線 `handPath.points`；渲染優先沿中線落墨。
