"""
stocks.py — Endpoints de acciones individuales.

GET /api/stocks/{ticker}
    Metadata completa + stats de una acción.

GET /api/stocks/{ticker}/chart
    Serie histórica de precios con downsampling automático.
    - n_rows <= 1500  → datos diarios (sin cambio)
    - n_rows <= 5000  → datos semanales (AVG close, SUM volume/dividends)
    - n_rows >  5000  → datos mensuales

GET /api/search?q={query}
    Búsqueda global de acciones por ticker o nombre (máx 15 resultados).

GET /api/status
    Estado del build de la DB.

POST /api/admin/rebuild
    Fuerza reconstrucción de la DB.
"""
import sqlite3
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..db import get_db, get_build_state, build_db
from ..services.universe_f5 import f5_base_where_sql

router = APIRouter(tags=["stocks"])

_CACHE_1H = "public, max-age=3600"


@router.get("/api/search")
def search_stocks(q: str = Query("", min_length=1), db: sqlite3.Connection = Depends(get_db)):
    """Búsqueda rápida por ticker o nombre. Máx 15 resultados."""
    pattern = f"%{q}%"
    where_sql, f5_params = f5_base_where_sql()
    rows = db.execute(f"""
        SELECT ticker, short_name, sector
        FROM stocks
        WHERE (ticker LIKE ? OR short_name LIKE ?) AND {where_sql}
        ORDER BY market_cap DESC NULLS LAST
        LIMIT 15
    """, [pattern, pattern] + f5_params).fetchall()
    return JSONResponse([dict(r) for r in rows], headers={"Cache-Control": "no-store"})


@router.get("/api/status")
def get_status():
    return get_build_state()


@router.post("/api/admin/rebuild")
async def rebuild_db():
    """Reconstruye la DB en background."""
    state = get_build_state()
    if not state["ready"]:
        return {"ok": False, "message": "Build ya en progreso."}

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, build_db)
    return {"ok": True, "message": "Reconstrucción iniciada."}


@router.get("/api/stocks/{ticker}")
def get_stock(ticker: str, db: sqlite3.Connection = Depends(get_db)):
    """Retorna metadata completa y stats de una acción."""
    ticker = ticker.upper()
    where_sql, f5_params = f5_base_where_sql()
    row = db.execute(f"""
        SELECT
            ticker, short_name, sector, industry,
            market_cap, beta, trailing_pe, dividend_yield,
            week52_low, week52_high, current_price,
            full_time_employees, summary,
            cagr, ann_volatility, n_rows
        FROM stocks WHERE ticker = ? AND {where_sql}
    """, [ticker] + f5_params).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado en el universo F5.")

    return JSONResponse(content=dict(row), headers={"Cache-Control": _CACHE_1H})


@router.get("/api/stocks/{ticker}/chart")
def get_chart(
    ticker: str,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Retorna la serie histórica del ticker con downsampling automático.
    n_rows <= 1500 → diario | <= 5000 → semanal | > 5000 → mensual
    """
    ticker = ticker.upper()

    # Conocer total de filas para decidir nivel de agregación
    where_sql, f5_params = f5_base_where_sql()
    stock_row = db.execute(
        f"SELECT n_rows FROM stocks WHERE ticker = ? AND {where_sql}",
        [ticker] + f5_params,
    ).fetchone()
    if not stock_row:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado en el universo F5.")
    n_rows = stock_row["n_rows"]

    date_filter = ""
    params: list = [ticker]
    if from_date:
        date_filter += " AND date >= ?"
        params.append(from_date)
    if to_date:
        date_filter += " AND date <= ?"
        params.append(to_date)

    if n_rows <= 1500:
        # Datos diarios — sin agrupación
        query = f"""
            SELECT date, close, volume, dividends
            FROM prices WHERE ticker = ?{date_filter}
            ORDER BY date ASC
        """
        rows = db.execute(query, params).fetchall()
        dates     = [r["date"]      for r in rows]
        closes    = [r["close"]     for r in rows]
        volumes   = [r["volume"]    for r in rows]
        dividends = [r["dividends"] for r in rows]

    elif n_rows <= 5000:
        # Datos semanales (ISO year-week)
        query = f"""
            SELECT
                strftime('%Y-W%W', date)       AS period,
                MIN(date)                       AS date,
                AVG(close)                      AS close,
                CAST(SUM(volume) AS INTEGER)    AS volume,
                SUM(dividends)                  AS dividends
            FROM prices WHERE ticker = ?{date_filter}
            GROUP BY period
            ORDER BY period ASC
        """
        rows = db.execute(query, params).fetchall()
        dates     = [r["date"]      for r in rows]
        closes    = [r["close"]     for r in rows]
        volumes   = [r["volume"]    for r in rows]
        dividends = [r["dividends"] for r in rows]

    else:
        # Datos mensuales
        query = f"""
            SELECT
                strftime('%Y-%m', date)         AS period,
                MIN(date)                       AS date,
                AVG(close)                      AS close,
                CAST(SUM(volume) AS INTEGER)    AS volume,
                SUM(dividends)                  AS dividends
            FROM prices WHERE ticker = ?{date_filter}
            GROUP BY period
            ORDER BY period ASC
        """
        rows = db.execute(query, params).fetchall()
        dates     = [r["date"]      for r in rows]
        closes    = [r["close"]     for r in rows]
        volumes   = [r["volume"]    for r in rows]
        dividends = [r["dividends"] for r in rows]

    if not dates:
        raise HTTPException(status_code=404, detail=f"Sin datos de precios para '{ticker}'.")

    payload = {
        "ticker":    ticker,
        "dates":     dates,
        "close":     closes,
        "volume":    volumes,
        "dividends": dividends,
        "resolution": "daily" if n_rows <= 1500 else ("weekly" if n_rows <= 5000 else "monthly"),
    }
    return JSONResponse(content=payload, headers={"Cache-Control": _CACHE_1H})
