import logging
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routers import health, registry, series, analytics, events, history, viz, llm


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
app.include_router(llm.router, prefix="/llm")

# Static files (for HTML viz pages)
static_dir = Path(__file__).resolve().parents[1] / "api" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/static/viz_indicators.html")


# -----------------------
# Simple access logging middleware (time + client IP)
# -----------------------
_access_logger = logging.getLogger("api.access")


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    try:
        return request.client.host  # type: ignore[return-value]
    except Exception:
        return "unknown"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    client_ip = _get_client_ip(request)
    ts = datetime.now(timezone.utc).isoformat()
    method = request.method
    path = request.url.path
    ua = request.headers.get("user-agent", "")
    response = await call_next(request)
    dur_ms = int((time.time() - t0) * 1000)
    try:
        _access_logger.info(
            f"{ts} ip={client_ip} {method} {path} status={response.status_code} dur={dur_ms}ms ua={ua}"
        )
    except Exception:
        pass
    return response

