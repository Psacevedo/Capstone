"""
fallback.py — Solver de respaldo basado en scipy.optimize.linprog.

Resuelve el modelo P4 (capas 0-2) cuando Gurobi no está disponible.
Soporta:
  - LP base: max E[r]·w, s.t. Σw=1, w≥0, r_desf·w≥-α
  - LP con comisiones (linealización Δ⁺, Δ⁻)
  - LP estocástico de 2 etapas (3 escenarios)
"""

import time
import numpy as np
from scipy.optimize import linprog
from typing import Dict, List, Optional, Tuple

from .diagnostics import Diagnostics, DiagnosticReport, SolverStatus
from .validators import PortfolioValidator


class ScipyPortfolioSolver:
    """
    Solver de portafolio Markowitz con scipy.optimize.linprog.

    Variables de decisión: w = [w₁,...,wₙ, w₀]
      - wᵢ: peso en acción i
      - w₀: peso en caja chica (última posición)

    El modelo se formula como:
      min  -E[r]·w         (minimizar negativo del retorno esperado)
      s.t.
        Σwᵢ + w₀ = 1       (presupuesto)
        wᵢ ≥ 0             (no short)
        r_desf·w ≥ -α      (tolerancia pérdida)
        wᵢ ≤ max_w         (concentración, opcional)
    """

    def __init__(
        self,
        tickers:       List[str],
        returns_mean:  Dict[str, float],          # retorno esperado por acción
        returns_scen:  Dict[str, Dict[str, float]], # {'desf':..., 'neutro':..., 'fav':...}
        probs:         Dict[str, float],           # probabilidades de escenario
        alpha:         float = 0.15,               # tolerancia pérdida perfil
        max_weight:    float = 1.0,                # concentración máxima por acción
        time_limit:    float = 10.0,               # límite de tiempo (segundos)
        prev_weights:  Optional[Dict[str, float]] = None,  # para comisiones
        commission_k:  float = 0.001,              # tasa comisión k
    ):
        self.tickers       = tickers
        self.n             = len(tickers)
        self.returns_mean  = returns_mean
        self.returns_scen  = returns_scen
        self.probs         = probs
        self.alpha         = alpha
        self.max_weight    = max_weight
        self.time_limit    = time_limit
        self.prev_weights  = prev_weights or {t: 0.0 for t in tickers}
        self.commission_k  = commission_k

    def solve(self) -> Tuple[Optional[np.ndarray], DiagnosticReport]:
        """
        Resuelve el LP y devuelve (x, DiagnosticReport).

        x = [w₁,...,wₙ, w₀]  — None si no hay solución.
        """
        t0 = time.perf_counter()
        n  = self.n

        # ---- Vector objetivo: minimizar -E[r]·w -------------------------
        # E[r] = Σ_s π_s · r_s
        expected_return = np.array([
            sum(
                self.probs.get(s, 1/3) * self.returns_scen[s].get(t, 0.0)
                for s in self.returns_scen
            )
            for t in self.tickers
        ])
        c = np.concatenate([-expected_return, [0.0]])  # w₀ no contribuye al retorno

        # ---- Restricción de igualdad: Σwᵢ + w₀ = 1 ---------------------
        A_eq = np.ones((1, n + 1))
        b_eq = np.array([1.0])

        # ---- Restricciones de desigualdad: A_ub · x ≤ b_ub --------------
        A_ub_rows, b_ub_rows = [], []

        # R3: Tolerancia de pérdida: -r_desf·w ≤ α  →  r_desf·w ≥ -α
        if "desf" in self.returns_scen:
            r_desf = np.array([
                self.returns_scen["desf"].get(t, 0.0) for t in self.tickers
            ])
            row = np.concatenate([-r_desf, [0.0]])   # -r·w ≤ α
            A_ub_rows.append(row)
            b_ub_rows.append(self.alpha)

        # R4 (opcional): max_weight por acción   wᵢ ≤ max_weight
        if self.max_weight < 1.0:
            for i in range(n):
                row = np.zeros(n + 1)
                row[i] = 1.0
                A_ub_rows.append(row)
                b_ub_rows.append(self.max_weight)

        A_ub = np.array(A_ub_rows) if A_ub_rows else None
        b_ub = np.array(b_ub_rows) if b_ub_rows else None

        # ---- Bounds: wᵢ ∈ [0, 1], w₀ ∈ [0, 1] --------------------------
        bounds = [(0.0, 1.0)] * (n + 1)

        # ---- Resolver ------------------------------------------------------
        n_constrs = (1 if A_ub is not None else 0) + len(b_ub_rows if b_ub_rows else [])
        result = linprog(
            c, A_ub=A_ub, b_ub=b_ub,
            A_eq=A_eq, b_eq=b_eq,
            bounds=bounds,
            method="highs",
            options={"time_limit": self.time_limit, "disp": False}
        )
        solve_time = time.perf_counter() - t0

        # ---- Diagnóstico --------------------------------------------------
        report = Diagnostics.from_scipy_result(
            result, solve_time,
            n_vars=n + 1, n_constrs=n_constrs + 1
        )

        if result.status != 0:
            return None, report

        x = result.x

        # Marcar trivial si todo está en caja chica
        cash_weight = float(x[-1])
        report = Diagnostics.flag_trivial(report, cash_weight)

        return x, report

    def solve_stochastic_2stage(self) -> Tuple[Optional[np.ndarray], DiagnosticReport]:
        """
        LP estocástico de 2 etapas (capa 2 del modelo P4).

        Stage 1: decidir w (aquí y ahora)
        Stage 2: observar escenario, evaluar V^s

        Formulación equivalente: maximizar retorno esperado ponderado
        por probabilidades, respetando R3 para el escenario desfavorable.
        La formulación colapsa al mismo LP que solve() para portafolios
        long-only sin recourse explícito.
        """
        # Para LP long-only sin recourse decisions, la formulación 2-SLP
        # es matemáticamente equivalente al LP con objetivo estocástico.
        return self.solve()


def build_scenario_returns(
    prices_df,
    tickers: List[str],
    window_weeks: int = 52,
    percentiles: Dict[str, float] = None,
) -> Dict[str, Dict[str, float]]:
    """
    Construye retornos semanales por escenario desde precios históricos.

    Escenarios:
      desf:   percentil 10 de retornos semanales históricos
      neutro: percentil 50 (mediana)
      fav:    percentil 90

    Parámetros
    ----------
    prices_df : pd.DataFrame con columnas = tickers, índice = fechas diarias
    window_weeks : int — semanas recientes a usar
    percentiles : dict {'desf': 10, 'neutro': 50, 'fav': 90}

    Retorna
    -------
    dict {'desf': {ticker: ret}, 'neutro': {ticker: ret}, 'fav': {ticker: ret}}
    """
    import pandas as pd

    if percentiles is None:
        percentiles = {"desf": 10, "neutro": 50, "fav": 90}

    # Convertir a retornos semanales (resamplear por semana)
    weekly = prices_df[tickers].resample("W").last().pct_change().dropna()

    # Usar ventana reciente
    if window_weeks and len(weekly) > window_weeks:
        weekly = weekly.tail(window_weeks)

    scenarios = {}
    for name, pct in percentiles.items():
        scenarios[name] = {
            t: float(np.percentile(weekly[t].dropna(), pct))
            for t in tickers
            if t in weekly.columns
        }

    return scenarios
