---
name: docker-web-deployment
description: Deploy Next.js + FastAPI web applications to cloud VPS via Docker Compose with nginx reverse proxy. Covers Dockerfile patterns, Tailwind v4 compatibility, SQLite read-only volumes, Next.js SSR client-component routing, and cloud-only build workflow.
version: 1.0.0
platforms: [linux, windows]
tags: [docker, deployment, nextjs, fastapi, sqlite, nginx]
---

# Docker Web Deployment

Deploy a Next.js frontend + FastAPI backend to a cloud VPS using Docker Compose with nginx reverse proxy. All builds happen on the target server, never locally.

## Trigger Conditions

- User asks to deploy a web app (Next.js, FastAPI, or similar) to a cloud server
- Docker Compose multi-service setup with nginx
- SQLite read-only access from inside Docker container
- Next.js SSR pages failing to reach backend API in Docker

## Frozen Rules

1. **No local builds** — all `docker build`, `docker compose up`, `npm` run on the cloud VPS
2. **No localhost verification** — verify via `curl` on the cloud host, never `localhost:3000`
3. **Windows is dev only** — write code on Windows, build+run on Linux cloud
4. **nginx is the entry point** — all traffic through port 80, backend and frontend ports are internal Docker network only

## Project Structure

```
project/
├── docker-compose.yml
├── nginx.conf
├── frontend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── package.json
│   └── src/
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py
    └── api/
```

## Dockerfile Patterns

### Next.js Frontend (node:22-alpine)

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps  # NOT npm ci (cross-platform lockfile issues)
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

**Pitfall**: `npm ci` fails when lockfile was generated on Windows (platform-specific optional deps differ). Use `npm install --legacy-peer-deps` instead.

### FastAPI Backend (python:3.12-slim)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## docker-compose.yml

```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ${EVENT_REGISTRY_PATH:-./data}:/data:ro
    environment:
      - DB_PATH=/data/database.db
    restart: unless-stopped

  frontend:
    build: ./frontend
    environment:
      - NEXT_PUBLIC_API_URL=/api/v1      # relative URL for browser-side fetch
    restart: unless-stopped
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"
    restart: unless-stopped
    depends_on:
      - frontend
```

## nginx.conf

```nginx
server {
    listen 80;

    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
    }
}
```

## SQLite Read-Only in Docker

When mounting a SQLite database as a read-only Docker volume, use the `immutable=1` URI parameter:

```python
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "database.db")

if os.environ.get("DB_PATH"):
    # Docker read-only mount: prevents WAL/SHM file creation attempts
    uri = f"file:{DB_PATH}?mode=ro&immutable=1"
    db = sqlite3.connect(uri, uri=True)
else:
    # Local development
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
```

**Root cause**: SQLite WAL mode creates `-wal` and `-shm` sidecar files on open. With a read-only volume mount, file creation fails → `OperationalError: unable to open database file`. `immutable=1` tells SQLite the database won't change, skipping WAL file creation entirely.

## Next.js API Routing in Docker

**Problem**: Server Components (`async function Page()`) do SSR. During SSR, `fetch("/api/v1/dashboard")` resolves to `http://frontend:3000/api/v1/dashboard` — but the API is on `backend:8000`, not frontend:3000.

**Fix**: Make data-fetching pages Client Components. The fetch then runs in the browser, resolving `/api/v1/` through nginx → backend correctly.

```tsx
// BEFORE (Server Component — SSR fails in Docker):
export default async function Page() {
  const data = await fetchAPI("/dashboard");  // resolves to frontend:3000 ❌
  return <div>{data}</div>;
}

// AFTER (Client Component — browser fetch works):
"use client";
export default function Page() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchAPI("/dashboard").then(setData);  // browser resolves via nginx ✅
  }, []);
  return <div>{data}</div>;
}
```

## Tailwind v4 @apply Compatibility

Tailwind v4 with `@theme inline` doesn't fully support `@apply` for certain custom utilities in Docker builds. Replace `@apply` with raw CSS:

```css
/* BEFORE — fails in Docker build */
body {
  @apply bg-background text-foreground antialiased;
}

/* AFTER — works everywhere */
body {
  background-color: var(--background);
  color: var(--foreground);
  -webkit-font-smoothing: antialiased;
}
```

