---
name: hermes-cron-engineering
description: Hermes Cron job engineering patterns — correct schedule syntax, shell+Python wrapper templates, fail-fast + dedup patterns, Windows Task Scheduler split, and backup strategy.
tags: [hermes, cron, scheduling, backup, devops, pipeline]
category: devops
---

# Hermes Cron 工程规范

## 一、关键陷阱

### `once` vs `every`

```bash
# ❌ 错误 — 只执行一次
hermes cron create "30m" ...
# → Schedule: once in 30m, Repeat: 0/1

# ✅ 正确 — 循环执行
hermes cron add "every 30m" ...
# → Schedule: every 30m, Repeat: ∞
```

`--repeat 99999` 在 `every` 模式下无效。

### `--no-agent` 必须加

非 LLM 任务（RSS扫描、Pipeline、备份）必须 `--no-agent`：

```bash
hermes cron add "every 5m" --name rss-scan --script rss-scanner.py --workdir "<scripts>" --no-agent
hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "<scripts>" --no-agent
```

不加 `--no-agent` 会导致每次 cron 运行都调用 LLM，产生不必要的费用。

## 二、Wrapper 脚本模板

### Shell (`xxx.sh`) — rss-scan 风格

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/bin:$PATH"
python "$SCRIPT_DIR/xxx.py" "$@" 2>&1
```

原则：Shell 只负责定位脚本 + 启动 Python，不做任何业务逻辑、不 `cd`、不硬编码路径。

### Python (`xxx.py`) — 薄 wrapper

```python
import argparse, logging, os, sys

os.environ["PYTHONUNBUFFERED"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/xxx.log"),
        logging.StreamHandler(sys.stdout),
    ]
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=1)
    args = parser.parse_args()
    report = run_pipeline(hours=args.hours)
    print_summary(report)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

原则：argparse + logging + report，不硬编码业务参数、不做 `sys.path` 黑魔法。

## 三、Fail-Fast 模式

### Qwen 本地模型降级

```python
_qwen_available = True  # 全局标记

def _call_qwen(...):
    global _qwen_available
    if not _qwen_available:
        return None
    try:
        # ... 调用 ...
    except Exception:
        _qwen_available = False  # 第一次失败后跳过所有后续调用
        return None
```

### 云端推送降级

```python
push_ok = 0; push_fail = 0
for article in push_rows:
    if push_fail >= 3:    # 连续3次失败 → 跳过剩余
        break
    if push_article(article):
        push_ok += 1
    else:
        push_fail += 1
```

## 四、去重模式

### 评分去重（跳过已评分）

```python
existing_urls = set(r[0] for r in dst.execute(
    "SELECT article_url FROM rss_raw").fetchall())
rows = [r for r in rows if r["link"] not in existing_urls]
duplicate = raw_count - len(rows)
```

### 增强去重（跳过已增强）

```sql
SELECT ni.id, ni.tier, rr.title
FROM news_intelligence ni
JOIN rss_raw rr ON ni.raw_id = rr.id
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A', 'B') AND nc.id IS NULL  -- 跳过已增强
```

## 五、调度器分工

| 任务类型 | 调度器 | 原因 |
|------|------|------|
| 循环任务（每5/30分钟） | Hermes Cron | 原生支持，简单 |
| 固定时间（每天12:00） | Windows Task Scheduler | 精确到秒，开机恢复 |

```powershell
# Windows Task Scheduler 创建
schtasks /create /tn "Hermes-Git-Backup" /tr "<script-path>" /sc daily /st 12:00 /f
```

## 六、Cron 任务清单

| 名称 | 频率 | 调度器 | 脚本 |
|------|:--:|------|------|
| rss-scan | 5min | Hermes Cron | rss-scanner.py |
| news-pipeline | 30min | Hermes Cron | news-pipeline.py |
| db-cloud-sync | 30min | Hermes Cron | cron-sync.py |
| git-backup | 每日12:00 | Task Scheduler | git-backup.sh |
| full-backup | 每日18:00 | Task Scheduler | full-backup.sh |

DB-to-Cloud sync: aggregates events + SCP uploads SQLite + restarts cloud backend. See `references/db-cloud-sync-pattern.md`.

## 七、Report JSON 规范

每个 pipeline 运行输出 `~/.hermes/xxx-report.json`，结构需区分批次与累计：

```json
{
  "timestamp": "2026-07-10T20:10:55",
  "batch_input": 22, "batch_new": 22, "batch_duplicate": 0,
  "batch_tier_a": 0, "batch_tier_b": 11, "batch_tier_c": 106,
  "batch_enhanced": 2, "batch_pushed": 11, "batch_push_failed": 0,
  "total_a": 5, "total_b": 122, "total_c": 1256,
  "total_articles": 130,
  "duration_sec": 29.2, "duration_pipeline_sec": 27.5, "duration_push_sec": 1.7
}
```

## 八、常见 Bug

### db.close() 顺序

累计统计查询必须在 `db.close()` **之前**执行：

```python
# ✅ 正确
cum = db.execute("SELECT ...").fetchall()
db.close()

# ❌ 错误
db.close()
cum = db.execute("SELECT ...")  # sqlite3.ProgrammingError
```

### stdout 缓冲

Cron 环境默认缓冲 stdout。修复：

```python
os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout.reconfigure(line_buffering=True)
```

### 模块路径

Wrapper 脚本必须与 `news_intel/` 在同一目录，或通过 `sys.path.insert` 指向正确位置。不要把 wrapper 放在与业务模块不同目录导致 import 失败。
