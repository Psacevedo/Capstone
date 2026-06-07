"""
candidate_selection.py — Selección y filtrado de candidatos de inversión
"""
import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..services.universe_f5 import f5_base_clauses, f5_base_where_sql


def candidate_query(
    profile_cfg: Dict,
    sector_filter: Optional[str],
) -> Tuple[str, List, str]:
    """Construye la query SQL para seleccionar candidatos."""
    clauses, params = f5_base_clauses()

    if profile_cfg["max_vol"] is not None:
        clauses.append("ann_volatility <= ?")
        params.append(profile_cfg["max_vol"])

    if sector_filter:
        clauses.append("sector = ?")
        params.append(sector_filter)
    elif profile_cfg["sectors"]:
        placeholders = ",".join("?" * len(profile_cfg["sectors"]))
        clauses.append(f"sector IN ({placeholders})")
        params.extend(profile_cfg["sectors"])

    if profile_cfg["dividend_bias"]:
        order_sql = "COALESCE(dividend_yield, 0) DESC, ann_volatility ASC, cagr DESC"
    else:
        order_sql = "cagr DESC, ann_volatility ASC"

    return " AND ".join(clauses), params, order_sql


def select_candidates(
    db: sqlite3.Connection,
    profile_cfg: Dict,
    candidate_pool_size: int,
    sector_filter: Optional[str],
) -> Tuple[List[Dict], int]:
    """Selecciona candidatos según perfil de riesgo."""
    where_sql, params, order_sql = candidate_query(profile_cfg, sector_filter)
    total_count = db.execute(
        f"SELECT COUNT(*) AS total FROM stocks WHERE {where_sql}",
        params,
    ).fetchone()["total"]

    rows = db.execute(
        f"""
        SELECT
            ticker, short_name, sector, industry, cagr, ann_volatility,
            market_cap, current_price, dividend_yield, trailing_pe, beta, n_rows
        FROM stocks
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ?
        """,
        params + [candidate_pool_size],
    ).fetchall()
    return [dict(row) for row in rows], int(total_count)


def select_market_cap_candidates(
    db: sqlite3.Connection,
    limit: int,
    sector_filter: Optional[str],
) -> Tuple[List[Dict], int]:
    """Selecciona candidatos ordenados por capitalización de mercado."""
    where_sql, params = f5_base_where_sql()
    clauses = [where_sql]
    out_params: List = list(params)
    if sector_filter:
        clauses.append("sector = ?")
        out_params.append(sector_filter)
    final_where = " AND ".join(clauses)

    total_count = db.execute(
        f"SELECT COUNT(*) AS total FROM stocks WHERE {final_where}",
        out_params,
    ).fetchone()["total"]

    rows = db.execute(
        f"""
        SELECT
            ticker, short_name, sector, industry, cagr, ann_volatility,
            market_cap, current_price, dividend_yield, trailing_pe, beta, n_rows
        FROM stocks
        WHERE {final_where}
        ORDER BY market_cap DESC NULLS LAST
        LIMIT ?
        """,
        out_params + [limit],
    ).fetchall()
    return [dict(row) for row in rows], int(total_count)


def build_benchmark_portfolio(
    candidates: List[Dict],
    target_holdings: int,
) -> Tuple[List[str], np.ndarray]:
    """Construye portafolio benchmark (equiponderado)."""
    selected = candidates[:target_holdings]
    if not selected:
        return [], np.array([])
    weights = np.ones(len(selected), dtype=float) / len(selected)
    return [item["ticker"] for item in selected], weights


def align_return_matrix(
    series_map: Dict[str, List[tuple]],
    tickers: Sequence[str],
) -> Tuple[List[str], np.ndarray]:
    """Alinea matriz de retornos diarios para tickers válidos."""
    from ..utils.helpers import daily_returns

    valid_tickers = [ticker for ticker in tickers if len(series_map.get(ticker, [])) >= 252]
    if len(valid_tickers) < 3:
        raise ValueError("No hay suficientes tickers con historia util en calibracion.")

    min_len = min(len(series_map[ticker]) for ticker in valid_tickers)
    matrix = np.column_stack(
        [
            daily_returns([close for _, close in series_map[ticker][-min_len:]])
            for ticker in valid_tickers
        ]
    )
    return valid_tickers, matrix


def fetch_price_series(
    db: sqlite3.Connection,
    tickers: Sequence[str],
    start: str,
    end: str,
) -> Dict[str, List[tuple]]:
    """Obtiene series de precios desde la base de datos."""
    if not tickers:
        return {}

    placeholders = ",".join("?" * len(tickers))
    rows = db.execute(
        f"""
        SELECT ticker, date, close
        FROM prices
        WHERE ticker IN ({placeholders})
          AND date >= ? AND date <= ?
          AND close IS NOT NULL
        ORDER BY ticker, date ASC
        """,
        list(tickers) + [start, end],
    ).fetchall()

    series: Dict[str, List[tuple]] = {}
    for row in rows:
        series.setdefault(row["ticker"], []).append((row["date"], float(row["close"])))
    return series
