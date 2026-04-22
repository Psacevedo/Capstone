"""
sectors.py — Endpoints de sectores.

GET /api/sectors
    Retorna lista de sectores con conteo de acciones.

GET /api/sectors/{sector}/stocks
    Retorna acciones de un sector, ordenadas por market_cap desc.
"""
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..db import get_db
from ..services.universe_f5 import f5_base_where_sql

_CACHE_1H = "public, max-age=3600"

router = APIRouter(prefix="/api/sectors", tags=["sectors"])


@router.get("")
def list_sectors(db: sqlite3.Connection = Depends(get_db)):
    """Lista todos los sectores con el conteo de acciones."""
    where_sql, params = f5_base_where_sql()
    rows = db.execute(f"""
        SELECT sector, COUNT(*) as count
        FROM stocks
        WHERE sector IS NOT NULL AND {where_sql}
        GROUP BY sector
        ORDER BY count DESC
    """, params).fetchall()

    data = [{"sector": r["sector"], "count": r["count"]} for r in rows]
    return JSONResponse(content=data, headers={"Cache-Control": _CACHE_1H})


@router.get("/{sector}/stocks")
def get_sector_stocks(sector: str, db: sqlite3.Connection = Depends(get_db)):
    """Retorna las acciones de un sector ordenadas por market_cap desc."""
    where_sql, params = f5_base_where_sql()
    rows = db.execute(f"""
        SELECT
            ticker, short_name, industry,
            market_cap, current_price,
            cagr, ann_volatility,
            beta, trailing_pe, dividend_yield,
            week52_low, week52_high, n_rows
        FROM stocks
        WHERE sector = ? AND {where_sql}
        ORDER BY market_cap DESC NULLS LAST
    """, [sector] + params).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' no encontrado o sin acciones.")

    data = [dict(r) for r in rows]
    return JSONResponse(content=data, headers={"Cache-Control": _CACHE_1H})
