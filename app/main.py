"""
main.py — FastAPI app factory para la webapp P4.

Startup:
  - Si la DB SQLite no existe, la construye en background.
  - Monta archivos estáticos en /static.
  - Sirve la SPA (index.html) en /.
"""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.gzip import GZipMiddleware

from .db import build_db_if_needed
from .routers import portfolio, report, sectors, stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

# Rutas de templates y static dentro del contenedor
_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR    = _HERE.parent / "static"

app = FastAPI(title="P4 — Sistema recomendador", version="1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Archivos estáticos
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Routers
app.include_router(sectors.router)
app.include_router(stocks.router)
app.include_router(portfolio.router)
app.include_router(report.router)


@app.on_event("startup")
async def startup_event():
    """Construye la DB en background para no bloquear el event loop."""
    log.info("Startup: verificando DB...")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, build_db_if_needed)


@app.get("/", response_class=HTMLResponse)
async def serve_spa(request: Request):
    static_version = 1
    try:
        static_version = int((STATIC_DIR / "app.js").stat().st_mtime)
    except Exception:
        static_version = 1

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "static_version": static_version},
    )
