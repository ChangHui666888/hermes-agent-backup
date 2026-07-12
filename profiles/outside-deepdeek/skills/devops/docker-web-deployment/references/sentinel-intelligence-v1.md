# Sentinel Intelligence V1 — Deployment Reference

## Cloud VPS

- Host: `100.107.117.23`
- OS: Ubuntu 24.04 (K8s worker node `ss-usc-k8s-worker-9`)
- Docker: 29.5.3
- RAM: 3.9GB (no `--no-cache` builds)
- Disk: 63GB total, 48GB available

## Deploy Commands

```bash
# From local Windows (Hermes):
python deploy.py  # paramiko tar + upload + extract

# From cloud SSH:
cd /home/administrator/news-intel-web
docker compose up -d --build
docker compose restart nginx  # after frontend rebuild

# Verify:
curl localhost:80                     # → HTML
curl localhost:80/api/v1/dashboard    # → JSON
```

## Database

SQLite file at `/home/administrator/news-intel-web/data/news_intel.db` (2.3MB).
Mounted read-only: `./data:/data:ro` in docker-compose.yml.
Python connection: `sqlite3.connect("file:/data/news_intel.db?mode=ro&immutable=1", uri=True)`.

## Ports

- `80`: nginx (public)
- `8000`: FastAPI backend (internal Docker network only)
- `3000`: Next.js frontend (internal Docker network only)

## Build Order

1. Upload code via SCP/paramiko (exclude node_modules, .next, .git)
2. `docker compose up -d --build`
3. Wait for frontend build (~60s for `npm install` + `next build`)
4. `docker compose restart nginx`
5. Verify with curl

## Image Sizes

- `news-intel-web-backend`: ~325MB
- `news-intel-web-frontend`: ~93MB
- `nginx:alpine`: ~45MB
