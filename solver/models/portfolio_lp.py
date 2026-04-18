"""
portfolio_lp.py -- Modelo LP base P4 (capas 0-1).

Genera codigo Python/Gurobi listo para ser ejecutado por el SolverSandbox.

Capas implementadas:
  Capa 0: max E[r]*w,  s.t. sum(w)=1, w>=0
  Capa 1: linealizacion |Dw| con variables D+, D-

Variables requeridas por el sandbox:
  _model   : gp.Model (ya resuelto)
  _weights : dict {ticker: gp.Var}
  _cash    : gp.Var
"""

from typing import Dict, List, Optional


def generate_gurobi_code(
    tickers:        List[str],
    returns_mean:   Dict[str, float],
    returns_desf:   Dict[str, float],
    alpha:          float,
    commission_k:   float = 0.001,
    prev_weights:   Optional[Dict[str, float]] = None,
    max_weight:     float = 1.0,
    time_limit:     float = 9.0,
    model_name:     str   = "portfolio_p4_base",
) -> str:
    """
    Genera codigo Python/Gurobi para el modelo P4 capas 0-1.
    El codigo expone _model, _weights, _cash para el sandbox.
    """
    use_commissions = prev_weights is not None and commission_k > 0

    lines = [
        "import gurobipy as gp",
        "from gurobipy import GRB",
        "",
        "# Datos del problema",
        "tickers      = " + repr(tickers),
        "returns_mean = " + repr(returns_mean),
        "returns_desf = " + repr(returns_desf),
        "prev_weights = " + repr(prev_weights or {}),
        "alpha        = " + repr(alpha),
        "",
        "# Construccion del modelo",
        "_model = gp.Model(" + repr(model_name) + ")",
        "_model.Params.TimeLimit    = " + repr(time_limit),
        "_model.Params.OutputFlag   = 0",
        "_model.Params.LogToConsole = 0",
        "",
        "# Variables de peso: w_i in [0, " + str(max_weight) + "]",
        "_weights = {t: _model.addVar(lb=0.0, ub=" + repr(max_weight) + ", name='w_' + t) for t in tickers}",
        "_cash = _model.addVar(lb=0.0, ub=1.0, name='w_cash')",
        "_model.update()",
        "",
    ]

    if use_commissions:
        lines += [
            "# Linealizacion comisiones R4: |Dw_i| = dp_i + dn_i",
            "dp = {t: _model.addVar(lb=0.0, name='dp_' + t) for t in tickers}",
            "dn = {t: _model.addVar(lb=0.0, name='dn_' + t) for t in tickers}",
            "_model.update()",
            "for t in tickers:",
            "    pw = prev_weights.get(t, 0.0)",
            "    _model.addConstr(_weights[t] - pw == dp[t] - dn[t], name='delta_' + t)",
            "commission_cost = gp.quicksum(" + repr(commission_k) + " * (dp[t] + dn[t]) for t in tickers)",
            "",
        ]
    else:
        lines += [
            "commission_cost = 0.0",
            "",
        ]

    lines += [
        "# Objetivo: max E[r]*w - comisiones",
        "expected_return = gp.quicksum(returns_mean.get(t, 0.0) * _weights[t] for t in tickers)",
        "_model.setObjective(expected_return - commission_cost, GRB.MAXIMIZE)",
        "",
        "# R1: Presupuesto: sum(w_i) + w_0 = 1",
        "_model.addConstr(gp.quicksum(_weights[t] for t in tickers) + _cash == 1.0, name='budget')",
        "",
        "# R3: Tolerancia de perdida: sum(r_desf_i * w_i) >= -alpha",
        "_model.addConstr(",
        "    gp.quicksum(returns_desf.get(t, 0.0) * _weights[t] for t in tickers) >= -alpha,",
        "    name='loss_tolerance'",
        ")",
        "",
    ]

    if max_weight < 1.0:
        lines += [
            "# Concentracion maxima por accion",
            "for t in tickers:",
            "    _model.addConstr(_weights[t] <= " + repr(max_weight) + ", name='maxw_' + t)",
            "",
        ]

    lines += [
        "# Resolver",
        "_model.optimize()",
    ]

    return "\n".join(lines)


def generate_latex_formulation(alpha: float, commission_k: float) -> str:
    """Formulacion LaTeX del modelo LP base para incluir en reportes."""
    return (
        "\\begin{align}\n"
        "  \\max_{\\mathbf{w}, w_0}\\; & \\sum_{i} \\mu_i w_i"
        " - k \\sum_{i} (\\Delta^+_i + \\Delta^-_i) \\\\\n"
        "  \\text{s.a.}\\quad\n"
        "  & \\sum_{i} w_i + w_0 = 1 \\tag{R1} \\\\\n"
        "  & w_i \\geq 0 \\quad \\forall i \\tag{R2} \\\\\n"
        f"  & \\sum_{{i}} r_i^{{\\text{{desf}}}} w_i \\geq -{alpha:.2f} \\tag{{R3}} \\\\\n"
        "  & \\Delta^+_i - \\Delta^-_i = w_i - w_i^{(t-1)} \\quad \\forall i \\tag{R4a} \\\\\n"
        "  & \\Delta^+_i, \\Delta^-_i \\geq 0 \\quad \\forall i \\tag{R4b}\n"
        "\\end{align}\n"
        f"% k = {commission_k:.4f}"
    )
