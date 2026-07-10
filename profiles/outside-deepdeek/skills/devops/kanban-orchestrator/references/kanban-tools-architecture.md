# Kanban Tools Architecture — Per-Task Tools Gap

> Full layer trace of the `skills` vs `tools` distinction, and what would need to change to add per-task toolset overrides. Discovered while investigating "新建任务无法选取工具" (cannot select tools when creating a kanban task).

## Current State

The kanban system supports per-task **skills** (skill bundles force-loaded into the worker via `--skills`) but has **no per-task tools** (runtime toolset capabilities). A worker's tools always come from the assignee profile's `toolsets:` config.yaml entry.

## Layer-by-Layer Trace

### 1. Database Schema
**File:** `hermes_cli/kanban_db.py:973`
- `tasks` table has a `skills TEXT` column (JSON array of skill names, line 1014)
- **No `tools` column**
- `model_override` column exists (line 1018) — precedent for per-task overrides

### 2. DB Layer — `create_task()`
**File:** `hermes_cli/kanban_db.py:2052`
```python
def create_task(
    conn,
    *,
    title, body, assignee, created_by,
    workspace_kind, workspace_path, branch_name,
    tenant, priority, parents,
    triage, idempotency_key, max_runtime_seconds,
    skills=None,        # <-- skills present
    max_retries=None,
    goal_mode, goal_max_turns,
    initial_status, session_id,
    board=None,
) -> str:
```
- Accepts `skills` parameter — **no `tools` parameter**
- Validates skills at line 2132: rejects toolset names (web/browser/terminal) with an explicit error: "X is a toolset name, not a skill name. Put toolsets in the assignee profile's `toolsets:` config instead of per-task skills."

### 3. CLI — `kanban create`
**File:** `hermes_cli/kanban.py:306`
```python
p_create.add_argument("--skill", action="append", default=[], dest="skills", ...)
```
- Has `--skill` (repeatable) — **no `--tools` flag**

### 4. Tool Layer — `_handle_create()`
**File:** `tools/kanban_tools.py:723`
```python
skills = args.get("skills")
...
kb.create_task(..., skills=skills, ...)
```
- Reads `skills` from args and passes to `create_task` — **no `tools` parameter**

### 5. Tool Registration — `kanban_create` schema
**File:** `tools/kanban_tools.py:1159`
- The tool schema's `parameters.properties` has `skills` — **no `tools` property**

### 6. Web UI Backend — `CreateTaskBody`
**File:** `plugins/kanban/dashboard/plugin_api.py:580`
```python
class CreateTaskBody(BaseModel):
    title: str
    body: Optional[str] = None
    assignee: Optional[str] = None
    ...
    skills: Optional[list[str]] = None
    goal_mode: bool = False
    goal_max_turns: Optional[int] = None
```
- Has `skills` field — **no `tools` field**
- POST `/tasks` (line 597) passes `skills=payload.skills` to `create_task`

### 7. Web UI Frontend
**File:** `plugins/kanban/dashboard/dist/index.js`
- The dashboard's task detail drawer shows "Skills" as a field
- No "Tools" or "Toolsets" field in the UI
- The "Create task" dialog has fields: title, body, assignee, tenant, priority, workspace, skills
- No tools selector

### 8. Dispatcher — `_default_spawn()`
**File:** `hermes_cli/kanban_db.py:6678`
```python
cmd = [
    *_resolve_hermes_argv(),
    "-p", profile_arg,
    "--accept-hooks",
]
if _kanban_worker_skill_available(...):
    cmd.extend(["--skills", "kanban-worker"])
# Per-task skills appended AFTER kanban-worker
if task.skills:
    for s in task.skills:
        cmd.extend(["--skills", s])
```
- Injects skills via `--skills` flags — **no `--toolsets` or `HERMES_TOOLSETS` injection**
- Worker inherits the profile's `toolsets:` config from its config.yaml

## What Would Need to Change

To add per-task tool overrides, every layer above would need a parallel `tools`/`toolsets` path:

| Layer | Change |
|-------|--------|
| DB Schema | Add `tools TEXT` column to `tasks` table |
| `create_task()` | Add `tools: Optional[Iterable[str]] = None` param, store as JSON |
| `kanban create` CLI | Add `--tools` (repeatable) argument |
| `_handle_create()` | Read `tools` from args, pass to `create_task()` |
| Tool schema | Add `tools` property to `kanban_create` parameters |
| `CreateTaskBody` | Add `tools: Optional[list[str]] = None` field |
| Frontend JS | Add tools selector to create-task dialog + task detail drawer |
| `_default_spawn()` | Inject `--toolsets <comma-separated>` or `HERMES_TOOLSETS` env var |

## Design Decision

The current design intentionally separates skills (knowledge bundles loaded into the agent's context) from toolsets (runtime capabilities configured per-profile). The dispatcher's comment in `kanban_db.py:2132` explains the rationale: toolsets belong in the profile config because they gate what API calls the model can make, and that's a profile-level security/privacy boundary.

A per-task tools override would weaken this boundary — a creator could grant the worker tools its profile doesn't normally have. If adding this, consider a union strategy (per-task tools are a subset of the profile's tools, or require explicit user approval) or an additive-only model (per-task tools can only ADD to what the profile already has, not remove).
