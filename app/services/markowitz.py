"""
markowitz.py - Optimizacion base para seleccion de portafolios FinPUC.

Implementacion con scipy.optimize (SLSQP):
  - compute_markowitz_portfolio: maximiza Sharpe
  - minimum_variance_portfolio: minimiza varianza
  - maximum_return_portfolio: maximiza retorno esperado
  - compute_efficient_frontier: genera puntos de la frontera eficiente
  - compute_cvar: calcula CVaR historico sobre retornos de calibracion

Si scipy no esta disponible, las funciones hacen fallback a pesos iguales.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

try:
    from scipy.optimize import minimize

    _SCIPY = True
except ImportError:  # pragma: no cover
    _SCIPY = False
    log.warning("scipy no disponible; se usara fallback a pesos iguales")


MAX_WEIGHT = 0.40
TRADING_DAYS_PER_YEAR = 252


def _annualize(
    daily_returns: np.ndarray,
    custom_ann_returns: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convierte retornos diarios a retorno esperado y covarianza anualizados."""
    ann_returns = (
        np.array(custom_ann_returns, dtype=float)
        if custom_ann_returns is not None
        else daily_returns.mean(axis=0) * TRADING_DAYS_PER_YEAR
    )
    ann_cov = np.cov(daily_returns.T) * TRADING_DAYS_PER_YEAR
    ann_cov += np.eye(len(ann_returns)) * 1e-8
    return ann_returns, ann_cov


def _portfolio_stats(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    tickers: Optional[List[str]] = None,
    ann_returns_override: Optional[np.ndarray] = None,
) -> Dict:
    """Calcula metricas anualizadas del portafolio."""
    if daily_returns.ndim == 1:
        daily_returns = daily_returns.reshape(-1, 1)

    ann_returns = (
        np.array(ann_returns_override, dtype=float)
        if ann_returns_override is not None
        else daily_returns.mean(axis=0) * TRADING_DAYS_PER_YEAR
    )

    if daily_returns.shape[1] > 1:
        ann_cov = np.cov(daily_returns.T) * TRADING_DAYS_PER_YEAR
        port_vol = float(np.sqrt(weights @ ann_cov @ weights))
    else:
        port_vol = float(daily_returns.std(axis=0)[0] * np.sqrt(TRADING_DAYS_PER_YEAR))

    port_return = float(np.dot(weights, ann_returns))
    sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 1e-10 else 0.0

    response: Dict = {
        "expected_return": port_return,
        "volatility": port_vol,
        "sharpe_ratio": sharpe,
        "weights": weights.tolist(),
    }
    if tickers:
        response["tickers"] = tickers
    return response


def _equal_weights_fallback(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float,
    label: str,
    ann_returns_override: Optional[np.ndarray] = None,
) -> Dict:
    """Fallback a pesos iguales cuando scipy no esta disponible."""
    n_assets = len(tickers)
    weights = np.ones(n_assets) / n_assets
    log.warning("Fallback a pesos iguales en %s", label)
    return _portfolio_stats(
        weights,
        daily_returns,
        risk_free_rate,
        tickers,
        ann_returns_override=ann_returns_override,
    )


def _neg_sharpe(
    weights: np.ndarray,
    ann_returns: np.ndarray,
    ann_cov: np.ndarray,
    risk_free_rate: float,
) -> float:
    port_return = float(np.dot(weights, ann_returns))
    port_vol = float(np.sqrt(weights @ ann_cov @ weights))
    if port_vol < 1e-10:
        return 1e10
    return -(port_return - risk_free_rate) / port_vol


def _portfolio_variance(weights: np.ndarray, ann_cov: np.ndarray) -> float:
    return float(weights @ ann_cov @ weights)


def _neg_return(weights: np.ndarray, ann_returns: np.ndarray) -> float:
    return -float(np.dot(weights, ann_returns))


def compute_cvar(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    confidence_level: float = 0.95,
) -> float:
    """
    CVaR historico anualizado.

    Interpreta el peor (1-beta)% de los dias como cola de perdida.
    """
    portfolio_returns = daily_returns @ weights
    threshold = np.percentile(portfolio_returns, (1 - confidence_level) * 100)
    tail = portfolio_returns[portfolio_returns <= threshold]
    if len(tail) == 0:
        return 0.0
    cvar_daily = -float(tail.mean())
    return round(float(cvar_daily * np.sqrt(TRADING_DAYS_PER_YEAR)), 4)


