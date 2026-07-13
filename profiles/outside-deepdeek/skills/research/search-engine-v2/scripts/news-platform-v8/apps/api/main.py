"""News Platform V8 — Unified FastAPI entry point.

Merges old platform (17 endpoints) + Sentinel V1 (6 endpoints).
Single PostgreSQL data source. No SQLite. No hardcoded secrets.

Routes:
  Old: /news/*, /internal/*, /auth/*, /admin/*, /ads/*, /categories
  New: /api/v1/dashboard, /api/v1/events/*, /api/v1/sources,
        /api/v1/search, /api/v1/map/events
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="News Platform V8",
    version="8.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Old Platform Routes ──────────────────────────────────────
from apps.api.routes import news, internal, categories, auth, admin, ads, admin_config

app.include_router(internal.router)
app.include_router(news.router)
app.include_router(categories.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_config.router)
app.include_router(ads.router)

# ── Sentinel V1 Routes ───────────────────────────────────────
from apps.api.routes import dashboard_v1, events_v1, sources_v1, search_v1, map_v1

app.include_router(dashboard_v1.router, prefix="/api/v1")
app.include_router(events_v1.router, prefix="/api/v1")
app.include_router(sources_v1.router, prefix="/api/v1")
app.include_router(search_v1.router, prefix="/api/v1")
app.include_router(map_v1.router, prefix="/api/v1")


@app.get("/")
def root():
    return {"service": "News Platform V8", "version": "8.0.0"}
