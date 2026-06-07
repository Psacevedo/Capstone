"""
hybrid_solver_utils.py — Utilidades para el solver híbrido y escenarios
"""
from typing import Dict, Sequence, Tuple

import numpy as np
from fastapi import HTTPException

from ..services.optimizer import ScipyPortfolioSolver
from ..services.portfolio_validator import PortfolioValidator
from ..utils.helpers import normalize_numeric


BL_Z_10_90 = 1.2815515655446004


def build_hybrid_scenarios(
    tickers: Sequence[str],
    ann_returns: np.ndarray,
    returns_matrix: np.ndarray,
) -> Dict[str, Dict[str, float]]:
    """Construye escenarios favorable/neutro/desfavorable para hybrid solver."""
    daily_vol = np.std(returns_matrix, axis=0)
    weekly_vol = daily_vol * np.sqrt(5)
    weekly_mu = np.array(
        [((1 + value) ** (1 / 52) - 1) if value > -0.999 else value / 52 for value in ann_returns],
        dtype=float,
    )
    return {
        "desf": {
            ticker: float(weekly_mu[idx] - BL_Z_10_90 * weekly_vol[idx])
            for idx, ticker in enumerate(tickers)
        },
        "neutro": {
            ticker: float(weekly_mu[idx])
            for idx, ticker in enumerate(tickers)
        },
        "fav": {
            ticker: float(weekly_mu[idx] + BL_Z_10_90 * weekly_vol[idx])
            for idx, ticker in enumerate(tickers)
        },
    }


def hybrid_probabilities(parameter_values: Dict[str, object]) -> Dict[str, float]:
    """Calcula probabilidades de escenarios para hybrid solver."""
    probs = {
        "desf": (normalize_numeric(parameter_values.get("prob_desfavorable_pct"), 25.0) or 25.0) / 100.0,
        "neutro": (normalize_numeric(parameter_values.get("prob_neutro_pct"), 50.0) or 50.0) / 100.0,
        "fav": (normalize_numeric(parameter_values.get("prob_favorable_pct"), 25.0) or 25.0) / 100.0,
    }
    total = sum(probs.values())
    if total <= 0:
        raise HTTPException(status_code=400, detail="Las probabilidades de escenarios deben sumar un valor positivo.")
    return {key: value / total for key, value in probs.items()}


def run_hybrid_solver(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    parameter_values: Dict[str, object],
    profile_key: str,
    alpha_p: float,
) -> Tuple[np.ndarray, float, Dict]:
    """Ejecuta el solver híbrido con escenarios estocásticos."""
    scenarios = build_hybrid_scenarios(tickers, ann_returns, returns_matrix)
    probabilities = hybrid_probabilities(parameter_values)
    commission_rate_pct = normalize_numeric(parameter_values.get("commission_rate_pct"), 1.0) or 1.0
    commission_weekly = (commission_rate_pct / 100.0) / 52.0

    returns_mean = {
        ticker: sum(probabilities[scenario] * scenarios[scenario][ticker] for scenario in probabilities)
        for ticker in tickers
    }
    solver = ScipyPortfolioSolver(
        tickers=list(tickers),
        returns_mean=returns_mean,
        returns_scen=scenarios,
        probs=probabilities,
        alpha=alpha_p,
        max_weight=0.40,
        time_limit=9.0,
        commission_k=commission_weekly,
    )
    solution, diagnostic = solver.solve_stochastic_2stage()
    if solution is None:
        raise HTTPException(
            status_code=400,
            detail=f"La metodologia hibrida no pudo resolver el problema: {diagnostic.message}",
        )

    validator = PortfolioValidator.from_scipy_solution(
        solution,
        list(tickers),
        returns_scenario=scenarios["desf"],
        profile=profile_key,
        commission_rate=commission_weekly,
        max_weight_single=0.40,
    ).validate()

    weights = np.array(solution[:-1], dtype=float)
    cash_weight = float(solution[-1])
    solver_details = {
        "solver_used": "solver.fallback.ScipyPortfolioSolver",
        "status": diagnostic.status.value,
        "message": diagnostic.message,
        "solve_time_s": diagnostic.solve_time,
        "obj_value": diagnostic.obj_value,
        "validation": validator.to_dict(),
        "scenario_probabilities": {
            "desfavorable_pct": round(probabilities["desf"] * 100, 2),
            "neutro_pct": round(probabilities["neutro"] * 100, 2),
            "favorable_pct": round(probabilities["fav"] * 100, 2),
        },
        "scenario_construction": "Escenarios por activo construidos desde mu_BL y volatilidad semanal p10/p50/p90.",
    }
    return weights, cash_weight, solver_details
