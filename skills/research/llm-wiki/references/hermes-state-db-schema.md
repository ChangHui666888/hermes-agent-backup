# Hermes State DB Schema Reference

> Hermes Agent 的 state.db (SQLite) 存储会话、消息、用户状态等核心数据。
> 此文件记录 key tables 及其字段，供 wiki 管线和其他集成脚本直接查询。

## 位置

默认路径: `~/.hermes/state.db` (macOS/Linux)
Windows: `C:\Users\<user>\AppData\Local\hermes\state.db`

可通过 `HERMES_STATE_DB` 环境变量覆盖。

## 关键表

### sessions

Hermes 对话会话元数据。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 会话 ID (如 `mqwjknu46n6kye`) |
| `source` | TEXT | 来源平台 (cli, telegram, discord, slack 等) |
| `user_id` | TEXT | 用户标识 |
| `model` | TEXT | 使用的模型 (如 `google/gemma-4-e4b`) |
| `model_config` | TEXT | JSON 序列化的模型配置 |
| `system_prompt` | TEXT | 系统提示词 |
| `parent_session_id` | TEXT | 父会话 ID (用于分支/重新) |
| `started_at` | REAL | Unix 时间戳 (秒) — 会话开始时间 |
| `ended_at` | REAL | Unix 时间戳 (秒) — 会话结束时间，NULL=进行中 |
| `end_reason` | TEXT | 结束原因 |
| `message_count` | INTEGER | 消息总数 |
| `tool_call_count` | INTEGER | 工具调用次数 |
| `input_tokens` | INTEGER | 输入 token 数 |
| `output_tokens` | INTEGER | 输出 token 数 |
| `cache_read_tokens` | INTEGER | 缓存读取 token 数 |
| `cache_write_tokens` | INTEGER | 缓存写入 token 数 |
| `reasoning_tokens` | INTEGER | 推理 token 数 |
| `title` | TEXT | 会话标题 (由模型自动生成) |
| `archived` | INTEGER | 0=活跃, 1=已归档 |
| `estimated_cost_usd` | REAL | 预估成本 (美元) |
| `actual_cost_usd` | REAL | 实际成本 (美元) |

**查询示例:**
```sql
-- 最近有标题的会话
SELECT id, title, message_count, started_at
FROM sessions
WHERE title IS NOT NULL AND title != ''
ORDER BY started_at DESC
LIMIT 10;

-- 按模型统计会话数
SELECT model, COUNT(*) AS cnt
FROM sessions WHERE model IS NOT NULL
GROUP BY model
ORDER BY cnt DESC;
```

### messages

每个会话中的消息记录。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增 ID |
| `session_id` | TEXT FK | 所属会话 ID |
| `role` | TEXT | 角色: user, assistant, tool |
| `content` | TEXT | 消息内容 (markdown) |
| `tool_call_id` | TEXT | 工具调用 ID |
| `tool_calls` | TEXT | JSON 格式的工具调用列表 |
| `tool_name` | TEXT | 调用的工具名 |
| `timestamp` | REAL | Unix 时间戳 (秒) |
| `token_count` | INTEGER | 这条消息的 token 数 |
| `finish_reason` | TEXT | 结束原因 |
| `reasoning` | TEXT | 推理过程 |
| `reasoning_content` | TEXT | 推理内容 |
| `active` | INTEGER | 1=活跃, 0=已清除 |

**查询示例:**
```sql
-- 某个会话的消息数
SELECT COUNT(*) FROM messages WHERE session_id = 'mqwjknu46n6kye';

-- 按角色统计 token 消耗
SELECT role, SUM(token_count) FROM messages
WHERE session_id = 'mqwjknu46n6kye'
GROUP BY role;
```

### 其他表

| 表名 | 说明 |
|---|---|
| `schema_version` | 数据库 schema 版本 |
| `state_meta` | 键值存储的状态元数据 |
| `compression_locks` | 压缩/清理锁 |
| `messages_fts*` | FTS5 全文搜索索引 (消息内容搜索) |

## 从 Python 连接

```python
import sqlite3, datetime
from pathlib import Path

db = Path("C:/Users/ChangHui/AppData/Local/hermes/state.db")
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 获取近期会话
cur.execute("""
    SELECT id, title, started_at, message_count, model
    FROM sessions
    WHERE title IS NOT NULL AND title != ''
    ORDER BY started_at DESC
    LIMIT 5
""")
for row in cur.fetchall():
    started = datetime.datetime.fromtimestamp(row["started_at"])
    print(f"[{row['id']}] {row['title']} — {started:%Y-%m-%d} ({row['message_count']} msgs)")

conn.close()
```

## 注意事项

- `started_at`/`ended_at` 是 Unix 时间戳 (秒)，需要用 `datetime.fromtimestamp()` 转换
- `title` 列可能为 NULL——只查询有标题的会话作为 wiki 源
- 数据库可能同时被 Hermes 写入，连接时不需要加锁 (SQLite 处理并发)
- 数据库文件可能较大 (常见 5-20 MB)，查询时加 LIMIT 避免大结果
- `message_count` 等统计字段是缓存值，在会话进行中可能不准确，结束后会更新
