"""
benchmark.py — Benchmark simple: selección de las N acciones con mayor CAGR histórico.

Épica 3: caso base para comparar contra el modelo de Markowitz.
"""
import sqlite3
import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def get_top_cagr_benchmark(
    db: sqlite3.Connection,
    n: int = 10,
    sector: Optional[str] = None,
) -> List[Dict]:
    """
    Selecciona las N acciones con mayor CAGR histórico (período de calibración).

    Asigna pesos iguales (1/N) a cada acción seleccionada.

    Args:
        db: Conexión SQLite.
        n: Número de acciones a incluir.
        sector: Si se especifica, filtra por sector GICS.

    Returns:
        Lista de dicts {ticker, short_name, sector, cagr, ann_volatility, weight}.
    """
    query = """
        SELECT ticker, short_name, sector, cagr, ann_volatility
        FROM stocks
        WHERE cagr IS NOT NULL
          AND ann_volatility IS NOT NULL
          AND n_rows >= 252
    """
    params: list = []

    if sector:
        query += " AND sector = ?"
        params.append(sector)

    query += " ORDER BY cagr DESC LIMIT ?"
    params.append(n)

    rows = db.execute(query, params).fetchall()
    stocks = [dict(r) for r in rows]

    weight = 1.0 / len(stocks) if stocks else 0.0
    for s in stocks:
        s["weight"] = weight

    return stocks
