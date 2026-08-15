# 中文字逐筆書寫設計與使用規範

## 1. 目標

讓白板動畫不是「把整個字擦出來」，而是依正確筆順，使用筆尖沿每一筆的實際書寫方向
逐步寫出中文字。正確模式必須能回答：

- 這是第幾筆？
- 這一筆從哪裡開始、在哪裡結束？
- 中間轉折與鉤是否仍屬同一筆？
- 與前後筆畫交叉時，哪些像素現在可以顯示？

## 2. 為何字型輪廓不能代表筆順

字型 glyph 的 contour 是印刷外框。它通常不保存筆畫編號、運筆方向、抬筆點或筆順。
相連筆畫可能被合成同一輪廓，一筆也可能因內外框被拆成數個 contour。因此本專案把
字型輪廓視為 fallback，而不是正確筆順的資料來源。

## 3. 權威資料模型

每個字至少需要：

```json
{
  "character": "十",
  "strokes": ["<SVG path 1>", "<SVG path 2>"],
  "medians": [
    [[109, 442], [932, 476]],
    [[456, 811], [507, -33]]
  ]
}
```

- `strokes[n]`：第 `n+1` 筆的完整填充輪廓，陣列順序就是筆順。
- `medians[n]`：同一筆由起點至終點的中心線，決定筆尖運動方向。
- `strokes` 與 `medians` 數量必須完全相同。
- median 至少需要兩個點，且不可自行反向。

支援 Hanzi Writer Data 逐字 JSON、Make Me a Hanzi `graphics.txt`／JSONL、單一 JSON、
JSON mapping 與 JSON list。

## 4. 座標規則

Make Me a Hanzi／Hanzi Writer 資料使用 1024×1024 字框，常見座標的左上角為
`(0, 900)`、右下角為 `(1024, -124)`，y 軸向下時必須轉換：

```text
canvas_x = origin_x + source_x × size / 1024
canvas_y = origin_y + (900 - source_y) × size / 1024
```

這個轉換同時套用 stroke path 與 median，才能保留真正的起筆方向。

## 5. 中文筆順與運筆規則

資料順序優先於任何口訣。人工檢查可參考：

- 先上後下。
- 先左後右。
- 先橫後豎。
- 先撇後捺。
- 先外後內，封閉結構通常最後封口。
- 部分字先中間後兩邊。

這些是一般規律，不是可覆蓋所有字的演算法。正式輸出遵守以下不變條件：

1. **原字不替換：** 不自動簡繁轉換或改用異體字。
2. **順序不猜測：** 單字依 `strokes` 陣列順序。
3. **方向不反轉：** 每筆依 median 第一點到最後一點。
4. **複合筆畫不中斷：** 橫折、豎鉤、撇折等同一 stroke 中途不抬筆。
5. **筆間才抬筆：** 一個 element 代表一筆；下一 element 才是下一筆。
6. **交叉不洩漏：** 每筆有獨立 `strokeMask`；當前筆只揭示自己的 mask。
7. **缺資料不冒充：** fallback 一律標記 `strokeOrderConfidence: approximate`。

## 6. Annotation 合約

權威筆畫 element 必須同時具備：

- `type: text-stroke`
- `reveal.mode: write`
- `strokeMask`
- `strokeOrderConfidence: authoritative`
- `character`、`characterIndex`
- `strokeIndex`、`strokeCount`
- `handPath.points`，至少兩個畫布座標點

驗證器會拒絕：

- mask 不存在、空白或尺寸不符；
- mask 可見像素超出 region；
- median 點格式錯誤或超出畫布；
- `authoritative` 卻缺少 mask 或 median。

## 7. 資料來源與授權

本專案不內嵌或重新散布完整筆畫資料。使用者可在本機安裝 Hanzi Writer Data，或提供
Make Me a Hanzi `graphics.txt`。這些資料有各自的第三方授權；若要把資料一起打包、
部署或散布，必須保留來源專案要求的授權文字與聲明。只引用資料路徑、不把資料提交到
本 repository，可避免把第三方資料誤納入本專案的 MIT License。

## 8. 建議命令

嚴格模式：

```bash
python scripts/chinese_stroke_split.py \
  --text "天地人" \
  --stroke-data /path/to/hanzi-writer-data \
  --strict-stroke-order \
  --size 260 --width 1920 --height 1080 \
  --scene-id tiandiren --out-dir .
```

資料優先、缺字允許 fallback：

```bash
python scripts/chinese_stroke_split.py \
  --text "天地人！" \
  --stroke-data /path/to/hanzi-writer-data \
  --stroke-source auto \
  --font /path/to/CJK-font.ttc \
  --scene-id tiandiren --out-dir .
```

驗證：

```bash
python scripts/validate_annotation.py \
  scenes/tiandiren.png scenes/tiandiren.annotation.json --strict
```

渲染：

```bash
python scripts/render_whiteboard.py \
  scenes/tiandiren.png scenes/tiandiren.annotation.json \
  output/tiandiren.mp4 --pointer pen --cap-long-edge 1920
```

## 9. 驗收重點

至少抽查一個有交叉筆畫的字，例如「十」：

- 第一筆橫完成時，只能看到橫畫；豎畫的上、下段仍是背景。
- 第二筆由 median 起點開始，按正確方向寫到終點。
- 交叉點可以在第一筆出現，但不可因此提前顯示豎畫其餘像素。
- 最後一幀完整顯示兩筆，結尾停留符合 `finalHoldMs`。
