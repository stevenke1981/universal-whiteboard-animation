# Universal Whiteboard Animation Skill

一套可直接交給 ChatGPT Codex、OpenCode 或一般程式代理使用的通用白板動畫 Skill。
它把 SRT / WebVTT / 逐字稿轉成依敘事順序繪製的影片，保留原專案最有價值的
「字幕驅動、語意排序、區域遮罩、連續筆跡、持久畫布」設計，但不再綁定猴子、
固定角色或單一故事風格。

## 與原版相比

| 項目 | 原版 | 本版 |
|---|---|---|
| 主體 | 範例與說明集中在猴子故事 | `subject_profile` 可換人物、動物、物件、產品、概念或無主角 |
| 工作流 | 每一步強制確認 | `auto`、`checkpoint`、`plan-only`、`validate-only` |
| 分幕 | 主要依秒數 | 標點、語意停頓、字幕間隔與最大時長共同決定 |
| 視覺 | 暖米黃 Notion 風固定 | 多個 preset，可完全自訂 |
| 標注 | 有格式但缺正式 Schema | JSON Schema + CLI 驗證器 |
| 預覽圖 | Windows 字型路徑寫死 | Windows/macOS/Linux 字型自動偵測 |
| 筆尖素材 | 依賴固定 PNG | 預設程序化筆尖；仍可傳入自訂 RGBA PNG |
| 完稿 | 合併 MP4 | 合併、H.264、音訊、soft/burn subtitles |
| 自動化 | 人工檢查為主 | smoke test、驗收報告、批次執行 |

## 30 秒開始

```bash
python scripts/prepare_env.py
# 末行會輸出 ENV_PY=...

<ENV_PY> scripts/generate_demo_assets.py
<ENV_PY> scripts/run_acceptance.py examples/demo/project.yaml
```

輸出位置：

```text
examples/demo/output/
```

## 建立自己的專案

```bash
python scripts/init_project.py \
  --source /path/to/story.srt \
  --project-dir /path/to/my-whiteboard \
  --subject-mode adaptive
```

接著放入每幕圖片與同名標注，再執行：

```bash
python scripts/batch_render.py /path/to/my-whiteboard/project.yaml
```

## 安裝成 Agent Skill

本套件本身就是一個 Skill 資料夾。使用通用安裝器複製到你的代理 Skill 根目錄：

```bash
python scripts/install_skill.py --target-dir /path/to/your/skills
```

安裝後資料夾名稱為 `universal-whiteboard-animation`。

## 主體替換範例

```yaml
subject_profile:
  mode: single
  default_id: host
  subjects:
    host:
      kind: human
      name: 小宇
      replaceable: true
      appearance:
        age_group: young_adult
        hair: short_black
        outfit: orange_hoodie
      identity_lock:
        - face_shape
        - hairstyle
        - outfit_silhouette
```

要改成產品主體：

```yaml
subject_profile:
  mode: object
  default_id: device
  subjects:
    device:
      kind: product
      name: 智慧翻譯機
      replaceable: true
      appearance:
        shape: rounded_rectangle
        screen: large_center_display
```

完全不需要固定主角：

```yaml
subject_profile:
  mode: none
  subjects: {}
```

### 直接替換既有主體

下列命令會把 `creator` 改成 `host`，同時更新 `project.yaml` 的場景綁定與所有已存在 annotation 的 `subjectIds`：

```bash
python scripts/set_subject.py project.yaml \
  --replace-id creator --id host \
  --mode single --kind human --name "新主持人" \
  --appearance outfit=blue_jacket \
  --identity-lock face_shape hairstyle outfit \
  --set-default --backup
```

先預演、不寫檔：

```bash
python scripts/set_subject.py project.yaml \
  --replace-id creator --id product \
  --kind product --name "智慧裝置" --dry-run
```

## 重要檔案

- `SKILL.md`：代理執行規則與工作流。
- `ANALYSIS.md`：原專案分析、問題與轉換決策。
- `SPEC.md`：資料模型、行為與相容性規格。
- `PLAN.md`：實作與後續擴充計畫。
- `ACCEPTANCE.md`：驗收條件。
- `schemas/`：project 與 annotation JSON Schema。
- `assets/preview.html`：不需伺服器的標注預覽台。
- `scripts/render_whiteboard.py`：通用單幕渲染器。

## 授權

MIT。改作來源與差異請見 `NOTICE.md`。
