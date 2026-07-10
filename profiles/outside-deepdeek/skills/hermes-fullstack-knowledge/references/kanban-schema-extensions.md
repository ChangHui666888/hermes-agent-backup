# 看板 (Kanban) 系统扩展新字段指南

## 背景

Kanban 看板系统有 SQLite 作为持久层，字段定义分散在多个层级。新增一个字段（如 `tools`）需要修改 **6 个层级**才能完整贯通。

## 完整链路（6 层）

从下到上修改：

| 层 | 文件 | 修改内容 |
|---|------|---------|
| **1. 数据库 schema** | `hermes_cli/kanban_db.py` | SCHEMA_SQL 加列 + Task 数据类加字段 + `from_row` 反序列化 + `create_task` 参数 |
| **2. 旧库迁移** | `hermes_cli/kanban_db.py` | `_migrate_add_optional_columns()` 中加 `ALTER TABLE ADD COLUMN` |
| **3. 调度器** | `hermes_cli/kanban_db.py` | `_default_spawn()` 中传递给 worker 子进程 |
| **4. CLI** | `hermes_cli/kanban.py` | `build_parser` 加 argparse 参数 + handler 传参 + `_task_to_dict` 序列化 |
| **5. Agent 工具** | `tools/kanban_tools.py` | `_handle_create` 解析参数 + JSON schema 注册 + 传给 `kb.create_task` |
| **6. API** | `plugins/kanban/dashboard/plugin_api.py` | `CreateTaskBody` Pydantic 模型加字段 + handler 传参 |
| **7. 前端 UI** | `plugins/kanban/dashboard/dist/index.js` | `InlineCreate` 组件加 state + 输入框 + submit 解析 + reset |

## 各层关键设计

### 1. Schema — JSON 列 vs 标量列

字段按用途决定存储格式：

```sql
-- JSON 数组（当值是列表）：
skills  TEXT,  -- JSON array of skill names
tools   TEXT,  -- JSON array of toolset names

-- 标量（当值是单值）：
model_override TEXT,
max_retries    INTEGER,
goal_mode      INTEGER NOT NULL DEFAULT 0,
```

### 2. Task 数据类 — 可选列表

```python
@dataclass
class Task:
    # NULL = 使用 profile 默认值
    # []    = 明确不附加任何额外项
    skills: Optional[list] = None
    tools:  Optional[list] = None
```

### 3. from_row 反序列化

```python
# Parse tools JSON blob if present
tools_value: Optional[list] = None
if "tools" in keys and row["tools"]:
    try:
        parsed = json.loads(row["tools"])
        if isinstance(parsed, list):
            tools_value = [str(s) for s in parsed if s]
    except Exception:
        tools_value = None
```

### 4. create_task 规范化

必须去重、去空白、过滤空值。对于 skills 还有额外的 toolset 名检测：

```python
# tools 规范化（只需去重+去空白）
tools_list: Optional[list[str]] = None
if tools is not None:
    cleaned_tools: list[str] = []
    seen_tools: set[str] = set()
    for t in tools:
        if not t: continue
        name = str(t).strip()
        if not name or name in seen_tools: continue
        seen_tools.add(name)
        cleaned_tools.append(name)
    tools_list = cleaned_tools
```

### 5. INSERT 语句 — 占位符计数

新增一个字段意味着 SQL 的 VALUES `(?, ...)` 计数 +1。**必须同时更新** column list、VALUES 占位符、和 tuple 参数三者，否则 OperationalError。

```python
INSERT INTO tasks (
    ..., skills, tools, max_retries, ...
) VALUES (..., ?, ?, ?, ?, ?)
#          ^ 原来 19 个占位符 → 现在 20 个
```

### 6. 调度器传参

```python
if task.tools:
    for tool_name in task.tools:
        if tool_name:
            cmd.extend(["-t", tool_name])
```

各参数互不影响：
- `--skills` → 技能包（skill bundle）
- `-t` → 工具集（toolset/runtime capability）
- `-m` → 模型覆盖

### 7. 旧库迁移

```python
def _migrate_add_optional_columns(conn):
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "tools" not in cols:
        _add_column_if_missing(conn, "tasks", "tools", "tools TEXT")
```

`_add_column_if_missing` 自动处理 "duplicate column name"（幂等安全）。

## 事件 payload

每次创建事件应在 payload 中记录新字段：

```python
_append_event(conn, task_id, "created", {
    "assignee": assignee,
    "skills": list(skills_list) if skills_list else None,
    "tools": list(tools_list) if tools_list else None,  # 新增
    ...
})
```

## 前端 InlineCreate 模式

```javascript
// 1. 加 state
const [tools, setTools] = useState("");

// 2. submit 中解析逗号分隔
const toolList = tools.split(",")
  .map(s => s.trim())
  .filter(s => s.length > 0);
if (toolList.length > 0) body.tools = toolList;

// 3. 渲染输入框
h(Input, {
  value: tools,
  onChange: e => setTools(e.target.value),
  placeholder: "toolsets (optional, comma-separated): terminal, file, web, browser",
  title: "Extra toolsets for this task (appended to the assignee profile's default toolsets).",
  className: "h-7 text-xs",
});

// 4. reset
setTools("");
```

## 文件定位速查

```
hermes_cli/kanban_db.py
  ├── SCHEMA_SQL (~973)
  ├── class Task (~732)
  ├── Task.from_row (~810)
  ├── _migrate_add_optional_columns (~1594)
  ├── create_task (~2052)
  └── _default_spawn (~6678)

hermes_cli/kanban.py
  ├── _task_to_dict (~60)
  ├── build_parser::p_create (~329)
  └── handle_create (~1340)

tools/kanban_tools.py
  ├── _handle_create (~723)
  └── KANBAN_CREATE_SCHEMA (~1167)

plugins/kanban/dashboard/plugin_api.py
  ├── class CreateTaskBody (~580)
  └── create_task handler (~597)

plugins/kanban/dashboard/dist/index.js
  └── function InlineCreate (~1088 in dist)
```
