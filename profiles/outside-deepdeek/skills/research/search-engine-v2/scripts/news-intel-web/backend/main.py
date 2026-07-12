"""News Intelligence Web API — FastAPI Read Adapter v1.0

Read-only adapter over existing v4.4 event_registry SQLite.
No write operations. No PostgreSQL dependency.
Serves 6 endpoints for the React dashboard.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="News Intelligence API",
    version="1.0.0",
    description="Read-only API adapter for v4.4 Event Registry (SQLite)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Import and register route modules
from api.dashboard import router as dashboard_router
from api.events import router as events_router
from api.sources import router as sources_router
from api.search import router as search_router
from api.map import router as map_router

app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(map_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
