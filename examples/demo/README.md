# 可替換主體 Demo

這個示範刻意不使用猴子或固定吉祥物，兩幕主體為：

1. 設計師、想法、產品原型。
2. 使用者、受測原型、迭代結果。

所有主體都在 `project.yaml.subject_profile.subjects` 中設為 `replaceable: true`。

## 重新產生與驗收

在 Skill 根目錄執行：

```bash
python scripts/generate_demo_assets.py
python scripts/run_acceptance.py examples/demo/project.yaml
```

主要產出：

- `output/final.mp4`：兩幕合併成片。
- `build/final-contact-sheet.png`：成片不同時間點的抽幀檢查表。
- `build/previews/`：區域、順序與時序標注圖。
- `build/acceptance-report.json`：端到端驗收報告。

## 替換主體示例

```bash
python scripts/set_subject.py examples/demo/project.yaml \
  --replace-id creator --id narrator \
  --kind human --name "新旁白角色" \
  --appearance outfit=green \
  --set-default --backup
```

這會同步更新場景綁定與 annotation。圖片本身仍需重新產生或手動替換，再重新檢查 region 與遮罩。
