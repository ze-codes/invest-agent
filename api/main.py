from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routers import health, registry, series, analytics, events, history, viz


app = FastAPI(title="invest-agent API", version="0.1.0")

# CORS (dev-friendly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include modular routers
app.include_router(health.router)
app.include_router(registry.router)
app.include_router(series.router)
app.include_router(analytics.router)
app.include_router(events.router)
app.include_router(history.router)
app.include_router(viz.router)

# Static files (for HTML viz pages)
static_dir = Path(__file__).resolve().parents[1] / "api" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


