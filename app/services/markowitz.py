"""
markowitz.py — Optimización de Markowitz para selección de portafolios.

Implementa:
  - Portafolio de máximo Sharpe ratio (maximize_sharpe)
  - Portafolio de mínima varianza (minimum_variance_portfolio)
  - Estadísticas básicas de portafolio

Si scipy no está disponible, cae a pesos iguales.
"""
import logging
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

try:
    from scipy.optimize import minimize
    _SCIPY = True
except ImportError:  # pragma: no cover
    _SCIPY = False
    log.warning("scipy no disponible — Markowitz usará pesos iguales como fallback")


# ============================================================
# Public API
# ============================================================

def compute_markowitz_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """
    Portafolio de máximo Sharpe ratio.

    Args:
        tickers: Lista de nombres/tickers (longitud N).
        daily_returns: Matriz (T x N) de retornos diarios.
        risk_free_rate: Tasa libre de riesgo anualizada.

    Returns:
        {weights, expected_return, volatility, sharpe_ratio, tickers}
    """
    n = len(tickers)
    if n == 0:
        return {}

    if daily_returns.ndim == 1 or daily_returns.shape[1] == 1:
        return _portfolio_stats(np.array([1.0]), daily_returns.reshape(-1, 1), risk_free_rate, tickers)

    if not _SCIPY:
        weights = np.ones(n) / n
        return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)

    ann_returns = daily_returns.mean(axis=0) * 252
    ann_cov = np.cov(daily_returns.T) * 252

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(np.dot(w, ann_returns))
        vol = float(np.sqrt(w @ ann_cov @ w))
        if vol < 1e-10:
            return 1e10
        return -(ret - risk_free_rate) / vol

    x0 = np.ones(n) / n
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    result = minimize(
        neg_sharpe, x0, method="SLSQP",
        bounds=bounds, constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    weights = result.x if result.success else x0
    weights = np.maximum(weights, 0.0)
    weights /= weights.sum()

    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)


def minimum_variance_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """Portafolio de mínima varianza (perfil conservador)."""
    n = len(tickers)
    if n == 0:
        return {}

    if daily_returns.ndim == 1 or daily_returns.shape[1] == 1:
        return _portfolio_stats(np.array([1.0]), daily_returns.reshape(-1, 1), risk_free_rate, tickers)

    if not _SCIPY:
        weights = np.ones(n) / n
        return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)

    ann_cov = np.cov(daily_returns.T) * 252

    def portfolio_variance(w: np.ndarray) -> float:
        return float(w @ ann_cov @ w)

    x0 = np.ones(n) / n
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    result = minimize(
        portfolio_variance, x0, method="SLSQP",
        bounds=bounds, constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    weights = result.x if result.success else x0
    weights = np.maximum(weights, 0.0)
    weights /= weights.sum()

    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)


# ============================================================
# Helpers
# ============================================================

def _portfolio_stats(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    tickers: Optional[List[str]] = None,
) -> Dict:
    """Calcula retorno esperado, volatilidad y Sharpe de un portafolio."""
    if daily_returns.ndim == 1:
        daily_returns = daily_returns.reshape(-1, 1)

    ann_returns = daily_returns.mean(axis=0) * 252

    if daily_returns.shape[1] > 1:
        ann_cov = np.cov(daily_returns.T) * 252
        port_vol = float(np.sqrt(weights @ ann_cov @ weights))
    else:
        port_vol = float(daily_returns.std(axis=0)[0] * np.sqrt(252))

    port_return = float(np.dot(weights, ann_returns))
    sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 1e-10 else 0.0

    out: Dict = {
        "expected_return": port_return,
        "volatility": port_vol,
        "sharpe_ratio": sharpe,
        "weights": weights.tolist(),
    }
    if tickers:
        out["tickers"] = tickers
    return out
