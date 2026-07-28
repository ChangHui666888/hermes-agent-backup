# Dual-Wiki Normalization Reference

> Session-specific detail: patterns and templates for normalizing two knowledge bases
> into one SSoT-per-class architecture. Used by `multi-agent-system-architecture` skill.

## Common Multi-Wiki Failure Modes

| Failure Mode | Symptom | Detection |
|-------------|---------|-----------|
| Dual-index drift | Global index last updated 7/3 but sub-index updated 7/14 | Compare last-modified timestamps |
| SSoT ambiguity | Same Constitution in 3 places with different content | `grep -r "CONSTITUTION" ~/wiki/ ~/Documents/ ~/AppData/` |
| AGENTS.md phantom | Role definitions exist in Obsidian but not in profiles/\*/ | `ls profiles/*/AGENTS.md` returns empty |
| Dual-pipeline-doc | Pipeline described in both wikis with different detail levels | grep pipeline name across both wikis |
| Skill isolation failure | All profiles have identical skill sets | Compare `profiles/*/skills/` directories |

## SSoT Decision Template

For every knowledge class found in multiple locations:

```
Knowledge class: <name>
Existing locations:
  1. <path> (last modified: <date>, size: <bytes>)
  2. <path> (last modified: <date>, size: <bytes>)
SSoT candidate: <choose based on: human-accessibility, agent-accessibility, update frequency>
Plan:
  - Keep at SSoT
  - <other location(s)> → DELETE / AUTO-SYNC / STUB
```

## Profile Audit Command Sequence

```bash
# 1. List all profiles
hermes profile list

# 2. Check each for AGENTS.md (auto-injection)
for p in c0orchestrator devteam medteam outside-deepdeek; do
  echo "$p: AGENTS.md=$([ -f "profiles/$p/AGENTS.md" ] && echo YES || echo MISSING)"
done

# 3. Check SOUL.md differentiation
for p in c0orchestrator devteam medteam outside-deepdeek; do
  echo "=== $p ==="
  head -5 "profiles/$p/SOUL.md"
done

# 4. Check cron job distribution
for p in c0orchestrator devteam medteam outside-deepdeek; do
  jobs=$(ls "profiles/$p/cron/" 2>/dev/null | grep -v ticker | grep -v output)
  echo "$p cron: $([ -n "$jobs" ] && echo "ACTIVE: $jobs" || echo "empty (ticker only)")"
done

# 5. Check skill isolation
for p in c0orchestrator devteam medteam outside-deepdeek; do
  echo "$p: $(ls "profiles/$p/skills/" | sort | tr '\n' ' ')"
done

# 6. Check workspace role directories
ls workspace/roles/*/AGENTS.md 2>/dev/null
```

## Concrete Normalization Scripts (Python)

```python
# check_duplicate_knowledge.py
import os, hashlib

wikis = {
    "llm-wiki": "C:/Users/ChangHui/wiki",
    "obsidian": "C:/Users/ChangHui/Documents/Obsidian Vault"
}

def hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

# Find files with same name across both wikis
for name in set(os.listdir(wikis["llm-wiki"])) & set(os.listdir(wikis["obsidian"])):
    if name.endswith('.md'):
        p1 = os.path.join(wikis["llm-wiki"], name)
        p2 = os.path.join(wikis["obsidian"], name)
        if os.path.isfile(p1) and os.path.isfile(p2):
            if hash_file(p1) != hash_file(p2):
                print(f"⚠️ DIVERGENT: {name}")
```

```python
# deploy_agents.py
import os, shutil

SSOT = "C:/Users/ChangHui/Documents/Obsidian Vault/_governance/agents_md"
PROFILES = "C:/Users/ChangHui/AppData/Local/hermes/profiles"

mapping = {
    "C0-orchestrator.AGENTS.md": "c0orchestrator/AGENTS.md",
    "DEV-team.AGENTS.md": "devteam/AGENTS.md",
    "MED-team.AGENTS.md": "medteam/AGENTS.md",
}

for src_name, dest_rel in mapping.items():
    src = os.path.join(SSOT, src_name)
    dest = os.path.join(PROFILES, dest_rel)
    if os.path.exists(src):
        shutil.copy2(src, dest)
        print(f"Deployed: {src} → {dest}")
    else:
        print(f"MISSING SSoT: {src}")
```

## Session Record

This reference documents learnings from a Hermes system architecture audit
(2026-07-27) that uncovered:
- 4 profiles with identical SOUL.md (no role differentiation)
- 0 profiles with AGENTS.md at profile root (auto-injection gap)
- 3 workspace/roles/AGENTS.md files serving as phantom cwd copies
- Dual wiki with 4 content overlaps (Constitution ×3, pipeline docs ×2, AGENTS.md ×2, indexes ×2)
- All profiles share identical skill sets (no role isolation)
- Only 1 of 4 profiles has active cron jobs
- All profiles have empty channel directories (no platform integration)
