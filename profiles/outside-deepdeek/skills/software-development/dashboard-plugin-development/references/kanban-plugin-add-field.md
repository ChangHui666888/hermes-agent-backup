# Kanban Plugin: Adding a New Per-Task Field

This reference documents the full cross-layer pattern for adding a new field (like `tools`) to the kanban task system — from database schema through frontend form.

## Layer Map

```
DB Schema → Task Dataclass → create_task() → _default_spawn → CLI → Tool → API → Frontend InlineCreate → Frontend Detail Drawer
```

## Step 1: Database Schema

**File**: `hermes_cli/kanban_db.py`

### 1a. Add column to `SCHEMA_SQL`

Find the `CREATE TABLE IF NOT EXISTS tasks ( ... )` statement. Add the new column near related columns, with doc comment:

```sql
-- Per-task toolset override, stored as JSON. Appended to the
-- profile's default toolsets via `-t`. NULL = use profile defaults.
tools                TEXT,
```

### 1b. Add migration in `_migrate_add_optional_columns()`

Find the function, add after the `skills` migration:

```python
if "tools" not in cols:
    conn.execute("ALTER TABLE tasks ADD COLUMN tools TEXT")
```

## Step 2: Task Dataclass

**File**: `hermes_cli/kanban_db.py`, find `class Task`

Add field with docstring:

```python
# Per-task toolset override (appended to the profile's default
# toolsets via `-t`). Stored as a JSON array of toolset names.
# None = use only the profile defaults; empty list = no extra
# toolsets beyond what the profile configures.
tools: Optional[list] = None
```

## Step 3: from_row Deserialization

In `Task.from_row()`, add JSON parsing (after skills parsing):

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

And pass it to the dataclass:

```python
return cls(
    ...
    skills=skills_value,
    tools=tools_value,
    model_override=...,
```

## Step 4: create_task() Function

**File**: `hermes_cli/kanban_db.py`

### 4a. Add parameter

```python
def create_task(
    conn,
    *,
    title,
    ...
    skills: Optional[Iterable[str]] = None,
    tools: Optional[Iterable[str]] = None,   # <-- new
    max_retries: Optional[int] = None,
```

### 4b. Add normalization logic

After skills normalization:

```python
# Normalise + validate tools: strip whitespace, drop empties, dedupe.
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

### 4c. Add to INSERT

Add `tools` to the column list and VALUES in the INSERT statement. The number of placeholders must match:

```python
INSERT INTO tasks (
    ..., skills, tools, max_retries, ...
) VALUES (..., ?, ?, ?, ...)

# Values tuple:
json.dumps(skills_list) if skills_list is not None else None,
json.dumps(tools_list) if tools_list is not None else None,
```

### 4d. Add to event payload

In `_append_event(conn, task_id, "created", {...})`:

```python
"skills": list(skills_list) if skills_list else None,
"tools": list(tools_list) if tools_list else None,
```

## Step 5: Dispatcher (_default_spawn)

**File**: `hermes_cli/kanban_db.py`, find `def _default_spawn`

After per-task skills block, add toolset passing:

```python
# Per-task toolset override. Each name goes in its own `-t X` pair.
if task.tools:
    for tool_name in task.tools:
        if tool_name:
            cmd.extend(["-t", tool_name])
```

## Step 6: CLI (`hermes kanban create`)

**File**: `hermes_cli/kanban.py`

### 6a. Add argparse argument

After `--skill` argument:

```python
p_create.add_argument("--tool", action="append", default=[], dest="tools",
    help="Toolset to enable for the worker "
         "(repeatable). Appended to the assignee "
         "profile's default toolsets. Example: "
         "--tool web --tool browser --tool terminal")
```

### 6b. Pass to create_task

In the handler:

```python
skills=getattr(args, "skills", None) or None,
tools=getattr(args, "tools", None) or None,
```

### 6c. Add to _task_to_dict

```python
"tools": list(t.tools) if t.tools else [],
```

## Step 7: Tool (_handle_create in kanban_tools.py)

**File**: `tools/kanban_tools.py`

### 7a. Parse tools arg

After goal parsing, before parents parsing:

```python
# Parse tools list
tools = args.get("tools")
if isinstance(tools, str):
    tools = [tools]
