# 可替換主體設定模板

```yaml
subject_profile:
  mode: adaptive
  default_id: null
  subjects:
    subject-01:
      kind: human | animal | product | object | concept | vehicle | building
      name: 可讀名稱
      replaceable: true
      appearance:
        silhouette: 描述外輪廓
        face: 角色才需要
        hair: 角色才需要
        outfit: 角色才需要
        material: 物件才需要
        palette: ["#000000"]
      identity_lock:
        - silhouette
        - face_shape
        - hairstyle
        - signature_outfit
      negative_constraints:
        - 不可改變物種
        - 不可增加文字或 logo
```

`replaceable: true` 表示主體可以在不改字幕與敘事結構的前提下替換；替換後仍須檢查
比例、區域與遮罩是否有效。
