# 封裝與驗收報告

版本：`1.0.0`  
驗收日期：`2026-08-15`

## 已執行

```text
python -m compileall -q scripts tests       PASS
pytest -q                                   7 passed
node --check assets/preview.html 的 script  PASS
validate_project.py demo/project.yaml       PASS
validate_annotation.py --strict（兩幕）     PASS
run_acceptance.py demo/project.yaml         9/9 checks passed
set_subject.py 跨兩幕同步替換               PASS
```

## Demo 輸出

| 檔案 | Codec | 尺寸 | FPS | 幀數 | 時長 |
|---|---:|---:|---:|---:|---:|
| `scene-01.mp4` | H.264 | 640×360 | 15 | 90 | 6 秒 |
| `scene-02.mp4` | H.264 | 640×360 | 15 | 90 | 6 秒 |
| `final.mp4` | H.264 | 640×360 | 15 | 180 | 12 秒 |

`examples/demo/build/acceptance-report.json` 為機器可讀的完整結果，值為 `valid: true`。

## 驗收重點

- Demo 不使用猴子故事，主體是人物、概念與產品。
- 所有 Demo 主體均為 `replaceable: true`。
- 主體替換可同步更新 project、scene bindings 與 annotation。
- 首幀為乾淨米黃畫布；末幀有完整繪製內容。
- grid 與 skeleton 兩種渲染路徑皆通過 smoke test。
- 預覽圖字型採跨平台偵測，不依賴單一 Windows 路徑。
