"""
markowitz.py - Optimizacion base para seleccion de portafolios FinPUC.

Implementacion con scipy.optimize (SLSQP):
  - compute_markowitz_portfolio: maximiza utilidad cuadratica mu'w - 0.5*gamma*w'Sigma*w
    (alineado con el solver academico del Informe 1, Seccion 3-4)
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


DEFAULT_MAX_WEIGHT = 0.40
TRADING_DAYS_PER_YEAR = 252
DEFAULT_SHRINKAGE = 0.20

# Gammas por perfil del solver academico (Entrega 2, Informe 1)
PROFILE_GAMMA = {
    "muy_conservador": 80.0,
    "conservador": 45.0,
    "neutro": 20.0,
    "arriesgado": 8.0,
    "muy_arriesgado": 3.0,
}

PROFILE_MAX_WEIGHT = {
    "muy_conservador": 0.05,
    "conservador": 0.07,
    "neutro": 0.10,
    "arriesgado": 0.15,
    "muy_arriesgado": 0.20,
}

PROFILE_MAX_VOL = {
    "muy_conservador": 0.08,
    "conservador": 0.12,
    "neutro": 0.18,
    "arriesgado": 0.28,
    "muy_arriesgado": 0.40,
}


def _annualize(
    daily_returns: np.ndarray,
    custom_ann_returns: Optional[np.ndarray] = None,
    shrinkage: float = DEFAULT_SHRINKAGE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convierte retornos diarios a retorno esperado y covarianza anualizados con shrinkage."""
    ann_returns = (
        np.array(custom_ann_returns, dtype=float)
        if custom_ann_returns is not None
        else daily_returns.mean(axis=0) * TRADING_DAYS_PER_YEAR
    )
    ann_cov = np.cov(daily_returns.T) * TRADING_DAYS_PER_YEAR
    if shrinkage > 0:
        ann_cov = (1.0 - shrinkage) * ann_cov + shrinkage * np.diag(np.diag(ann_cov))
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


def _neg_quadratic_utility(
    weights: np.ndarray,
    ann_returns: np.ndarray,
    ann_cov: np.ndarray,
    gamma: float,
) -> float:
    port_return = float(np.dot(weights, ann_returns))
    port_variance = float(weights @ ann_cov @ weights)
    return -(port_return - 0.5 * gamma * port_variance)


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
    profile: str = "neutro",
    max_weight: Optional[float] = None,
    gamma: Optional[float] = None,
    max_vol: Optional[float] = None,
) -> Dict:
    """Portafolio Markowitz: maximiza utilidad cuadratica mu'w - 0.5*gamma*w'Sigma*w
    con restricciones de presupuesto, no-short y cota de volatilidad.
    Alineado con el solver academico de Entrega 2."""
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
    _gamma = gamma if gamma is not None else PROFILE_GAMMA.get(str(profile), 20.0)
    _max_weight = max_weight if max_weight is not None else PROFILE_MAX_WEIGHT.get(str(profile), 0.10)
    _max_vol = max_vol if max_vol is not None else PROFILE_MAX_VOL.get(str(profile))
    upper = min(_max_weight, 1.0)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if _max_vol is not None:
        constraints.append({"type": "ineq", "fun": lambda w: _max_vol**2 - float(w @ ann_cov @ w)})
    bounds = [(0.0, upper)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _neg_quadratic_utility,
        w0,
        args=(ann_returns, ann_cov, _gamma),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 2000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, upper)
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
    max_weight: Optional[float] = None,
) -> Dict:
    """Portafolio de minima varianza global."""
    n_assets = len(tickers)
    if n_assets == 0:
        return {}
    if not _SCIPY:
        return _equal_weights_fallback(
            tickers, daily_returns, risk_free_rate, "minimum_variance_portfolio"
        )

    upper = min(max_weight if max_weight is not None else DEFAULT_MAX_WEIGHT, 1.0)
    _, ann_cov = _annualize(daily_returns)
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, upper)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _portfolio_variance,
        w0,
        args=(ann_cov,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 1000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, upper)
    weights /= weights.sum()
    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)


