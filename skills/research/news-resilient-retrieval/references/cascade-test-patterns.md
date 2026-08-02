# Cascade Engine — 结构化测试模式

> 用于验证 cascade 抓取引擎的修改是否生效，以及边界情况是否覆盖。
> 每次修改后至少跑完批量测试 5 批次 + 编排测试 5 场景，才算验证完成。

## 一、batch.py 5 批次测试

### 准备

```bash
cd "<scripts_dir>"  # auto-pipeline.py 所在目录
```

### 批次 1：回归
**目的：** 纯URL列表（无tab），无 `--force-strategy`，验证主路径没被改动破坏。

```bash
cat > _t1.txt << 'EOF'
https://www.bbc.com/news
https://arstechnica.com
https://www.theguardian.com/world
EOF
python batch.py --urls _t1.txt --out _t1.jsonl --max-workers 1 --verbose
```

**验收：** 3/3 成功，`strategy_used` 应为 `direct`。

### 批次 2：多候选 + searxng_alt 级联
**目的：** `url\t标题` 格式，验证 `searxng_alt` 失败时是否正确继续试 `tavily`。

```bash
cat > _t2.txt << 'EOF'
https://www.reuters.com/world/middle-east/	Gaza ceasefire Middle East latest
https://www.bloomberg.com/news/articles/2026-07-13/gold-holds-decline	Gold holds decline
https://www.marketwatch.com/story/test-article	MarketWatch test
EOF
python batch.py --urls _t2.txt --out _t2.jsonl \
  --force-strategy searxng_alt,tavily --max-workers 1 --verbose
```

**验收：** cascade 链完整，`cost_trace` 中能看到 `searxng_alt` → (success/fail) → `tavily`。

### 批次 3：Tavily-only
**目的：** 验证 `strategy_used` 字段正确落到 JSONL 里为 `"tavily"`。

```bash
cat > _t3.txt << 'EOF'
https://www.reuters.com/world/middle-east/	Gaza ceasefire
https://www.marketwatch.com/story/test-article	MarketWatch stock market
EOF
python batch.py --urls _t3.txt --out _t3.jsonl \
  --force-strategy tavily --max-workers 1 --verbose
```

**验收：** JSONL 中 `strategy_used` 为 `tavily`，`cost_trace` 包含 tavily 调用。

### 批次 4：混合格式
**目的：** 一份文件里既有 `url\t标题` 也有纯 `url` 行，验证 `_parse_url_line` 不炸。

```bash
cat > _t4.txt << 'EOF'
https://www.bbc.com/news
https://www.reuters.com/world/middle-east/	Gaza ceasefire
https://www.theguardian.com/world
EOF
python batch.py --urls _t4.txt --out _t4.jsonl --max-workers 1
```

**验收：** 正常完成，无解析错误。

### 批次 5：全员失败边界
**目的：** 故意用不存在的域名/404 URL，验证 JSONL 字段完整性。

```bash
cat > _t5.txt << 'EOF'
https://www.this-domain-definitely-does-not-exist-12345.com/article
https://www.reuters.com/nonexistent-page-987654321
EOF
python batch.py --urls _t5.txt --out _t5.jsonl \
  --force-strategy searxng_alt,tavily --verbose
```

**验收：** 每个 result 字段完整（`ok`、`url`、`error`、`cost_trace` 齐全）。

### 统一检查命令

```python
import json
for line in open('_tN.jsonl'):
    r = json.loads(line)
    print(r['ok'], r.get('strategy_used'), r['url'][:60])
```

## 二、auto-pipeline.py 5 场景测试

### 场景 A：Step3 异常 → Step3.5 独立性
**怎么测：** 临时移走 `batch.py`，跑一轮 pipeline。

```bash
mv batch.py batch.py.BAK
python auto-pipeline.py  # 预期 Step3 FAILED
mv batch.py.BAK batch.py
```

