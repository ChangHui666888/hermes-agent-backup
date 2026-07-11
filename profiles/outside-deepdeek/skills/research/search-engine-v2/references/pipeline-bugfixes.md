# Pipeline Bugfixes & Engineering Pitfalls

## db.close() 顺序陷阱 (2026-07-11)

**现象**: `sqlite3.ProgrammingError: Cannot operate on a closed database.`

**原因**: 在 `db.close()` 之后执行数据库查询。

```python
# ❌ 错误 — 查询在 close 之后
db.close()
cum = db.execute("SELECT ...")  # 💥 数据库已关闭

# ✅ 正确 — 查询在 close 之前
cum = db.execute("SELECT ...")
db.close()
```

**修复位置**: `news_intel/pipeline.py:141-150` — 累计统计查询移到 `db.close()` 之前。

## Report 统计口径混淆 (2026-07-10)

旧版 report 的 `processed`/`tier_a`/`tier_b`/`tier_c` 语义混乱——既是本轮批次又是累计。

**新格式**: 明确区分 `batch_*`（本轮）和 `total_*`（全库累计）。

```python
report = {
    "batch_input": 22,       # 本轮 RSS 输入
    "batch_new": 22,         # 实际新文章（去重后）
    "batch_duplicate": 0,    # 已评分跳过
    "batch_tier_a": 0,       # 本轮 Tier A
    "batch_pushed": 19,      # 本轮推送成功
    "total_a": 5,            # 累计 Tier A
    "total_articles": 120,   # 累计入库
    "duration_pipeline_sec": 0.8,
    "duration_push_sec": 1.5,
    "duration_total_sec": 2.3,
}
```

## Qwen3 合并调用 (2026-07-10)

旧版: 每篇 3 次 `_call_qwen`（tags + entities + summary），3 × 13s = 39s/篇。

新版: 合并为 1 次调用 (`QMERGE_PROMPT`)，1 × 13s = 13s/篇。

```python
QMERGE_PROMPT = """分析以下新闻，只输出JSON:
{"tags":["标签1"],"companies":["公司"],"persons":["人物"],"summary_cn":"20字摘要"}"""
```

## Cloud Push 批量优化 (2026-07-11)

旧版: 19 篇文章 × 单篇 POST × 1.4s = 27s。

新版: `POST /internal/news/batch` 一次请求发送全部，≈2s。