def compute_markowitz_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    custom_ann_returns: Optional[np.ndarray] = None,
) -> Dict:
    """Portafolio de maximo Sharpe con restricciones de presupuesto y no-short."""
    n_assets = len(tickers)
    if n_assets == 0:
        return {}
    if not _SCIPY:
        return _equal_weights_fallback(
            tickers,
            daily_returns,
            risk_free_rate,
            "compute_markowitz_portfolio",
            ann_returns_override=custom_ann_returns,
        )

    ann_returns, ann_cov = _annualize(daily_returns, custom_ann_returns)
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, MAX_WEIGHT)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _neg_sharpe,
        w0,
        args=(ann_returns, ann_cov, risk_free_rate),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, 1.0)
    weights /= weights.sum()
    return _portfolio_stats(
        weights,
        daily_returns,
        risk_free_rate,
        tickers,
        ann_returns_override=ann_returns,
    )


def minimum_variance_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """Portafolio de minima varianza global."""
    n_assets = len(tickers)
    if n_assets == 0:
        return {}
    if not _SCIPY:
        return _equal_weights_fallback(
            tickers, daily_returns, risk_free_rate, "minimum_variance_portfolio"
        )

    _, ann_cov = _annualize(daily_returns)
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, MAX_WEIGHT)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _portfolio_variance,
        w0,
        args=(ann_cov,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, 1.0)
    weights /= weights.sum()
    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)


def maximum_return_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    custom_ann_returns: Optional[np.ndarray] = None,
) -> Dict:
    """Portafolio que maximiza el retorno esperado sujeto a las mismas restricciones."""
    n_assets = len(tickers)
    if n_assets == 0:
        return {}
    if not _SCIPY:
        return _equal_weights_fallback(
            tickers,
            daily_returns,
            risk_free_rate,
            "maximum_return_portfolio",
            ann_returns_override=custom_ann_returns,
        )

    ann_returns, _ = _annualize(daily_returns, custom_ann_returns)
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, MAX_WEIGHT)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _neg_return,
        w0,
        args=(ann_returns,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, 1.0)
    weights /= weights.sum()
    return _portfolio_stats(
        weights,
        daily_returns,
        risk_free_rate,
        tickers,
        ann_returns_override=ann_returns,
    )


def compute_efficient_frontier(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    n_points: int = 25,
) -> List[Tuple[float, float]]:
    """Genera puntos de la frontera eficiente sobre el universo dado."""
    n_assets = len(tickers)
    if n_assets == 0 or not _SCIPY:
        return []

    ann_returns, ann_cov = _annualize(daily_returns)
    bounds = [(0.0, MAX_WEIGHT)] * n_assets
    w0 = np.ones(n_assets) / n_assets
    constraints_budget = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

    gmv = minimize(
        _portfolio_variance,
        w0,
        args=(ann_cov,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints_budget,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    max_ret = minimize(
        _neg_return,
        w0,
        args=(ann_returns,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints_budget,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    if not gmv.success or not max_ret.success:
        return []

    gmv_weights = np.clip(gmv.x, 0.0, 1.0)
    gmv_weights /= gmv_weights.sum()
    max_weights = np.clip(max_ret.x, 0.0, 1.0)
    max_weights /= max_weights.sum()

    min_return = float(np.dot(gmv_weights, ann_returns))
    max_return = float(np.dot(max_weights, ann_returns))
    if max_return <= min_return:
        return []

    frontier: List[Tuple[float, float]] = []
    for target_return in np.linspace(min_return, max_return, n_points):
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {
                "type": "eq",
                "fun": lambda w, target=target_return: float(np.dot(w, ann_returns)) - target,
            },
        ]
        result = minimize(
            _portfolio_variance,
            w0,
            args=(ann_cov,),
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 1000},
        )
        if not result.success:
            continue

        weights = np.clip(result.x, 0.0, 1.0)
        weights /= weights.sum()
        volatility = float(np.sqrt(weights @ ann_cov @ weights))
        expected_return = float(np.dot(weights, ann_returns))
        frontier.append((round(volatility * 100, 4), round(expected_return * 100, 4)))

    frontier.sort(key=lambda point: point[0])
    return frontier
