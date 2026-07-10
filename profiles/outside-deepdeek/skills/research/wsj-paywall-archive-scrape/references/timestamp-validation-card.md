# V1 时间戳验证速查卡 — WSJ 专用

## 五条硬规则（伪代码）

### 1️⃣ URL年份优先规则
```
if URL_extracted_year != Content_displayed_year:
    flag = HIGH_RISK  # 例: URL有2025, 内容写June 30, 2026
    STOP — 不要用此URL
```

### 2️⃣ Last Updated 硬约束
```python
# 搜索摘要中的 Last Updated 字段是最高优先级信号
LAST_UPDATED = TRUSTED_SOURCE  # 如 "Last Updated: June 30, 2025 at 9:44pm ET"
if URL_year != LAST_UPDATED_year:
    override all other signals
```

### 3️⃣ 多源一致性检查
```python
signals = [
    extract_year_from_url(url),        # URL 路径年份
    extract_year_from_title(),         # 标题提及年份
    extract_year_from_content(),       # 正文年份
    extract_last_updated_year(),       # 搜索摘要 Last Updated
]
if len(set(filter(None, signals))) > 1:
    MUST_NOT_PROCEED  # 任何两个不一致 → 重新搜索
```

### 4️⃣ Wayback 降级规则
```
Wayback = archival evidence, NOT temporal truth source
- 返回的是"曾存在过的页面快照"，不一定是最新正确版本
- 06-30-2025 的快照可能包含 2026 年内容（URL被跨年复用）
- 优先 web_extract 直连；Wayback 仅作备份
- 使用后必须标注 "数据来源: web.archive.org 历史快照"
```

### 5️⃣ 冲突触发机制（关键）
```python
ANY inconsistency among:
  ① URL 年份  ② 标题/描述日期  ③ Last Updated
→ FORCE re-query live source until timeline-consistent URL found
```

## 执行前 Checklist

- [ ] URL 中的年份段（如 `06-30-2025`）与内容年份一致？
- [ ] 搜索摘要中的 `Last Updated` 年份与 URL 年份一致？
- [ ] 标题中出现的年份与以上两者一致？
- [ ] 如果走 Wayback Machine，快照时间戳对应的是正确日期？
- [ ] 如果以上任意项不一致 → **不要执行**，重新搜索
