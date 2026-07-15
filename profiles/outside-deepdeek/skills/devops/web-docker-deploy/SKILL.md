---
name: web-docker-deploy
description: Deploy Next.js + FastAPI + SQLite web apps to cloud Docker. NEVER build locally.
version: 1.1.0
category: devops
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [deployment, docker, nextjs, fastapi, sqlite, cloud]
---

# Web Docker Deployment Skill

Deploy a Next.js + FastAPI + SQLite stack to a remote Docker host. All builds happen on the cloud — never locally.

## Golden Rules

1. **NEVER build locally.** No `npm run dev`, no `docker build`, no `docker compose up` on Windows.
2. **All verification via cloud curl**, never `localhost:3000`.
3. **SQLite needs `immutable=1`** for Docker read-only volume mounts.
4. **`NEXT_PUBLIC_API_URL` must be inlined at build time** — set in BOTH Dockerfile ENV AND next.config.ts `env` block.
5. **After every frontend rebuild, restart nginx**: `docker compose restart nginx`.
6. **Never use `--no-cache`** on small VMs (3.9GB RAM). Incremental build works.

## Project Structure

```
project/
├── docker-compose.yml
├── nginx.conf
├── frontend/
│   ├── Dockerfile           ← ENV NEXT_PUBLIC_API_URL=/api/v1 BEFORE COPY+BUILD
│   ├── .dockerignore
│   ├── next.config.ts       ← env: { NEXT_PUBLIC_API_URL: "/api/v1" }
│   ├── package.json
│   └── src/
│       ├── app/             ← pages (client components for SSR avoidance)
│       ├── components/
│       ├── lib/api.ts       ← hardcoded /api/v1, NO localhost fallback
│       └── contracts/
└── backend/
    ├── Dockerfile
    ├── main.py
    ├── db.py                ← immutable=1 for Docker
    ├── api/
    └── requirements.txt
```

## Key File Templates

### frontend/Dockerfile

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps      # NOT npm ci
ENV NEXT_PUBLIC_API_URL=/api/v1         # MUST be before COPY+BUILD
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
```

### frontend/next.config.ts

```typescript
import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  typescript: { ignoreBuildErrors: true },
  env: { NEXT_PUBLIC_API_URL: "/api/v1" },
};
export default nextConfig;
```

### frontend/src/lib/api.ts

```typescript
async function fetchAPI<T>(path: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`);  // hardcoded, NO env var
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
export { fetchAPI };
```

### backend/db.py

```python
import sqlite3, os
PIPELINE_DB = os.environ.get("DB_PATH", "default.db")

def get_db() -> sqlite3.Connection:
    if os.environ.get("DB_PATH"):
        # Docker: volume is read-only, SQLite needs immutable flag
        uri = f"file:{PIPELINE_DB}?mode=ro&immutable=1"
        db = sqlite3.connect(uri, uri=True)
    else:
        db = sqlite3.connect(f"file:{PIPELINE_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db
```

## Deployment Workflow

```
1. Write code locally (Windows)
2. Tar + SCP to cloud (paramiko)
3. docker compose up -d --build    ← NEVER --no-cache
4. docker compose restart nginx    ← ALWAYS after frontend build
5. curl localhost:80/api/v1/dashboard
6. Browser verify: browser_navigate(http://IP)
```

## Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| "API unavailable" | `NEXT_PUBLIC_API_URL` not inlined | Set in Dockerfile ENV + next.config.ts + hardcode in api.ts |
| `sqlite3.OperationalError` | WAL mode on ro mount | `mode=ro&immutable=1` in URI |
| `useSearchParams` prerender error | Server Component | Wrap in `<Suspense>` |
| Tailwind v4 `@apply` errors | shadcn/v4 incompatibility | Use vanilla CSS instead of @apply |
| `npm ci` fails on Alpine | Cross-platform lockfile | Use `npm install --legacy-peer-deps` |
| 502 after rebuild | Nginx cached upstream | `docker compose restart nginx` |
| SSR page API error | fetch() on frontend container | Convert to client component + useEffect |
| Cloud crash on build | `--no-cache` OOM | Never use --no-cache |
| TypeScript errors | Missing @types/* | `ignoreBuildErrors: true` |
| DB corrupted after SFTP download | Immutable mode vs local open | Restore via `src.backup(dst)` |
| Page empty/grep shows 0 content | Client components not in grep output | Verify with browser_navigate, not curl grep |
| Old `/api/` prefix on unified routes | V8 backend serves /news/ /auth/ directly | Remove /api/ prefix from old-platform page fetches |
| SQLAlchemy 2.0 raw SQL error | `db.execute("SQL")` without text() | Use `db.execute(text("SQL"))` |
| PG events table mismatch | Old PG has different schema than ORM model | Drop+recreate with CASCADE, then migrate SQLite→PG |
| Scrapling always times out | Timeout passed in seconds, expects ms | `timeout * 1000` — see references/fetch-engine-optimization.md |
| France24/investing 403 on direct | Missing Sec-Fetch-* headers | Add browser fingerprint headers — see references/fetch-engine-optimization.md |
| V2 npm deps not in Docker build | Dynamic imports fail, static imports missing | Use static imports, ensure packages in package.json before Docker build |
| /news/{id} returns 401/empty | Endpoint requires JWT auth | Make auth optional with Header(None), VIP-only for content_md |
| Article content empty in PG | SQLite→PG sync only pushes metadata | Add content push step in pipeline, ON CONFLICT(url) DO UPDATE content_md |
| Client page shows \"empty\" in grep | Client components render via JS | Verify with browser_navigate, not curl grep |

## Workflow Rules

1. **NEVER make code changes without asking.** Present analysis + proposed fix, wait for explicit approval.
2. **All Docker operations on cloud only.** No local npm, docker build, or docker compose.
3. **After every change, commit + push to git.**
4. **Verify with browser_navigate AND curl.**
5. **nginx.conf must route ALL backend paths** (/news/, /auth/, /admin/, /internal/, /docs).

## Related References

- `references/paramiko-deploy-pattern.md` — SCP upload via paramiko
- `references/sqlite-readonly-docker.md` — SQLite immutable mode
- `references/fetch-engine-optimization.md` — Scrapling timeout fix, header optimization, retry patterns
| Old `/api/` prefix on unified routes | V8 backend serves /news/ /auth/ directly | Remove /api/ prefix from old-platform page fetches |
| SQLAlchemy 2.0 raw SQL error | `db.execute("SQL")` without text() | Use `db.execute(text("SQL"))` |
| PG events table mismatch | Old PG has different schema than ORM model | Drop+recreate with CASCADE, then migrate SQLite→PG |

## Workflow Rules

1. **NEVER make code changes without asking.** Present the analysis, proposed fix, and wait for explicit approval. This includes patches, file writes, and terminal commands that modify code.
2. **All Docker operations on cloud only.** No local npm, docker build, or docker compose.
3. **After every change, commit + push to git.** Both hermes-agent-backup AND the project's own repo if separate.
4. **Verify with browser_navigate AND curl.** Client-rendered pages won't show content in grep/curl alone.
5. **nginx.conf must route ALL backend paths**, not just /api/*. Include /news/, /auth/, /admin/, /internal/, /docs etc.