## Build Verification (on cloud host)

```bash
# Build all services
cd project && docker compose build

# Start
docker compose up -d

# Verify
curl localhost:80                    # → HTML with page title
curl localhost:80/api/v1/endpoint    # → JSON response

# Check logs
docker compose logs backend --tail=20
```

## Additional Docker Build Pitfalls

### Nginx 502 after frontend rebuild

When frontend container is rebuilt, nginx holds stale upstream connection to old container IP. Symptom: `502 Bad Gateway` while all containers show UP.

```bash
docker compose up -d --build frontend
docker compose restart nginx     # REQUIRED after frontend rebuild
```

### NEXT_PUBLIC_API_URL: build-time vs runtime

`NEXT_PUBLIC_*` env vars are inlined at BUILD time. docker-compose.yml `environment` only sets runtime. Must use BOTH:

1. **Dockerfile**: `ENV NEXT_PUBLIC_API_URL=/api/v1` (before `npm run build`)
2. **next.config.ts**: `env: { NEXT_PUBLIC_API_URL: "/api/v1" }` (build-time fallback)
3. **api.ts fallback**: `"/api/v1"` — never `localhost:8000`

### --no-cache crashes small VMs

On <4GB RAM VPS, `docker compose build --no-cache` exhausts memory. Use incremental builds:

```bash
docker exec <container> rm -rf .next   # force clean if needed
docker compose up -d --build frontend
```

### useSearchParams() requires Suspense

Pages using `useSearchParams()` crash during `next build` in Docker with `Error occurred prerendering page`. Next.js tries to statically prerender but `useSearchParams` needs a client-side request context.

```tsx
// BEFORE — prerender error:
export default function ExplorerPage() {
  const searchParams = useSearchParams();  // ❌ prerender crash
  ...
}

// AFTER — wrap in Suspense boundary:
function ExplorerContent() {
  const searchParams = useSearchParams();  // ✅ inside Suspense
  ...
}
export default function ExplorerPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ExplorerContent />
    </Suspense>
  );
}
```

### TypeScript type errors on 3rd-party modules

`react-simple-maps` and similar packages lack type declarations, causing Docker build failures. Quick fix:

```ts
// next.config.ts
const nextConfig: NextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
};
```

Or create `src/types/react-simple-maps.d.ts` with `declare module 'react-simple-maps' { ... }`.

### SFTP-downloaded SQLite appears corrupted

After SFTP download, `sqlite3.connect()` reports `database disk image is malformed`. The DB is fine on the server but the file transfer creates WAL inconsistencies. Repair by copying through Python:

```python
import sqlite3
src = sqlite3.connect("file:corrupted.db?mode=ro&immutable=1", uri=True)
dst = sqlite3.connect("repair.db")
src.backup(dst)
dst.close(); src.close()
# repair.db is now clean
```

**Root cause**: SQLite in immutable mode keeps WAL state that corrupts on raw file copy. Python's `backup()` API copies the logical database content cleanly.

### Empty page / skeleton only when browser opens

When curl shows HTML but the browser renders only header/sidebar (no dashboard content), the issue is client-side fetch failing. Diagnose differently from server-side debugging:

```bash
# Server-side (won't catch client fetch issues):
curl localhost:80 | grep "Global Situation"   # → 0 (page IS rendering, but content is loaded by JS)

# Correct diagnosis:
browser_navigate(http://IP)                   # → shows "API unavailable" in snapshot
browser_console(expression="fetch('/api/v1/dashboard')...")  # test client fetch
```

**Root cause**: Next.js client components do API fetches in the browser, not during SSR. Server-side curl only captures the initial HTML shell.

`npm install` inside Alpine may miss transitive deps. Common fixes:

```bash\nnpm install prop-types --legacy-peer-deps\nnpm install @tailwindcss/postcss --legacy-peer-deps\n```

The old `shadcn-ui` package is deprecated. Use:

```bash
npx shadcn@latest init -d    # default style, no prompts
```

The `--style new-york` flag was removed in v4.
