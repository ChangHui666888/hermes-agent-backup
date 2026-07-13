# News Intelligence Platform — Deployment Plan (Frozen)

## Frozen Deployment Rules

| Rule | Detail |
|------|--------|
| **Build location** | Cloud Ubuntu VPS only (100.107.117.23) |
| **npm / node** | Only inside Docker container on cloud |
| **docker build** | Only on cloud host |
| **docker compose** | Only on cloud host |
| **Verification** | curl from cloud host, not localhost:3000 |
| **Windows** | Development only — no builds, no servers, no npm |

## Target Architecture (Cloud)

```
Cloud VPS (100.107.117.23)

docker compose up -d
  │
  ├── frontend (node:22-alpine)
  │     npm run build inside container → npx next start :3000
  │
  ├── backend (python:3.12-slim)
  │     uvicorn :8000 · mounts SQLite (read-only)
  │
  └── nginx (nginx:alpine)
        :80 → frontend:3000
        /api/* → backend:8000
```

## Deployment Tasks

---

### Task D-001: Create Dockerfiles

**Goal**: Two Dockerfiles for frontend and backend

**Files**:

`frontend/Dockerfile`:
```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
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

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`frontend/.dockerignore`:
```
node_modules
.next
.git
```

**Acceptance**: Files exist, syntax valid (`docker build --check` would pass)

---

### Task D-002: Create docker-compose.yml + nginx.conf

**Goal**: Single `docker compose up` starts everything

`docker-compose.yml` (project root):
```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ${EVENT_REGISTRY_PATH:-./data}:/data:ro
    environment:
      - DB_PATH=/data/news_intel.db
    restart: unless-stopped

  frontend:
    build: ./frontend
    environment:
      - NEXT_PUBLIC_API_URL=/api/v1
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

`nginx.conf`:
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

**Acceptance**: Files exist, docker compose config parses without error

---

### Task D-003: Transfer Code to Cloud

**Goal**: All project files on cloud host

**Method**: SCP or paramiko tar upload (reuse deploy2.py pattern)

**Target path**: `/home/administrator/news-intel-web/`

**Files to transfer**:
```
frontend/src/       (all source)
frontend/public/
frontend/package.json
frontend/package-lock.json
frontend/tsconfig.json
frontend/next.config.js
frontend/tailwind.config.ts (if exists)
frontend/postcss.config.js (if exists)
frontend/components.json
backend/main.py
backend/db.py
backend/requirements.txt
backend/api/        (all route files)
backend/models/     (schemas)
docker-compose.yml
nginx.conf
```

**Exclude**: `node_modules/`, `.next/`, `.git/`, `__pycache__/`

**Acceptance**:
```
ssh administrator@100.107.117.23 "ls /home/administrator/news-intel-web/docker-compose.yml"
→ /home/administrator/news-intel-web/docker-compose.yml
```

---

### Task D-004: Build and Start on Cloud

**Goal**: Docker build + run all services on cloud VPS

**Commands** (all executed on cloud via SSH):
```bash
cd /home/administrator/news-intel-web

# Place SQLite DB for mount
mkdir -p data
cp /path/to/news_intel.db data/news_intel.db

# Build images
docker compose build

# Start services
docker compose up -d
```

**Acceptance**:
```bash
# From cloud host:
curl -s http://localhost:80 | head -5
→ HTML with "News Intelligence" title

curl -s http://localhost:80/api/v1/dashboard | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['metrics'])"
→ {'active_events': N, 'critical_events': N, ...}

curl -s http://localhost:80/api/v1/events/EVT-20260710-006 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['title'][:50])"
→ Apple calls OpenAI's hardware business...
```

**No `localhost:3000` verification. All verification through port 80 (nginx).**

---

### Task D-005: End-to-End Verification

**Goal**: Full pipeline → web flow confirmed

**Checklist** (all executed on cloud or via cloud):
```bash
# 1. Containers running
ssh administrator@100.107.117.23 "docker compose -f /home/administrator/news-intel-web/docker-compose.yml ps"
→ 3 services UP

# 2. Dashboard serves real data
curl -s http://100.107.117.23/api/v1/dashboard | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['hot_events']),'hot events')"

# 3. Event detail serves dossier
curl -s http://100.107.117.23/api/v1/events/EVT-20260710-006 | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert d['event_id']=='EVT-20260710-006'
assert len(d['evidence'])>0
assert len(d['source_chain'])>0
print('Dossier OK')
"

# 4. Sources endpoint
curl -s http://100.107.117.23/api/v1/sources | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['items']),'sources')"

# 5. Search
curl -s "http://100.107.117.23/api/v1/search?q=Iran" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['events']),'results for Iran')"
```

**Final acceptance**: Open `http://100.107.117.23` in browser → see Dashboard with real event data from pipeline.

---

## What Is Forbidden

| Forbidden | Reason |
|-----------|--------|
| `npm run dev` on Windows | Development only, not deployment |
| `docker build` on Windows | All builds on cloud |
| `docker compose up` on Windows | All runtime on cloud |
| `curl localhost:3000` on Windows | Not a deployment target |
| Installing Node.js on cloud host | Docker provides the runtime |
| Recovering old news-intel-platform containers | Different product, frozen |

## File Manifest

```
news-intel-web/
├── docker-compose.yml          ← D-002
├── nginx.conf                  ← D-002
├── frontend/
│   ├── Dockerfile              ← D-001
│   └── .dockerignore           ← D-001
├── backend/
│   ├── Dockerfile              ← D-001
│   └── ...
└── docs/
    ├── ARCHITECTURE.md
    ├── DATA_FLOW.md
    └── DEPLOYMENT.md           ← this file
```
