# Docker Cloud Deployment Pattern

## Architecture

```
Cloud VPS → docker compose up -d
  ├── nginx (:80) → reverse proxy
  │     /     → frontend:3000
  │     /api/ → backend:8000
  ├── frontend (node:22-alpine)
  │     Next.js 16 static build → npx next start
  └── backend (python:3.12-slim)
        FastAPI + SQLite read-only mount
```

## docker-compose.yml Template

```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ./data:/data:ro
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

## nginx.conf Template

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

## Frontend Dockerfile (Next.js 16)

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps
ENV NEXT_PUBLIC_API_URL=/api/v1
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

## Backend Dockerfile (FastAPI + SQLite)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Code Transfer (paramiko SCP pattern)

```python
import paramiko, tarfile, io, os

SRC = os.path.expanduser("~/workspace/news-intel-web")
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".git", "__pycache__")]
        for f in files:
            if f.endswith(".pyc"): continue
            tar.add(os.path.join(root, f), os.path.relpath(os.path.join(root, f), SRC))

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)
buf.seek(0)
sftp = client.open_sftp()
sftp.putfo(buf, "/tmp/project.tar.gz")
sftp.close()
client.exec_command("cd /home/user/project && tar xzf /tmp/project.tar.gz")
```

## Deploy Workflow

```bash
# 1. Transfer code
python deploy.py

# 2. Build + start on cloud
ssh user@host "cd /home/user/project && docker compose up -d --build"

# 3. Restart nginx (always after frontend rebuild)
ssh user@host "cd /home/user/project && docker compose restart nginx"

# 4. Verify
curl http://host:80
curl http://host:80/api/v1/dashboard
```

## Common Issues

| Symptom | Fix |
|---------|-----|
| 502 after frontend rebuild | `docker compose restart nginx` |
| "API unavailable" in browser | Hardcode `/api/v1` in `api.ts`, add `ENV` in Dockerfile |
| SQLite "unable to open" | Use `?mode=ro&immutable=1` URI |
| Server crash during `--no-cache` | Use incremental build on low-memory hosts |
| Push rejected (>100MB) | `git reset --soft` + `git rm --cached` large files |
