"""
views_and_loadings.py — Parseo de views y cálculo de loadings para Black-Litterman
"""
import json
from typing import List, Sequence, Tuple

import numpy as np
from fastapi import HTTPException

from ..utils.helpers import normalize_numeric, zscore


def parse_views_json(
    raw_views: object,
    tickers: Sequence[str],
) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Parsea views JSON para Black-Litterman."""
    if isinstance(raw_views, str):
        try:
            data = json.loads(raw_views)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Views JSON invalido: {exc.msg}.") from exc
    elif isinstance(raw_views, list):
        data = raw_views
    else:
        raise HTTPException(status_code=400, detail="Las views deben enviarse como JSON valido.")

    if not isinstance(data, list) or not data:
        raise HTTPException(status_code=400, detail="Debes ingresar al menos una view para Black-Litterman.")

    ticker_index = {ticker: idx for idx, ticker in enumerate(tickers)}
    p_rows = []
    q_values = []
    views_used = []
    for item in data:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Cada view debe ser un objeto JSON.")
        ticker = str(item.get("ticker", "")).upper().strip()
        if ticker not in ticker_index:
            raise HTTPException(
                status_code=400,
                detail=f"La view referencia un ticker fuera del universo operativo: {ticker}.",
            )
        view_return_pct = normalize_numeric(item.get("view_return_pct"))
        if view_return_pct is None:
            raise HTTPException(status_code=400, detail=f"La view para {ticker} no incluye view_return_pct.")

        row = np.zeros(len(tickers), dtype=float)
        row[ticker_index[ticker]] = 1.0
        p_rows.append(row)
        q_values.append(float(view_return_pct) / 100.0)
        views_used.append({"ticker": ticker, "view_return_pct": round(float(view_return_pct), 4)})

    return np.vstack(p_rows), np.array(q_values, dtype=float), views_used


def size_loadings(tickers: Sequence[str], metadata: dict[str, dict]) -> np.ndarray:
    """Calcula loadings de tamaño aproximados con market cap."""
    market_caps = np.array(
        [max(float(metadata.get(ticker, {}).get("market_cap") or 1.0), 1.0) for ticker in tickers],
        dtype=float,
    )
    return zscore(-np.log(market_caps))


def value_loadings(tickers: Sequence[str], metadata: dict[str, dict]) -> np.ndarray:
    """Calcula loadings de valor aproximados con dividend yield y trailing PE."""
    dividend_yields = []
    earnings_yields = []
    for ticker in tickers:
        meta = metadata.get(ticker, {})
        dividend_yields.append(float(meta.get("dividend_yield") or 0.0))
        trailing_pe = float(meta.get("trailing_pe") or 0.0)
        earnings_yields.append(0.0 if trailing_pe <= 0 else 1.0 / trailing_pe)
    dividend_score = zscore(np.array(dividend_yields, dtype=float))
    earnings_score = zscore(np.array(earnings_yields, dtype=float))
    return (dividend_score + earnings_score) / 2.0
