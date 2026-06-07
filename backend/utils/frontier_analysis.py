"""
frontier_analysis.py — Análisis de frontera eficiente y puntos de Markowitz
"""
from typing import Dict, Optional, Sequence

import numpy as np

from ..services.markowitz import (
    compute_efficient_frontier,
    compute_markowitz_portfolio,
    maximum_return_portfolio,
    minimum_variance_portfolio,
)
from ..utils.helpers import portfolio_metrics


def frontier_metric_point(
    label: str,
    weights: Sequence[float],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    risk_free_rate: float,
) -> Optional[Dict]:
    """Calcula métricas para un punto en la frontera eficiente."""
    weights_arr = np.array(weights, dtype=float)
    if weights_arr.size != returns_matrix.shape[1] or weights_arr.sum() <= 0:
        return None
    weights_arr = np.clip(weights_arr, 0.0, 1.0)
    weights_arr = weights_arr / weights_arr.sum()
    point: Dict = portfolio_metrics(weights_arr, returns_matrix, ann_returns, risk_free_rate)
    point["label"] = label
    point["weights"] = weights_arr.tolist()
    return point


def build_frontier_markers(
    tickers: Sequence[str],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    risk_free_rate: float,
    selected_weights_full: Sequence[float],
    max_weight: Optional[float] = None,
) -> Dict[str, Dict]:
    """Construye puntos destacados en la frontera eficiente."""
    marker_specs = {
        "selected_point": ("Portafolio seleccionado", selected_weights_full),
    }

    try:
        gmv = minimum_variance_portfolio(list(tickers), returns_matrix, risk_free_rate, max_weight=max_weight)
        marker_specs["gmv_point"] = ("Minima varianza global", gmv.get("weights", []))
    except Exception:
        pass

    try:
        sharpe = compute_markowitz_portfolio(
            list(tickers),
            returns_matrix,
            risk_free_rate,
            custom_ann_returns=ann_returns,
        )
        marker_specs["max_sharpe_point"] = ("Markowitz maximo Sharpe", sharpe.get("weights", []))
    except Exception:
        pass

    try:
        max_ret = maximum_return_portfolio(
            list(tickers),
            returns_matrix,
            risk_free_rate,
            custom_ann_returns=ann_returns,
            max_weight=max_weight,
        )
        marker_specs["max_return_point"] = ("Maximo retorno", max_ret.get("weights", []))
    except Exception:
        pass

    markers: Dict[str, Dict] = {}
    for key, (label, weights) in marker_specs.items():
        point = frontier_metric_point(label, weights, returns_matrix, ann_returns, risk_free_rate)
        if point is not None:
            markers[key] = point
    return markers


def compute_efficient_frontier_points(
    tickers: Sequence[str],
    returns_matrix: np.ndarray,
    risk_free_rate: float,
    ann_returns: np.ndarray,
    profile_max_w: Optional[float],
    n_points: int = 25,
) -> list:
    """Computa puntos de la frontera eficiente."""
    try:
        gmv = minimum_variance_portfolio(list(tickers), returns_matrix, risk_free_rate, max_weight=profile_max_w)
        gmv_w = np.array(gmv.get("weights", []), dtype=float) if gmv else None
    except Exception:
        gmv_w = None

    try:
        max_ret = maximum_return_portfolio(
            list(tickers),
            returns_matrix,
            risk_free_rate,
            custom_ann_returns=ann_returns,
            max_weight=profile_max_w,
        )
        max_ret_w = np.array(max_ret.get("weights", []), dtype=float) if max_ret else None
    except Exception:
        max_ret_w = None

    frontier_points = compute_efficient_frontier(
        list(tickers),
        returns_matrix,
        risk_free_rate,
        n_points=n_points,
        max_weight=profile_max_w,
        gmv_weights=gmv_w,
        max_return_weights=max_ret_w,
        custom_ann_returns=ann_returns,
    )

    return [
        {"volatility_pct": vol, "expected_return_pct": ret}
        for vol, ret in frontier_points
    ]
