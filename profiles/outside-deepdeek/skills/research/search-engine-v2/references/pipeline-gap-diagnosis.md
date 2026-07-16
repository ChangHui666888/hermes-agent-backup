# Pipeline Gap Diagnosis — 数据缺口根因诊断手册

> 当 pipeline_check.py 报 FETCHER FAIL 时，用此文档快速定位三层缺口根因。

## 三层数据缺口

```
RSS_raw (23,827)
  │
  ├─ sync+scorer ──→ news_intelligence (4,445)
  │                   ├─ tier A: ~6
  │                   ├─ tier B: ~416
  │                   └─ tier C: ~4,023 (不参与抓取)
  │
  ├─ fetch ──→ news_content (369 rows)
  │             ├─ 有正文: 84 (23%)
  │             ├─ 空内容: 285 (77%) ← 核心故障
  │             └─ 策略分布: direct=76, archive=3, none=285
  │
  └─ no content row: 53 (tier A+B 中完全缺失)
```

## 诊断 SQL

### 1. 快速总览

```sql
-- 基本计数
SELECT
  (SELECT COUNT(*) FROM news_intelligence) AS intel_total,
  (SELECT COUNT(*) FROM news_content) AS content_rows,
  (SELECT COUNT(*) FROM news_content WHERE content_md IS NOT NULL AND content_md != '') AS content_ok;

-- 按策略分布
SELECT COALESCE(fetch_strategy,'none') AS strategy,
       COUNT(*) AS total,
       COUNT(CASE WHEN content_md IS NOT NULL AND content_md != '' THEN 1 END) AS ok
FROM news_content GROUP BY strategy ORDER BY total DESC;
```

### 2. 定位占位行

```sql
-- 空内容占位行 (content_md = '' 但 fetch_strategy IS NULL)
SELECT COUNT(*), DATE(created_at) AS day
FROM news_content
WHERE content_md = '' AND fetch_strategy IS NULL
GROUP BY day ORDER BY day;

-- 占位行样本（检查谁创建的）
SELECT article_url, summary_cn, extraction_method, created_at
FROM news_content
WHERE content_md = '' AND fetch_strategy IS NULL
LIMIT 5;
```

### 3. 查缺失覆盖

```sql
-- A+B tier 中哪些没有 content 行
SELECT COUNT(*) FROM news_intelligence ni
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A','B') AND nc.id IS NULL;

-- 哪些没有正文（NULL 或 ''）
SELECT
  COUNT(CASE WHEN nc.id IS NULL THEN 1 END) AS no_row,
  COUNT(CASE WHEN nc.content_md IS NULL AND nc.id IS NOT NULL THEN 1 END) AS null_content,
  COUNT(CASE WHEN nc.content_md = '' AND nc.id IS NOT NULL THEN 1 END) AS empty_content
FROM news_intelligence ni
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A','B');
```

## 常见根因 & 修复

### Root Cause 1: content_md = '' vs IS NULL 陷阱

**症状**: 占位行 content_md = ''（空字符串非 NULL），SQL WHERE 条件 `content_md IS NULL` 跳过它们。

**根因**: 旧版 pipeline 用 INSERT 创建占位行时 content_md 设为 '' 而非 NULL。

**修复**: SQL 条件必须同时检查二者：
```sql
-- ❌ 只检查 NULL — 错过空字符串行
WHERE content_md IS NULL

-- ✅ 同时检查 NULL 和空字符串
WHERE content_md IS NULL OR content_md = ''
-- 或更简洁（SQLite）
WHERE COALESCE(NULLIF(content_md, ''), NULL) IS NULL
```

### Root Cause 2: 占位行阻塞重抓

**症状**: 占位行 content_md='', fetch_strategy=NULL 存在，但 batch.py 永远无法覆盖它们（因 URL 反爬/paywall）。

**根因**: auto-pipeline Step 3 对每批 200 URL 跑 batch.py，失败的不重试。占位行在下一次 cron 可能不被选中（200 LIMIT 随机选）。

**修复**: 加 CLEANUP step — 在 Step 2 之前清理空占位行：
```sql
DELETE FROM news_content
WHERE (content_md IS NULL OR content_md = '')
  AND (fetch_strategy IS NULL OR fetch_strategy = '');
```

### Root Cause 3: 200 LIMIT 瓶颈

**症状**: 422 篇 A+B 需要抓取，但每次 cron 只处理 200。

**根因**: `auto-pipeline.py` LIMIT 200 硬编码。

**修复**: 
- 短期内可接受（15min cron，2轮跑完 338 篇待抓取）
- 长期加 `--retry-failed` 模式：连续3次失败后标记 fetch_strategy='exhausted'

### Root Cause 4: 抓取成功率低

**症状**: batch.py direct 策略在 Bloomberg/BBC/Guardian 等反爬源全败。

**根因**: 这些域名有 paywall/Cloudflare，需要 Scrapling 或 SearXNG/Tavily recovery。

**修复**:
- 确认 Scrapling 安装可用
- SearXNG/Tavily recovery 已集成到 auto-pipeline Step 3.5/3.6
- 域名画像表标记需要 Scrapling 的域名
