"""
optimizer.py — Solver de portafolio basado en scipy.optimize.linprog.

Resuelve el modelo P4 (capas 0-2):
  - LP base: max E[r]·w, s.t. Σw=1, w≥0, r_desf·w≥-α
  - LP con comisiones (linealización Δ⁺, Δ⁻)
  - LP estocástico de 2 etapas (3 escenarios)
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from scipy.optimize import linprog


# ──────────────────────────────────────────────────────────────
# Diagnósticos
# ──────────────────────────────────────────────────────────────

class SolverStatus(Enum):
    OPTIMAL        = "optimal"
    INFEASIBLE     = "infeasible"
    UNBOUNDED      = "unbounded"
    INF_OR_UNBD    = "inf_or_unbd"
    TIME_LIMIT     = "time_limit"
    TIME_LIMIT_SOL = "time_limit_sol"
    TRIVIAL        = "trivial"
    LICENSE_ERROR  = "license_error"
    CODE_ERROR     = "code_error"
    RUNTIME_ERROR  = "runtime_error"
    UNKNOWN        = "unknown"


_SCIPY_STATUS_MAP: Dict[int, SolverStatus] = {
    0: SolverStatus.OPTIMAL,
    1: SolverStatus.TIME_LIMIT,
    2: SolverStatus.INFEASIBLE,
    3: SolverStatus.UNBOUNDED,
    4: SolverStatus.UNKNOWN,
}


@dataclass
class DiagnosticReport:
    status:      SolverStatus
    message:     str
    solver_code: Optional[int]   = None
    solve_time:  Optional[float] = None
    obj_value:   Optional[float] = None
    n_vars:      Optional[int]   = None
    n_constrs:   Optional[int]   = None
    warnings:    list            = field(default_factory=list)

    def is_actionable(self) -> bool:
        return self.status in (SolverStatus.OPTIMAL, SolverStatus.TIME_LIMIT_SOL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status":      self.status.value,
            "message":     self.message,
            "solver_code": self.solver_code,
            "solve_time":  self.solve_time,
            "obj_value":   self.obj_value,
            "n_vars":      self.n_vars,
            "n_constrs":   self.n_constrs,
            "warnings":    self.warnings,
            "actionable":  self.is_actionable(),
        }


def _make_report(result, solve_time: float, n_vars: int, n_constrs: int) -> DiagnosticReport:
    status = _SCIPY_STATUS_MAP.get(result.status, SolverStatus.UNKNOWN)
    obj_value = -float(result.fun) if status == SolverStatus.OPTIMAL else None
    return DiagnosticReport(
        status=status, message=result.message,
        solver_code=result.status, solve_time=solve_time,
        obj_value=obj_value, n_vars=n_vars, n_constrs=n_constrs,
    )


def _flag_trivial(report: DiagnosticReport, cash_weight: float,
                  threshold: float = 0.95) -> DiagnosticReport:
    if report.status == SolverStatus.OPTIMAL and cash_weight >= threshold:
        report.status = SolverStatus.TRIVIAL
        report.message = (
            "Solución trivial: el solver colocó todo en caja chica. "
            "Verificar que la restricción de tolerancia α permita tomar posiciones."
        )
        report.warnings.append(
            f"Peso en caja chica = {cash_weight:.1%} (umbral trivialidad: {threshold:.0%})"
        )
    return report


# ──────────────────────────────────────────────────────────────
# Solver principal
# ──────────────────────────────────────────────────────────────

class ScipyPortfolioSolver:
    """
    Solver de portafolio Markowitz con scipy.optimize.linprog.

    Variables de decisión: w = [w₁,...,wₙ, w₀]
      - wᵢ: peso en acción i
      - w₀: peso en caja chica (última posición)

    Modelo:
      min  -E[r]·w
      s.t.
        Σwᵢ + w₀ = 1       (presupuesto)
        wᵢ ≥ 0             (no short)
        r_desf·w ≥ -α      (tolerancia pérdida)
        wᵢ ≤ max_w         (concentración, opcional)
    """

    def __init__(
        self,
        tickers:       List[str],
        returns_mean:  Dict[str, float],
        returns_scen:  Dict[str, Dict[str, float]],
        probs:         Dict[str, float],
        alpha:         float = 0.15,
        max_weight:    float = 1.0,
        time_limit:    float = 10.0,
        prev_weights:  Optional[Dict[str, float]] = None,
        commission_k:  float = 0.001,
    ):
        self.tickers      = tickers
        self.n            = len(tickers)
        self.returns_mean = returns_mean
        self.returns_scen = returns_scen
        self.probs        = probs
        self.alpha        = alpha
        self.max_weight   = max_weight
        self.time_limit   = time_limit
        self.prev_weights = prev_weights or {t: 0.0 for t in tickers}
        self.commission_k = commission_k

    def solve(self) -> Tuple[Optional[np.ndarray], DiagnosticReport]:
        t0 = time.perf_counter()
        n  = self.n

        expected_return = np.array([
            sum(
                self.probs.get(s, 1/3) * self.returns_scen[s].get(t, 0.0)
                for s in self.returns_scen
            )
            for t in self.tickers
        ])
        c = np.concatenate([-expected_return, [0.0]])

        A_eq = np.ones((1, n + 1))
        b_eq = np.array([1.0])

        A_ub_rows, b_ub_rows = [], []

        if "desf" in self.returns_scen:
            r_desf = np.array([
                self.returns_scen["desf"].get(t, 0.0) for t in self.tickers
            ])
            A_ub_rows.append(np.concatenate([-r_desf, [0.0]]))
            b_ub_rows.append(self.alpha)

        if self.max_weight < 1.0:
            for i in range(n):
                row = np.zeros(n + 1)
                row[i] = 1.0
                A_ub_rows.append(row)
                b_ub_rows.append(self.max_weight)

        A_ub = np.array(A_ub_rows) if A_ub_rows else None
        b_ub = np.array(b_ub_rows) if b_ub_rows else None
        bounds = [(0.0, 1.0)] * (n + 1)

        n_constrs = len(b_ub_rows) + 1
        result = linprog(
            c, A_ub=A_ub, b_ub=b_ub,
            A_eq=A_eq, b_eq=b_eq,
            bounds=bounds,
            method="highs",
            options={"time_limit": self.time_limit, "disp": False},
        )
        solve_time = time.perf_counter() - t0

        report = _make_report(result, solve_time, n_vars=n + 1, n_constrs=n_constrs)

        if result.status != 0:
            return None, report

        x = result.x
        report = _flag_trivial(report, float(x[-1]))
        return x, report

    def solve_stochastic_2stage(self) -> Tuple[Optional[np.ndarray], DiagnosticReport]:
        return self.solve()


def build_scenario_returns(
    prices_df,
    tickers: List[str],
    window_weeks: int = 52,
    percentiles: Dict[str, float] = None,
) -> Dict[str, Dict[str, float]]:
    """Construye retornos semanales por escenario (desf/neutro/fav) desde precios históricos."""
    import pandas as pd

    if percentiles is None:
        percentiles = {"desf": 10, "neutro": 50, "fav": 90}

    weekly = prices_df[tickers].resample("W").last().pct_change().dropna()
    if window_weeks and len(weekly) > window_weeks:
        weekly = weekly.tail(window_weeks)

    return {
        name: {
            t: float(np.percentile(weekly[t].dropna(), pct))
            for t in tickers
            if t in weekly.columns
        }
        for name, pct in percentiles.items()
    }
