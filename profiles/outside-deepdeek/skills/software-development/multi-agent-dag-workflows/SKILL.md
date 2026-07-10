---
name: multi-agent-dag-workflows
description: "Build, orchestrate, and operate multi-agent DAG workflow systems using Hermes Agent's delegate_task, skills, cron, and subprocess spawning. Covers content factories, CI/CD pipelines, data processing chains, and any multi-step AI agent pipeline."
version: 1.1.0
author: Content Factory
tags: [multi-agent, dag, workflow, pipeline, orchestration, content-factory]
---

# Multi-Agent DAG Workflows

Build and orchestrate multi-step DAG workflows where each node is an AI agent or automated step. Hermes Agent's `delegate_task`, skills, cron scheduling, and background processes provide the runtime; this skill covers the architectural patterns.

## Architecture

A DAG workflow system has three layers:

```
┌──────────────────────────────────────┐
│  CLI / Web UI / API Layer            │  ← user interaction
├──────────────────────────────────────┤
│  DAG Orchestration Engine            │  ← topological sort, state machine
│  ┌─ Node01 ─ Node02 ─ Node03 ┐      │
│  │      └──⇄──┘      ↓      │      │
│  │          ...              │      │
│  └──────────────────────────┘      │
├──────────────────────────────────────┤
│  Agent Layer (Hermes delegate_task)  │  ← LLM calls for AI nodes
│  Skills / LLM / Human-in-the-loop    │
└──────────────────────────────────────┘
```

## Project Structure Template

```
~/project/
├── engine/                # Python DAG engine
│   ├── dag.py             # Topological sort + node scheduler
│   ├── models.py          # Pydantic models (node I/O schemas)
│   ├── store.py           # SQLite / file persistence
│   ├── llm.py             # LLM integration layer
│   ├── cli.py             # CLI entry point
│   ├── agents/            # Hermes agent integration
│   └── nodes/             # One module per DAG node
├── webui.py               # FastAPI web dashboard
├── hermes_skills/         # Hermes Skills for delegate_task
└── scripts/
```

## DAG Engine Patterns

### Node Definition

Each node is a standalone module exporting `run(pipeline) -> pipeline`:

```python
"""Node NN: Node Name"""
from content_engine.models import ContentPipeline
from content_engine import store

def run(pipeline: ContentPipeline) -> ContentPipeline:
    # ... process pipeline ...
    store.save_pipeline(pipeline)
    return pipeline
```

### Dependency Map

Define edges as `node_id → [prerequisite_node_ids]`:

```python
DAG_EDGES = {
    1: [],            # Start node
    2: [1],           # Depends on node 1
    3: [2],           # Depends on node 2
    4: [3],           # Depends on node 3
}
```

### Topological Sort

```python
def topological_sort(edges: dict[int, list[int]]) -> list[int]:
    in_degree = {n: len(prereqs) for n, prereqs in edges.items()}
    queue = [n for n, d in in_degree.items() if d == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for n, prereqs in edges.items():
            if node in prereqs:
                in_degree[n] -= 1
                if in_degree[n] == 0:
                    queue.append(n)
    return result
```

### Quick Path (Branch)

For high-priority items, define a parallel edge set that skips nodes:

```python
QUICK_EDGES = {1: [], 2: [1], 5: [2], 8: [5]}  # skips 3,4,6,7
```

## LLM Integration

### API Key Retrieval Pattern

Hermes API keys are stored in the profile's `.env` file. Read them directly in Python:

```python
import pathlib, re

def _read_api_key(profile_name: str, key_name: str) -> str:
    """Read API key from Hermes profile .env"""
    candidates = [
        pathlib.Path.home() / "AppData" / "Local" / "hermes" / "profiles" / profile_name / ".env",
        pathlib.Path.home() / ".hermes" / ".env",
    ]
    for env_file in candidates:
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            match = re.search(rf'^\s*{key_name}\s*=\s*(.+?)\s*$', content, re.MULTILINE)
            if match:
                key = match.group(1).strip().strip("'\""")
                if key and not key.startswith("#"):
                    return key
    return ""
```

### Direct API Call Pattern (Fastest)

Prefer direct HTTP API calls over `hermes chat -q` (13x faster, ~1.5s vs ~20s):

```python
import json, urllib.request

def llm_chat(prompt: str, api_key: str, model: str = "deepseek-chat") -> str:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]
```

### Hermes CLI Fallback

When direct API access isn't available, fall back to `hermes chat -q`:

```python
import subprocess
result = subprocess.run(
    ["hermes", "chat", "-q", prompt, "--yolo", "-Q"],
    capture_output=True, text=True, timeout=120,
)
output = result.stdout.strip()
```

## Web Dashboard Integration

### FastAPI Skeleton

Serve a web dashboard alongside the CLI:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="Workflow Engine")

@app.get("/api/health")
def health(): return {"status": "ok"}

@app.get("/api/stats")
def stats(): return {"total": 42}

@app.get("/", response_class=HTMLResponse)
def index(): return HTMLResponse(INDEX_HTML)
```

Run on a separate port (e.g., 8650):

```bash
python -m uvicorn webui:app --host 0.0.0.0 --port 8650
```

## Compliance & Safety Patterns

### Three-Stage Compliance Filter
1. **Input stage**: Check keywords against blocklists, mark risky items
2. **Processing stage**: Cross-validate sources against each other
3. **Output stage**: Final gate before publishing — human approval required for risky items

### Human-in-the-Loop (HITL) Pattern
- AI recommends → Human confirms priority
- AI generates variants → Human selects or merges
- AI checks facts → Human signs off
- AI finds patterns → Human validates before deploying

## Pitfalls

### Windows Path Resolution (write_file trap)
On Windows, `/c/Users/...` passed to `write_file` resolves to `C:\c\Users\...` (wrong!). Use `C:/Users/...` (absolute Windows path with forward slashes) instead of MSYS-style `/c/Users/...`. MSYS expansion works for `terminal()` but NOT for `write_file()` on Windows.

### Hermes `chat -q` Overhead
`hermes chat -q` loads the full agent session (~20s cold start). Avoid it for batch LLM calls — read the API key from the profile .env and call the API directly instead.

### Missing Data in Branch Paths
When branches skip nodes, downstream nodes may find expected data missing. Always add fallback logic in node handlers:
```python
if pipeline.required_data is None:
    pipeline.required_data = default_value  # or generate fallback
```

### SQLite on Windows
On Windows, use `os.path.join` or pathlib for DB paths. `~/.hermes/` expands to `/c/Users/<user>/.hermes/` in bash but `C:\Users\<user>\.hermes\` in Python. Use `pathlib.Path.home()` for cross-consistency.

## Reference Files
- `references/hermes-studio-api.md` — Hermes Studio API endpoint discovery
- `references/deepseek-integration.md` — DeepSeek API key retrieval and integration patterns
