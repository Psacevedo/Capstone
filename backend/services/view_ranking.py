"""
view_ranking.py — Ranking de views BL por mediana de mejoras P4 vs Markowitz.

Score_view^mediana = mediana_{i∈I} ( (Score_BL,i - Score_MK,i) / |Score_MK,i| )

I = {sin_pandemia, con_pandemia} × {5 perfiles}
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
import sqlite3

import numpy as np

from ..services.markowitz import (
    compute_markowitz_portfolio,
)
from ..services.simulation import simulate_client_behavior
from ..services.bl_views import build_bl_view
from ..services.return_estimators import historical_ann_returns
from ..utils.candidate_selection import select_candidates, fetch_price_series, align_return_matrix
from ..utils.helpers import portfolio_metrics

log = logging.getLogger(__name__)

DEFAULT_RISK_FREE_RATE = 0.02
DEFAULT_COMPANY_MONTHLY_FEE_RATE = 0.005
BL_VIEW_FOR_RECOMMEND = "momentum_top20_6m"
MIN_OPTIMIZER_UNIVERSE = 20
MAX_OPTIMIZER_UNIVERSE = 80
TRADING_DAYS = 252

RISK_PROFILES = {
    "muy_conservador": {"alpha_p": 0.00, "label": "Muy conservador", "gamma": 80.0, "max_weight": 0.05, "n_assets": 40, "candidate_pool_max": 50, "candidate_pool_default": 40, "max_vol": 0.08, "sectors": ["Utilities", "Consumer Defensive"], "cvar_level": 0.99, "dividend_bias": True, "max_sector_fraction": 0.30},
    "conservador":     {"alpha_p": 0.05, "label": "Conservador",     "gamma": 45.0, "max_weight": 0.07, "n_assets": 60, "candidate_pool_max": 80, "candidate_pool_default": 65, "max_vol": 0.12, "sectors": None, "cvar_level": 0.95, "dividend_bias": True, "max_sector_fraction": 0.30},
    "neutro":          {"alpha_p": 0.10, "label": "Neutro",          "gamma": 20.0, "max_weight": 0.10, "n_assets": 80, "candidate_pool_max": 120, "candidate_pool_default": 100, "max_vol": 0.18, "sectors": None, "cvar_level": 0.90, "dividend_bias": False, "max_sector_fraction": 0.25},
    "arriesgado":      {"alpha_p": 0.15, "label": "Arriesgado",      "gamma": 8.0,  "max_weight": 0.15, "n_assets": 100, "candidate_pool_max": 150, "candidate_pool_default": 125, "max_vol": 0.28, "sectors": None, "cvar_level": 0.85, "dividend_bias": False, "max_sector_fraction": 0.30},
    "muy_arriesgado":  {"alpha_p": 0.20, "label": "Muy arriesgado",  "gamma": 3.0,  "max_weight": 0.20, "n_assets": 120, "candidate_pool_max": None, "candidate_pool_default": None, "max_vol": 0.40, "sectors": None, "cvar_level": 0.80, "dividend_bias": False, "max_sector_fraction": 0.35},
}

PROFILES_ORDER = ["muy_conservador", "conservador", "neutro", "arriesgado", "muy_arriesgado"]


def resolve_candidate_pool_size(profile_cfg: Dict, requested: Optional[int], f5_total_size: int) -> int:
    if requested is not None:
        pool_max = profile_cfg.get("candidate_pool_max")
        if pool_max is not None:
            return max(10, min(requested, pool_max))
        return max(10, min(requested, f5_total_size))
    default = profile_cfg.get("candidate_pool_default")
    pool_max = profile_cfg.get("candidate_pool_max")
    if default is not None:
        if pool_max is not None:
            return min(default, pool_max, f5_total_size)
        return min(default, f5_total_size)
    return f5_total_size


def optimizer_universe_size(candidate_pool_size: int, target_holdings: int) -> int:
    return min(candidate_pool_size, max(MIN_OPTIMIZER_UNIVERSE, target_holdings * 6), MAX_OPTIMIZER_UNIVERSE)


def _build_bl_returns(tickers, returns_matrix, metadata):
    """Construye retornos BL manualmente."""
    try:
        p, q, confidence, info = build_bl_view(BL_VIEW_FOR_RECOMMEND, tickers, returns_matrix, metadata)
    except Exception:
        return historical_ann_returns(tickers, metadata, returns_matrix)

    n = len(tickers)
    tau = 0.05
    mu_prior = returns_matrix.mean(axis=0)
    sigma = np.cov(returns_matrix.T)
    diag = np.diag(np.diag(sigma))
    sigma = (1.0 - 0.20) * sigma + 0.20 * diag
    sigma += np.eye(n) * 1e-10

    omega = (1.0 - confidence) / confidence * np.diag(p @ sigma @ p.T) if p.shape[0] > 0 else np.eye(1) * 0.01
    omega = np.atleast_2d(np.diag(omega)) if omega.ndim == 1 else omega
    omega += np.eye(omega.shape[0]) * 1e-10

    try:
        sigma_p = p @ sigma @ p.T
        inv_term = np.linalg.inv(sigma_p + omega)
        mu_bl = mu_prior + tau * sigma @ p.T @ inv_term @ (q.T - p @ mu_prior)
        mu_bl = np.clip(mu_bl, -0.5, 0.5)
    except Exception:
        return historical_ann_returns(tickers, metadata, returns_matrix)

    return mu_bl * TRADING_DAYS


def _try_select_candidates(db, profile_cfg):
    """Prueba select_candidates, retorna ([], 0) si falla o da 0 candidatos."""
    try:
        c, t = select_candidates(db=db, profile_cfg=profile_cfg, candidate_pool_size=636, sector_filter=None)
        return c or [], t or 0
    except Exception:
        return [], 0


def compute_view_ranking(db: sqlite3.Connection) -> Dict:
    """Evalúa BL vs Markowitz para {sin_pandemia, con_pandemia} × {5 perfiles}."""
    all_improvements: List[float] = []
    detail_rows: List[Dict] = []

    for profile_key in PROFILES_ORDER:
        base_cfg = RISK_PROFILES[profile_key]

        # Intentar con filtros originales
        candidates, total_count = _try_select_candidates(db, base_cfg)
        if not candidates:
            # Fallback: relajar max_vol y sectores
            relaxed = dict(base_cfg)
            relaxed["max_vol"] = None
            relaxed["sectors"] = None
            candidates, total_count = _try_select_candidates(db, relaxed)
            if not candidates:
                log.warning(f"No candidates for {profile_key} even relaxed")
                continue
            profile_cfg = relaxed
        else:
            profile_cfg = base_cfg

        pool_size = resolve_candidate_pool_size(profile_cfg, None, total_count)
        if not candidates:
            log.warning(f"No candidates for {profile_key}")
            continue

        metadata = {c["ticker"]: c for c in candidates}
        tickers_list = [c["ticker"] for c in candidates]

        # Dos escenarios: full data (con pandemia) y pre-pandemia
        for scenario_key, split_end in [("Con pandemia", None), ("Sin pandemia", "2020-02-01")]:
            try:
                series = fetch_price_series(db, tickers_list, "2004-01-01", split_end or "2025-01-01")
                valid_tickers, returns_matrix = align_return_matrix(series, tickers_list)
            except Exception as e:
                log.warning(f"Data error {profile_key}/{scenario_key}: {e}")
                continue

            if len(valid_tickers) < 10:
                continue

            opt_size = optimizer_universe_size(len(valid_tickers), profile_cfg["n_assets"])
            vt = valid_tickers[:opt_size]
            rm = returns_matrix[:, :opt_size] if returns_matrix.shape[1] >= opt_size else returns_matrix

            # Retornos históricos (Markowitz)
            ann_hist = historical_ann_returns(vt, metadata, rm)

            # Retornos BL
            ann_bl = _build_bl_returns(vt, rm, metadata)

            gamma = profile_cfg["gamma"]
            max_w = profile_cfg["max_weight"]
            alpha_p = profile_cfg["alpha_p"]

            def _score(mu_vec):
                try:
                    w = compute_markowitz_portfolio(mu_vec, np.cov(rm.T), gamma, max_w)
                except Exception:
                    w = np.ones(len(mu_vec)) / len(mu_vec)
                metrics = portfolio_metrics(w, rm, mu_vec, DEFAULT_RISK_FREE_RATE)
                ann_ret = metrics["expected_return_pct"] / 100.0
                ann_vol = max(metrics["volatility_pct"] / 100.0, 1e-6)
                sim = simulate_client_behavior(
                    initial_capital=1000.0, expected_return=ann_ret, volatility=ann_vol,
                    max_loss_pct=alpha_p, years=5, commission_rate=0.0,
                    n_simulations=2000, rebalance_freq_weeks=1,
                    abandonment_policy="v1_plus",
                    company_monthly_fee_rate=DEFAULT_COMPANY_MONTHLY_FEE_RATE,
                )
                return sim["score_p4"], sim["final_capital_mean"], sim["total_commissions_mean"], \
                       sim["withdrawal_rate"], metrics.get("sharpe_ratio", 0.0)

            mk_score, mk_w, mk_u, mk_r, mk_s = _score(ann_hist)
            bl_score, bl_w, bl_u, bl_r, bl_s = _score(ann_bl)

            denom = abs(mk_score) if abs(mk_score) > 1e-9 else 1.0
            improvement = (bl_score - mk_score) / denom
            all_improvements.append(improvement)

            detail_rows.append({
                "scenario": scenario_key, "perfil": profile_cfg["label"],
                "mk_score": round(mk_score, 2), "bl_score": round(bl_score, 2),
                "mejora_pct": round(improvement * 100, 2),
                "mk_wealth": round(mk_w, 2), "bl_wealth": round(bl_w, 2),
                "mk_utility": round(mk_u, 2), "bl_utility": round(bl_u, 2),
                "mk_retiro": round(mk_r, 2), "bl_retiro": round(bl_r, 2),
                "mk_sharpe": round(mk_s, 4), "bl_sharpe": round(bl_s, 4),
            })

    improvements = np.array(all_improvements)
    return {
        "view": BL_VIEW_FOR_RECOMMEND,
        "view_label": "Momentum Top20 6M",
        "median_improvement_pct": round(float(np.median(improvements)) * 100, 2) if len(improvements) > 0 else 0.0,
        "mean_improvement_pct": round(float(np.mean(improvements)) * 100, 2) if len(improvements) > 0 else 0.0,
        "n_combinations": len(all_improvements),
        "detail": detail_rows,
        "resumen": {
            "mejora_mediana": f"{round(float(np.median(improvements)) * 100, 2)}%" if len(improvements) > 0 else "N/A",
            "mejora_promedio": f"{round(float(np.mean(improvements)) * 100, 2)}%" if len(improvements) > 0 else "N/A",
            "combinaciones_evaluadas": len(all_improvements),
        },
    }
