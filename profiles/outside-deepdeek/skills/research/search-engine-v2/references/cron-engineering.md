# Cron Job 工程规范

所有 Hermes Cron Job 遵循统一模板。

## Shell (`xxx.sh`)

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/bin:$PATH"
python "$SCRIPT_DIR/xxx.py" "$@"
# 读 Report JSON → 打印摘要
```

## Python (`xxx.py`)

```python
import argparse, logging, os, sys

EXIT_OK=0; EXIT_PIPELINE=1; EXIT_IMPORT=2

def print_summary(report: dict):
    report = report or {}
    # 动态循环输出，不硬编码 tier 名称

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=1)
    args = parser.parse_args()
    try:
        from xxx import run_pipeline
        report = run_pipeline(hours=args.hours) or {}
        print_summary(report)
        return EXIT_OK
    except ImportError:
        return EXIT_IMPORT
    except Exception:
        logger.exception("failed")
        return EXIT_PIPELINE
```

## 业务 (`pipeline.py`)

```python
def run_pipeline(...) -> dict:
    # 返回 report dict
    report_path = os.path.expanduser("~/.hermes/xxx-report.json")
    with open(report_path, "w") as f:
        json.dump(report, f)
    return report
```

## Report 结构

```json
{
  "batch_input": 22, "batch_new": 22, "batch_duplicate": 0,
  "batch_tier_a": 0, "batch_tier_b": 19, "batch_tier_c": 179,
  "batch_enhanced": 6, "batch_pushed": 6, "batch_push_failed": 0,
  "total_a": 5, "total_b": 122, "total_c": 1256, "total_articles": 160,
  "duration_sec": 89.5, "duration_push_sec": 2.1, "duration_pipeline_sec": 87.4
}
```

## 退出码

| 码 | 含义 |
|:--:|------|
| 0 | 成功 |
| 1 | Pipeline 执行错误 |
| 2 | 模块导入失败 |
