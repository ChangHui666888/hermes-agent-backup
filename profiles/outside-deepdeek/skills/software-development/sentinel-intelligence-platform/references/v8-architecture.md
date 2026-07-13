# V8 Architecture Reference

## Project Structure
```
search-engine-v2/scripts/
├── news-platform-v8/        ← V8 Backend (FastAPI + PG)
│   ├── apps/api/
│   │   ├── main.py          ← Entry (23 endpoints)
│   │   ├── database.py      ← PG connection
│   │   ├── models.py        ← 18 SQLAlchemy models
│   │   ├── schemas.py       ← Pydantic
│   │   └── routes/          ← 12 route files
│   ├── Dockerfile
│   └── .env                 ← gitignored
│
├── news-intel-web/          ← V8 Frontend + Docker Compose
│   ├── frontend/
│   │   └── src/app/         ← 12 page routes
│   ├── backend/             ← (deprecated, replaced by news-platform-v8)
│   ├── docker-compose.yml   ← 4 services: postgres+backend+frontend+nginx
│   └── nginx.conf
│
├── news_intel/              ← Pipeline (data production)
│   ├── aggregator.py        ← L5 event aggregation
│   └── news_intel.db        ← SQLite (local only)
│
└── news-intel-platform/     ← Old system (frozen)
```

## Docker Compose
```yaml
services:
  postgres:    image: postgres:16-alpine, volume: external pgdata
  backend:     build: ../news-platform-v8, PYTHONPATH=/app
  frontend:    build: ./frontend
  nginx:       image: nginx:alpine, ports 80:80
volumes:
  pgdata:      external: true, name: news-intel-platform_pgdata
```

## Key Endpoints
| Route | Data | Auth |
|-------|------|:--:|
| /api/v1/dashboard | events + sources | Public |
| /api/v1/events/{id} | Full Event Dossier | Public |
| /news/* | Articles | Public (content masked for free) |
| /auth/* | Login/Register | Public |
| /admin/* | Admin dashboard | JWT + admin |
| /internal/* | Pipeline push | INTERNAL_TOKEN |