def maximum_return_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
    custom_ann_returns: Optional[np.ndarray] = None,
    max_weight: Optional[float] = None,
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

    upper = min(max_weight if max_weight is not None else DEFAULT_MAX_WEIGHT, 1.0)
    ann_returns, _ = _annualize(daily_returns, custom_ann_returns)
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, upper)] * n_assets
    w0 = np.ones(n_assets) / n_assets

    result = minimize(
        _neg_return,
        w0,
        args=(ann_returns,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 1000},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, upper)
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
    max_weight: Optional[float] = None,
    gmv_weights: Optional[np.ndarray] = None,
    max_return_weights: Optional[np.ndarray] = None,
    custom_ann_returns: Optional[np.ndarray] = None,
) -> List[Tuple[float, float]]:
    """Genera puntos de la frontera eficiente sobre el universo dado.
    
    Si se proveen gmv_weights y max_return_weights, se usan como extremos
    de la frontera en vez de recalcularlos, garantizando consistencia con
    los markers del grafico.
    
    Si se provee custom_ann_returns, se usa en vez de mean*252 (permite
    alinear con CAGR del endpoint)."""
    n_assets = len(tickers)
    if n_assets == 0 or not _SCIPY:
        return []

    upper = min(max_weight if max_weight is not None else DEFAULT_MAX_WEIGHT, 1.0)
    ann_returns, ann_cov = _annualize(daily_returns, custom_ann_returns)
    bounds = [(0.0, upper)] * n_assets

    if gmv_weights is not None and max_return_weights is not None:
        gmv_w = np.array(gmv_weights, dtype=float)
        max_w = np.array(max_return_weights, dtype=float)
    else:
        w0 = np.ones(n_assets) / n_assets
        constraints_budget = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        gmv = minimize(_portfolio_variance, w0, args=(ann_cov,), method="SLSQP",
                        bounds=bounds, constraints=constraints_budget,
                        options={"ftol": 1e-10, "maxiter": 1000})
        max_ret = minimize(_neg_return, w0, args=(ann_returns,), method="SLSQP",
                            bounds=bounds, constraints=constraints_budget,
                            options={"ftol": 1e-10, "maxiter": 1000})
        if not gmv.success:
            log.warning("GMV no convergio para frontera eficiente")
            return []
        gmv_w = np.clip(gmv.x, 0.0, upper)
        if gmv_w.sum() > 1e-10:
            gmv_w = gmv_w / gmv_w.sum()
        max_w = np.clip(max_ret.x if max_ret.success else gmv.x, 0.0, upper)
        if max_w.sum() > 1e-10:
            max_w = max_w / max_w.sum()

    gmv_return = float(np.dot(gmv_w, ann_returns))
    max_ret_return = float(np.dot(max_w, ann_returns))
    gmv_vol = float(np.sqrt(gmv_w @ ann_cov @ gmv_w))

    if max_ret_return <= gmv_return + 1e-6:
        return [(round(gmv_vol * 100, 4), round(gmv_return * 100, 4))]

    w0 = np.ones(n_assets) / n_assets
    frontier: List[Tuple[float, float]] = []
    for target_return in np.linspace(gmv_return, max_ret_return, n_points):
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {"type": "eq",
             "fun": lambda w, target=target_return: float(np.dot(w, ann_returns)) - target},
        ]
        result = minimize(
            _portfolio_variance, gmv_w.copy(), args=(ann_cov,),
            method="SLSQP", bounds=bounds, constraints=constraints,
            options={"ftol": 1e-10, "maxiter": 2000},
        )
        if not result.success:
            continue
        w = np.clip(result.x, 0.0, upper)
        if w.sum() > 1e-10:
            w = w / w.sum()
        vol = float(np.sqrt(w @ ann_cov @ w))
        ret = float(np.dot(w, ann_returns))
        frontier.append((round(vol * 100, 4), round(ret * 100, 4)))

    frontier.sort(key=lambda point: point[0])
    return frontier
