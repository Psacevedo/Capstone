"""
validators.py — Validación de soluciones de portafolio P4.

Verifica que la solución cumpla todas las restricciones del modelo
antes de devolverla al cliente.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np


# Tolerancias numéricas
TOL_BUDGET   = 1e-4   # |Σwᵢ + w₀ - 1| < TOL_BUDGET
TOL_NEGATIVE = -1e-6  # wᵢ ≥ TOL_NEGATIVE (pequeñas negatividades numéricas OK)
TOL_LOSS     = 1e-6   # margen para restricción de tolerancia de pérdida

# Perfiles de riesgo: tolerancia máxima de pérdida α_p
RISK_PROFILES = {
    "muy_conservador": 0.00,  # 0%
    "conservador":     0.05,  # 5%
    "neutro":          0.15,  # 15%
    "arriesgado":      0.30,  # 30%
    "muy_arriesgado":  0.40,  # 40%
}


@dataclass
class ValidationResult:
    valid:      bool
    violations: List[str] = field(default_factory=list)
    warnings:   List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "valid":      self.valid,
            "violations": self.violations,
            "warnings":   self.warnings,
        }


class PortfolioValidator:
    """
    Valida una solución de portafolio contra las restricciones del modelo P4.

    Parámetros
    ----------
    weights : dict  {ticker: weight} — pesos en acciones
    cash    : float — peso en caja chica (w₀)
    returns_scenario : dict {ticker: return} — retornos en escenario desfavorable
    profile : str   — nombre del perfil de riesgo
    commission_rate : float — tasa de comisión k (fracción, ej: 0.001)
    prev_weights : dict — pesos previos para calcular costos de rebalanceo
    """

    def __init__(
        self,
        weights:           Dict[str, float],
        cash:              float,
        returns_scenario:  Optional[Dict[str, float]] = None,
        profile:           str = "neutro",
        commission_rate:   float = 0.001,
        prev_weights:      Optional[Dict[str, float]] = None,
        max_weight_single: float = 1.0,
    ):
        self.weights           = weights
        self.cash              = cash
        self.returns_scenario  = returns_scenario or {}
        self.profile           = profile
        self.alpha             = RISK_PROFILES.get(profile, 0.15)
        self.commission_rate   = commission_rate
        self.prev_weights      = prev_weights or {}
        self.max_weight_single = max_weight_single

    def validate(self) -> ValidationResult:
        violations, warnings = [], []

        self._check_budget(violations, warnings)
        self._check_non_negativity(violations, warnings)
        self._check_max_weight(violations, warnings)
        self._check_loss_tolerance(violations, warnings)
        self._check_trivial(warnings)
        self._check_concentration(warnings)

        valid = len(violations) == 0
        return ValidationResult(valid=valid, violations=violations, warnings=warnings)

    # ------------------------------------------------------------------ #
    # Restricciones duras                                                  #
    # ------------------------------------------------------------------ #

    def _check_budget(self, violations, warnings):
        """R1: Σwᵢ + w₀ = 1"""
        total = sum(self.weights.values()) + self.cash
        err   = abs(total - 1.0)
        if err > TOL_BUDGET:
            violations.append(
                f"R1 VIOLADA — Restricción presupuesto: Σwᵢ + w₀ = {total:.6f} ≠ 1.0 "
                f"(error={err:.2e}, umbral={TOL_BUDGET:.0e})"
            )
        elif err > 1e-6:
            warnings.append(f"R1 Presupuesto: error numérico menor {err:.2e} (aceptable)")

    def _check_non_negativity(self, violations, warnings):
        """R2: wᵢ ≥ 0 (no short-selling)"""
        for ticker, w in self.weights.items():
            if w < TOL_NEGATIVE:
                violations.append(
                    f"R2 VIOLADA — Peso negativo: w[{ticker}] = {w:.6f}"
                )
        if self.cash < TOL_NEGATIVE:
            violations.append(f"R2 VIOLADA — Caja chica negativa: w₀ = {self.cash:.6f}")

    def _check_max_weight(self, violations, warnings):
        """Restricción de concentración máxima por acción."""
        if self.max_weight_single >= 1.0:
            return
        for ticker, w in self.weights.items():
            if w > self.max_weight_single + TOL_NEGATIVE:
                violations.append(
                    f"Concentración VIOLADA — w[{ticker}] = {w:.4f} > "
                    f"max_weight={self.max_weight_single:.2f}"
                )

    def _check_loss_tolerance(self, violations, warnings):
        """R3: Σwᵢ · rᵢˢ⁻ ≥ -α_p (escenario desfavorable)"""
        if not self.returns_scenario:
            warnings.append("R3 no verificada: retornos del escenario desfavorable no provistos")
            return
        portfolio_return = sum(
            self.weights.get(t, 0.0) * r
            for t, r in self.returns_scenario.items()
        )
        if portfolio_return < -self.alpha - TOL_LOSS:
            violations.append(
                f"R3 VIOLADA — Retorno escenario desfavorable: {portfolio_return:.4f} < "
                f"-α_p={-self.alpha:.4f} (perfil={self.profile})"
            )

    # ------------------------------------------------------------------ #
    # Advertencias (soft)                                                  #
    # ------------------------------------------------------------------ #

    def _check_trivial(self, warnings):
        """Detecta solución trivial (todo en caja chica)."""
        if self.cash > 0.95:
            warnings.append(
                f"Solución potencialmente trivial: caja chica w₀={self.cash:.1%}. "
                "El solver puede estar evitando el riesgo del escenario desfavorable."
            )

    def _check_concentration(self, warnings):
        """Detecta concentración excesiva en una sola acción."""
        for ticker, w in self.weights.items():
            if w > 0.40:
                warnings.append(
                    f"Concentración alta: w[{ticker}]={w:.1%} > 40%. "
                    "Considerar restricción de diversificación."
                )

    # ------------------------------------------------------------------ #
    # Utilidades                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def from_gurobi_solution(model, weight_vars: dict,
                              cash_var, **kwargs) -> "PortfolioValidator":
        """
        Construye un PortfolioValidator extrayendo valores directamente
        de un Model de gurobipy ya resuelto.

        weight_vars: dict {ticker: gurobipy.Var}
        cash_var:    gurobipy.Var
        """
        weights = {t: v.X for t, v in weight_vars.items()}
        cash    = cash_var.X
        return PortfolioValidator(weights=weights, cash=cash, **kwargs)

    @staticmethod
    def from_scipy_solution(x: np.ndarray, tickers: list,
                            cash_idx: int = -1, **kwargs) -> "PortfolioValidator":
        """
        Construye un PortfolioValidator desde el array solución de scipy.
        Por convención, x[-1] = peso caja chica.
        """
        if cash_idx == -1:
            cash_idx = len(x) - 1
        weights = {t: float(x[i]) for i, t in enumerate(tickers)}
        cash    = float(x[cash_idx])
        return PortfolioValidator(weights=weights, cash=cash, **kwargs)

    def portfolio_summary(self) -> Dict:
        """Resumen del portafolio para logging."""
        n_active = sum(1 for w in self.weights.values() if w > 1e-4)
        total_invested = sum(w for w in self.weights.values())
        top5 = sorted(self.weights.items(), key=lambda x: -x[1])[:5]

        return {
            "n_active_positions": n_active,
            "total_invested":     round(total_invested, 6),
            "cash_weight":        round(self.cash, 6),
            "top5_positions":     [(t, round(w, 4)) for t, w in top5],
            "profile":            self.profile,
            "alpha":              self.alpha,
        }
