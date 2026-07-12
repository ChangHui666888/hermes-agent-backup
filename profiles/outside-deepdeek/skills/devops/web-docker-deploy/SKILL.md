---
name: web-docker-deploy
description: Deploy Next.js + FastAPI + SQLite web apps to cloud Docker. NEVER build locally.
version: 1.0.0
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
4. **`NEXT_PUBLIC_API_URL` must be inlined at build time** — set in Dockerfile ENV AND next.config.ts `env` block.

## Project Structure

```
project/
├── docker-compose.yml
├── nginx.conf
├── frontend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── next.config.ts     ← MUST have env: { NEXT_PUBLIC_API_URL: "/api/v1" }
│   ├── package.json
│   └── src/
│       ├── app/           ← pages
│       ├── components/    ← React components
│       ├── lib/api.ts     ← API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1"
│       └── contracts/     ← TypeScript interfaces (frozen)
└── backend/
    ├── Dockerfile
    ├── main.py            ← FastAPI entry
    ├── db.py              ← SQLite connect with immutable mode
    ├── models/schemas.py  ← Pydantic models matching contracts
    ├── api/               ← route modules
    └── requirements.txt
```

## Critical Files

### frontend/Dockerfile

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps
ENV NEXT_PUBLIC_API_URL=/api/v1    # ← MUST be before COPY+BUILD
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
  env: { NEXT_PUBLIC_API_URL: "/api/v1" },  // ← build-time inlining
};
export default nextConfig;
```

### frontend/src/lib/api.ts

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";  // ← NEVER localhost fallback
```

### backend/db.py — SQLite Read-Only

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
```python

### nginx.conf

```nginx
server {
    listen 80;
    location /api/ { proxy_pass http://backend:8000/api/; }
    location / { proxy_pass http://frontend:3000; }
}
```

### docker-compose.yml

```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ${EVENT_REGISTRY_PATH:-./data}:/data:ro
    environment:
      - DB_PATH=/data/news_intel.db

  frontend:
    build: ./frontend
    environment:
      - NEXT_PUBLIC_API_URL=/api/v1

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"
```

## Deployment Workflow

```bash
# 1. Write code locally (Windows)
# 2. Tar + SCP to cloud (paramiko) — see references/paramiko-deploy-pattern.md for Python snippet
# 3. On cloud: docker compose up -d --build
# 4. Verify: curl localhost:80/api/v1/dashboard
```

## Cloud Crash Recovery

If the cloud VPS becomes unreachable after a build (common with `--no-cache` on small VMs):
1. Wait for the host to reboot (K8s worker nodes auto-recover)
2. SSH in and check with `docker compose ps`
3. If containers are down: `docker compose up -d` (no rebuild needed, images exist)
4. Always `docker compose restart nginx` after frontend container IP change

## Common Pitfalls

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| "API unavailable" in browser | `NEXT_PUBLIC_API_URL` not inlined, falls back to localhost | Set in Dockerfile ENV + next.config.ts env |
| `sqlite3.OperationalError: unable to open database file` | WAL mode needs write access on read-only mount | Add `&immutable=1` to URI |
| `useSearchParams` prerender error | Server Component using client hook | Wrap in `<Suspense>` or make client component |
| Tailwind v4 `@apply` errors (`border-border`, `bg-background`) | `@apply` with shadcn/Tailwind v4 incompatibility | Use vanilla CSS instead of `@apply` |
| `npm ci` fails on Alpine | Platform-locked package-lock.json | Use `npm install --legacy-peer-deps` instead |
| 502 after frontend rebuild | Nginx caches old upstream IP | `docker compose restart nginx` |
| SSR page shows API error | Server Component fetch() runs on frontend container (no API) | Convert page to client component with useEffect fetch |
| Cloud crashes on `--no-cache` build | Full rebuild exhausts RAM (~3.9GB) | Never use `--no-cache`; incremental rebuild works |
| `npm ci` fails on Alpine | Platform-locked package-lock.json from Windows | Use `npm install --legacy-peer-deps` (NOT `npm ci`) |
| TypeScript type error on `react-simple-maps` | No `@types/react-simple-maps` | `typescript: { ignoreBuildErrors: true }` in next.config.ts |

For the complete 10-issue pitfalls reference, see `references/sqlite-readonly-docker.md`.`,
