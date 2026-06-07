"""
helpers.py — Funciones utilitarias comunes para portfolio.py
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def get_split_dates() -> Dict[str, str]:
    """Calcula las fechas de split para calibración y validación."""
    today = date.today()
    validation_end = today
    validation_start = today.replace(year=today.year - 2)
    calibration_end = validation_start - timedelta(days=1)
    calibration_start = calibration_end.replace(year=calibration_end.year - 8)
    return {
        "calibration_start": calibration_start.isoformat(),
        "calibration_end": calibration_end.isoformat(),
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
    }


def daily_returns(closes: List[float]) -> np.ndarray:
    """Calcula retornos diarios simples a partir de precios."""
    prices = np.array(closes, dtype=float)
    return np.diff(prices) / prices[:-1]


def closes_from_series(series_map: Dict[str, List[Tuple[str, float]]]) -> Dict[str, List[float]]:
    """Extrae precios de cierre de serie de (fecha, precio)."""
    return {ticker: [close for _, close in rows] for ticker, rows in series_map.items()}


def zscore(values: np.ndarray) -> np.ndarray:
    """Normaliza un array al rango [-inf, inf] con media 0 y std 1."""
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std < 1e-12:
        return np.zeros_like(values)
    return (values - mean) / std


def normalize_numeric(value, default=None):
    """Convierte un valor a float, devolviendo default si falla."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def format_parameter_value(value, unit: str) -> str:
    """Formatea un valor de parámetro para display."""
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit.startswith("%"):
            return f"{round(value, 4)} {unit}".strip()
        return str(round(value, 6))
    return str(value)


def portfolio_metrics(
    weights: np.ndarray,
    returns_matrix: np.ndarray,
    ann_returns_override: np.ndarray,
    risk_free_rate: float,
) -> Dict[str, float]:
    """Calcula métricas de portafolio: retorno esperado, volatilidad, Sharpe."""
    ann_cov = np.cov(returns_matrix.T) * 252 if returns_matrix.shape[1] > 1 else np.array([[returns_matrix.var() * 252]])
    ann_cov += np.eye(len(weights)) * 1e-8
    expected_return = float(np.dot(weights, ann_returns_override))
    volatility = float(np.sqrt(weights @ ann_cov @ weights))
    sharpe = (expected_return - risk_free_rate) / volatility if volatility > 1e-10 else 0.0
    return {
        "expected_return_pct": round(expected_return * 100, 2),
        "volatility_pct": round(volatility * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
    }


def trim_portfolio(
    tickers: List[str],
    weights: Sequence[float],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    target_holdings: int,
    renormalize: bool = True,
) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    """Recorta portafolio a N holdings manteniendo los mayores pesos."""
    weights_arr = np.array(weights, dtype=float)
    ranked = np.argsort(weights_arr)[::-1]
    selected = [idx for idx in ranked if weights_arr[idx] > 0][:target_holdings]
    if not selected:
        selected = list(ranked[:target_holdings])

    trimmed_weights = weights_arr[selected]
    if renormalize and trimmed_weights.sum() > 0:
        trimmed_weights = trimmed_weights / trimmed_weights.sum()

    trimmed_tickers = [tickers[idx] for idx in selected]
    trimmed_returns = returns_matrix[:, selected]
    trimmed_ann_returns = ann_returns[selected]
    return trimmed_tickers, trimmed_weights, trimmed_returns, trimmed_ann_returns
