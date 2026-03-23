"""
markowitz.py — Optimización de Markowitz para selección de portafolios.

⚠️  MAQUETA: Esta es una maqueta sin funcionalidad real.
El grupo debe definir la implementación formal del modelo de Markowitz con Gurobi.

Estructura preparada para usar Gurobi como solver:
  - Portafolio de máximo Sharpe ratio (maximize_sharpe)
  - Portafolio de mínima varianza (minimum_variance_portfolio)
  - Estadísticas básicas de portafolio

Retorna valores placeholder/dummy hasta que sea implementado.
"""
import logging
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

try:
    import gurobipy as gp
    from gurobipy import GRB
    _GUROBI = True
except ImportError:  # pragma: no cover
    _GUROBI = False
    log.warning("Gurobi no disponible — usando pesos iguales como fallback")


# ============================================================
# Public API
# ============================================================

def compute_markowitz_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """
    ⚠️  MAQUETA: Portafolio de máximo Sharpe ratio.
    
    Retorna valores placeholder. A ser implementado por el grupo usando Gurobi.
    
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

    # Maqueta: retorna pesos iguales
    weights = np.ones(n) / n
    log.warning(f"MAQUETA: compute_markowitz_portfolio retorna pesos iguales (sin optimizar)")
    
    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)


def minimum_variance_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """
    ⚠️  MAQUETA: Portafolio de mínima varianza (perfil conservador).
    
    Retorna valores placeholder. A ser implementado por el grupo usando Gurobi.
    """
    n = len(tickers)
    if n == 0:
        return {}

    # Maqueta: retorna pesos iguales
    weights = np.ones(n) / n
    log.warning(f"MAQUETA: minimum_variance_portfolio retorna pesos iguales (sin optimizar)")
    
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
