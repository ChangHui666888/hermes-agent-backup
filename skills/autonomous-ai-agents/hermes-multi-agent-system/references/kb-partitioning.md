# Knowledge-base partitioning (Obsidian / shared vault)

A shared KB serving multiple agent roles must be physically partitioned with
permission-by-profile, or content-farm noise pollutes authoritative knowledge.

## Layout
```
<vault>/
  raw/                 # append-only. NO agent may edit/delete. Original inputs.
    web_snapshots/  financial_reports/  code_repos/  media_sources/
  wiki/                # ONLY authoritative agents (dev/research/investment) write.
    entities/  concepts/  skills_index/  <domain-a>/  <domain-b>/
  media_analytics/     # ONLY content agents write; others read-only (e.g. sentiment weight).
    traffic_daily/  sentiment/  hot_topics/     # volatile: decay/expire past a time threshold
  archive/             # ONLY an archive script writes. Cold nodes leave the RAG index.
  _index/              # auto-generated index for RAG/LLM-wiki. Do NOT hand-edit.
  _governance/         # constitution mirror + permission matrix
```

## Permission matrix (put in _governance/KB_README.md)
| Partition | Write | Read | Forbidden |
|---|---|---|---|
| raw/ | all agents, append-only | all | modify/delete existing |
| wiki/ | authoritative agents only | all | content-farm agents writing |
| media_analytics/ | content agents only | others read-only | polluting wiki |
| archive/ | archive script only | on demand | — |

## Enforcement
Permissions are enforced by each **profile's file-path whitelist**, not by the
filesystem. State the rule in each partition's README AND in the role's
`AGENTS.md`. The load-bearing rule: content-farm "clickbait" must NEVER enter
`wiki/`; auto-archive cold nodes so the model's context window isn't blown.

## Writing pages
- `raw/`: `YYYY-MM-DD_source_titlehash.md`, include source URL + capture timestamp.
- `wiki/`: distilled, source-cited, deterministic facts only. Index into `_index/`.
- `media_analytics/`: always timestamped; downstream consumers apply time-decay.

## Gotcha
If the vault lives under a OneDrive-managed `Documents`, see
`environment-recon.md` for the hydration workaround before creating dirs.
