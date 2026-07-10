# Knowledge Graph Schema Reference

> Complete template for the 4-layer Knowledge Graph schema document (SCHEMA-GRAPH.md).
> Place this alongside SCHEMA.md in the wiki root when upgrading from File Graph to
> Knowledge Graph.

## Architecture

```
Knowledge Layer              Capability Layer        Execution Layer      Artifact Layer
Topic → Concept → Entity     Skill → Workflow        Session → Task       Content → Report
         → Pattern           → Prompt → Tool         → Run → Result       → Summary → Media
         → Evidence
```

## Node Types

### Knowledge Layer
| Type | ID Prefix | Description | Required Fields |
|------|-----------|-------------|-----------------|
| `topic` | `t_` | Broad subject area | id, title, type, created, tags |
| `concept` | `c_` | Specific idea within topic | id, title, type, created, parent_topic |
| `entity` | `e_` | Named thing | id, title, type, created, aliases[] |
| `pattern` | `p_` | Reusable template/approach | id, title, type, success_rate, applies_to[] |
| `evidence` | `ev_` | Supporting data/fact | id, title, type, source, confidence |

### Capability Layer
| Type | ID Prefix | Description | Required Fields |
|------|-----------|-------------|-----------------|
| `skill` | `s_` | Executable capability | id, title, type, version, requires[] |
| `workflow` | `w_` | Multi-step process | id, title, type, steps[] |
| `prompt` | `pr_` | Template prompt | id, title, type, version |
| `tool` | `tl_` | External tool | id, title, type, provider |

### Execution Layer
| Type | ID Prefix | Description | Required Fields |
|------|-----------|-------------|-----------------|
| `session` | `ses_` | Agent conversation | id, title, type, model, started_at |
| `task` | `tsk_` | Specific task | id, title, type, status, session_id |
| `run` | `r_` | Single execution | id, type, task_id, duration_ms |
| `result` | `res_` | Execution output | id, type, run_id, status |

### Artifact Layer
| Type | ID Prefix | Description | Required Fields |
|------|-----------|-------------|-----------------|
| `content` | `ct_` | Generated article/message | id, title, type, created, path |
| `report` | `rp_` | Structured report | id, title, type, sections[] |
| `summary` | `sm_` | Condensed version | id, title, type, source_ids[] |
| `media` | `m_` | Image/video | id, title, type, format, path |

## Edge Types

| Type | Source → Target | Meaning | Example |
|------|----------------|---------|---------|
| `is_a` | Concept → Topic | Concept belongs to topic | Planning → AI Agent |
| `contains` | Topic → Concept | Topic includes concept | AI Agent → Reflection |
| `requires` | Skill → Concept | Capability depends on knowledge | content_writer → Planning |
| `uses` | Workflow → Skill | Workflow uses capability | write_article → content_writer |
| `references` | Session → Topic | Session references topic | ses_001 → AI Agent |
| `evolved_from` | Node v2 → Node v1 | Version evolution | v2 → v1 |
| `has_pattern` | Content → Pattern | Content uses pattern | article_123 → hook_conflict_v1 |
| `implements` | Entity → Concept | System implements concept | Hermes → Reflection |
| `produces` | Run → Content | Run produces artifact | run_456 → article_789 |
| `evidence_for` | Evidence → Concept | Evidence supports concept | benchmark → Planning |
| `depends_on` | Concept → Concept | Concept dependency | Reflection → Planning |

## Evolution Rules

### Knowledge Evolution
When a new concept appears:
1. Check existing Concept nodes
2. If new, create Concept node and link to parent Topic
3. Check relationships to existing concepts → auto-add edges
4. When Topic has >10 Concepts → trigger sub-topic split

### Skill Evolution
When a Skill is used N times successfully:
1. Analyze results for emerging Pattern usage
2. If new Pattern frequency > threshold → create Pattern node
3. When Patterns accumulate → trigger version upgrade (v1 → v2)
4. Link versions via `evolved_from` edge

### Pattern Mining
- Extract patterns from Content nodes automatically
- Each Pattern node records: success_rate, applies_to[], first_seen, last_used
- Patterns should be cross-referencable (one article can use multiple patterns)

## Graph JSON Format

```json
{
  "meta": {
    "type": "knowledge-graph",
    "version": "3.0.0",
    "schema": "4-layer",
    "node_types": ["topic", "concept", "entity", "pattern", "skill", "session"],
    "edge_types": ["is_a", "contains", "requires", "references", "implements"]
  },
  "nodes": [
    {"id": "c_planning", "type": "concept", "title": "Planning",
     "description": "Task planning and decomposition", "tags": ["ai-agent"]}
  ],
  "edges": [
    {"source": "c_planning", "target": "ai-agent", "type": "is_a"}
  ]
}
```

## Migration Path

```
Phase 1           Phase 2                  Phase 3
Markdown + JSON   Markdown + JSON          Neo4j / Qdrant
File Graph        Knowledge Graph          Knowledge Graph
Manual export     Auto-evolution           Real-time query
```

Stabilize the Schema first (Phase 1→2). Storage migration (Phase 3) is cheap once
the node types, edge types, and evolution rules are defined.