if tools is not None and not isinstance(tools, (list, tuple)):
    return tool_error(
        f"tools must be a list of toolset names, got {type(tools).__name__}"
    )
```

### 7b. Pass to kb.create_task

Add `tools=tools,` to the `kb.create_task(...)` call.

### 7c. Add to JSON schema

In `KANBAN_CREATE_SCHEMA["parameters"]["properties"]`, after `"skills"`:

```python
"tools": {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Toolset names to enable for the dispatched worker "
        "(in addition to the assignee profile's default toolsets). "
        "Use this to grant specific runtime capabilities \u2014 "
        "e.g. ['terminal', 'file'] for a coding task."
    ),
},
```

## Step 8: Plugin API (CreateTaskBody)

**File**: `plugins/kanban/dashboard/plugin_api.py`

### 8a. Add to Pydantic model

```python
class CreateTaskBody(BaseModel):
    ...
    skills: Optional[list[str]] = None
    tools: Optional[list[str]] = None    # <-- new
    goal_mode: bool = False
```

### 8b. Pass to create_task

```python
skills=payload.skills,
tools=payload.tools,
```

## Step 9: Frontend InlineCreate

**File**: `plugins/kanban/dashboard/dist/index.js`

### 9a. Add state

```javascript
const [tools, setTools] = useState("");
```

### 9b. Add to body construction in submit()

```javascript
// Parse comma-separated tools into a clean list.
const toolList = tools
    .split(",")
    .map(function (s) { return s.trim(); })
    .filter(function (s) { return s.length > 0; });
if (toolList.length > 0) body.tools = toolList;
```

### 9c. Add to reset

```javascript
setGoalMode(false); setGoalMaxTurns(""); setTools("");
```

### 9d. Add Input element

After the skills Input:

```javascript
h(Input, {
    value: tools,
    onChange: function (e) { setTools(e.target.value); },
    placeholder: "toolsets (optional, comma-separated): terminal, file, web, browser",
    title: "Extra toolsets for this task (appended to the assignee profile's default toolsets).",
    className: "h-7 text-xs",
}),
```

### 9e. (Optional) Add dropdown quick-picker

Load available options via `useEffect` and render a `Select` dropdown:

```javascript
const [availableToolsets, setAvailableToolsets] = useState([]);

useEffect(function () {
    SDK.fetchJSON(API + "/toolsets")
        .then(function (d) { setAvailableToolsets(d.toolsets || []); })
        .catch(function () {});
}, []);

// In JSX, after the tools Input:
availableToolsets.length > 0 ? h("div", { className: "flex gap-1 mb-1" },
    h(Select, {
        value: "",
        className: "h-7 text-xs flex-1",
        onValueChange: function (v) {
            if (v) {
                const curr = tools ? tools.split(",").map(s => s.trim()).filter(Boolean) : [];
                if (!curr.includes(v)) { curr.push(v); setTools(curr.join(", ")); }
            }
        },
    },
        h(SelectOption, { value: "" }, "+ add toolset\u2026"),
        availableToolsets.map(function (t) {
            return h(SelectOption, { key: t, value: t }, t);
        }),
    ),
) : null,
```

## Step 10: Frontend Detail Drawer

**File**: `plugins/kanban/dashboard/dist/index.js`

In the task detail JSX, after the skills MetaRow:

```javascript
(t.tools && t.tools.length > 0) ? h(MetaRow, {
    label: tx(i18n, "tools", "Tools"),
    value: t.tools.join(", "),
}) : null,
```

## Backend API for Dropdown Options

Add a `GET /toolsets` endpoint to `plugin_api.py`:

```python
@router.get("/toolsets")
def list_toolsets():
    try:
        from toolsets import get_toolset_names
        names = sorted(get_toolset_names())
        return {"toolsets": names}
    except Exception as e:
        log.warning("list_toolsets failed: %s", e)
        return {"toolsets": []}
```

This returns 58+ toolset names (web, browser, terminal, file, vision, etc.).