**验收：** 日志应看到 `Step 3/6: FAILED` 之后紧接 `Step 3.5: Recovery` 正常执行。

### 场景 B：intel_id 不漏写
**怎么测：** 跑一轮后查 DB。

```sql
SELECT COUNT(*) AS null_intel_id
FROM news_content
WHERE intel_id IS NULL
  AND fetch_at > datetime('now','-2 hours','localtime');
-- 必须 = 0
```

### 场景 C：strategy_used 落库准确
**怎么测：** 跑一轮后查 DB。

```sql
SELECT fetch_strategy, COUNT(*) AS cnt
FROM news_content
WHERE fetch_at > datetime('now','-2 hours','localtime')
GROUP BY fetch_strategy
ORDER BY cnt DESC;
```

### 场景 D：进程锁
**怎么测：** 模拟已有实例在跑。

```bash
# 创建锁文件（2 秒前）
python -c "
import os, time
fd = os.open('.pipeline.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
os.write(fd, b'test'); os.close(fd)
os.utime('.pipeline.lock', (time.time()-2, time.time()-2))
"
python auto-pipeline.py
# 应打印: [SKIP] 已有 pipeline 在跑
```

### 场景 E：TOKEN 缺失回归
**怎么测：** 临时 unset `NEWS_API_TOKEN`。

```bash
NEWS_API_TOKEN="" python auto-pipeline.py
```

**验收：** Step5/6 应 `skipped: NEWS_API_TOKEN not set`，不报错、不崩。

## 三、数据库质量检查

```sql
-- 按策略统计有效/无效
SELECT nc.fetch_strategy,
       COUNT(*) as total,
       SUM(CASE WHEN length(nc.content_md) >= 2000 THEN 1 ELSE 0 END) as good,
       SUM(CASE WHEN length(nc.content_md) >= 500 AND length(nc.content_md) < 2000 THEN 1 ELSE 0 END) as fair,
       SUM(CASE WHEN length(nc.content_md) >= 100 AND length(nc.content_md) < 500 THEN 1 ELSE 0 END) as thin,
       SUM(CASE WHEN nc.content_md IS NULL OR length(nc.content_md) < 100 THEN 1 ELSE 0 END) as empty
FROM news_content nc
WHERE nc.fetch_strategy IS NOT NULL AND nc.fetch_strategy != ''
GROUP BY nc.fetch_strategy
ORDER BY total DESC;

-- 按域名看有效率和平均字长
SELECT SUBSTR(rr.source_domain, 1, 25) as domain,
       COUNT(*) as total,
       SUM(CASE WHEN length(nc.content_md) >= 100 THEN 1 ELSE 0 END) as useful,
       ROUND(AVG(length(nc.content_md))) as avg_len
FROM news_content nc
JOIN news_intelligence ni ON nc.intel_id = ni.id
JOIN rss_raw rr ON ni.raw_id = rr.id
GROUP BY rr.source_domain
ORDER BY useful DESC;
```

## 四、调优测试（批次大小验证）

```bash
# 1. 从DB取 N 个待抓取 URL（N=10 或 15）
# 2. 跑 batch.py
# 3. 如果稳定 < 120s，可考虑加 LIMIT

python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
urls = conn.execute('''SELECT DISTINCT rr.article_url FROM news_intelligence ni
    JOIN rss_raw rr ON ni.raw_id=rr.id
    LEFT JOIN news_content nc ON nc.intel_id=ni.id
    WHERE ni.tier IN (\"A\",\"B\") AND (nc.id IS NULL OR nc.content_md='')
    ORDER BY ni.score_total DESC LIMIT 10''').fetchall()
conn.close()
with open('_batch_N.txt','w') as f:
    for u in urls: f.write(u[0]+'\n')
"
python batch.py --urls _batch_N.txt --out _batch_N.jsonl \
  --rate-delay 0.3 --max-workers 1
```
