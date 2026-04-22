"""
universe_f5.py - Definicion operativa del universo F5.

Centraliza las restricciones usadas para:
- Explorer "Universo F5" (sectores, busqueda, fichas).
- Seleccion de candidatos del recomendador (router portfolio).
"""

from typing import List, Tuple

F5_MIN_HISTORY_ROWS = 2520
F5_MIN_PRICE = 5.0
F5_MIN_MARKET_CAP = 2_000_000_000

F5_VOL_MIN = 0.05
F5_VOL_MAX = 1.0


def f5_base_clauses() -> Tuple[List[str], List]:
    clauses = [
        "cagr IS NOT NULL",
        "ann_volatility IS NOT NULL",
        "current_price IS NOT NULL",
        "market_cap IS NOT NULL",
        "n_rows >= ?",
        "current_price >= ?",
        "market_cap >= ?",
        "ann_volatility BETWEEN ? AND ?",
        "COALESCE(sector, '') <> 'Unknown'",
        "COALESCE(industry, '') <> 'Shell Companies'",
    ]
    params: List = [
        F5_MIN_HISTORY_ROWS,
        F5_MIN_PRICE,
        F5_MIN_MARKET_CAP,
        F5_VOL_MIN,
        F5_VOL_MAX,
    ]
    return clauses, params


def f5_base_where_sql() -> Tuple[str, List]:
    clauses, params = f5_base_clauses()
    return " AND ".join(clauses), params

