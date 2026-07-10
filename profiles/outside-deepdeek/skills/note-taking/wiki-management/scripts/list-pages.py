#!/usr/bin/env python3
"""List wiki pages with title, type, and section — for index.md maintenance."""
import os, re
from pathlib import Path

WIKI_DIR = Path(os.environ.get("WIKI_PATH", "C:/Users/<user>/wiki"))

def parse_frontmatter(content):
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip().strip("\"'")
        if key in ("title", "type", "summary", "tags"):
            meta[key] = val
    return meta

exclude = {"SCHEMA.md", "SCHEMA-GRAPH.md", "index.md", "log.md", "data.json", "graph.json"}
exclude_prefixes = (".obsidian/", "raw/", "_archive/", "scripts/", ".git/")

pages = {}

for fpath in sorted(WIKI_DIR.rglob("*.md")):
    rel = fpath.relative_to(WIKI_DIR).as_posix()
    if fpath.name in exclude or any(rel.startswith(p) for p in exclude_prefixes):
        continue
    content = fpath.read_text(encoding="utf-8", errors="replace")
    meta = parse_frontmatter(content)
    title = meta.get("title", fpath.stem)
    section = rel.split("/")[0] if "/" in rel else "other"
    pages.setdefault(section, []).append((title, rel, meta.get("type", "")))

for section, items in sorted(pages.items()):
    print(f"\n## {section.capitalize()} ({len(items)} pages)")
    for title, path, ptype in items:
        print(f"- [{title}]({path}) [{ptype}]")
