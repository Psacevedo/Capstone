"""
stochastic_lp.py -- LP estocastico de 2 etapas P4 (capas 0-2).

Stage 1 (aqui y ahora): decidir pesos w_i
Stage 2 (wait and see): observar escenario s, evaluar V^s_t

Escenarios: desf (pi_1), neutro (pi_2), fav (pi_3),  sum(pi)=1

Para LP long-only sin decisiones de recourse, la formulacion 2-SLP
colapsa a maximizar el retorno esperado ponderado respetando R3.
"""

from typing import Dict, List, Optional


DEFAULT_PROBS = {"desf": 0.25, "neutro": 0.50, "fav": 0.25}


def generate_gurobi_code(
    tickers:       List[str],
    returns_scen:  Dict[str, Dict[str, float]],
    probs:         Dict[str, float],
    alpha:         float,
    commission_k:  float = 0.001,
    prev_weights:  Optional[Dict[str, float]] = None,
    max_weight:    float = 1.0,
    time_limit:    float = 9.0,
    model_name:    str   = "portfolio_p4_2slp",
) -> str:
    """
    Genera codigo Python/Gurobi para el modelo P4 2-SLP (capas 0-2).
    El codigo expone _model, _weights, _cash para el sandbox.
    """
    use_commissions = prev_weights is not None and commission_k > 0
    probs = {**DEFAULT_PROBS, **probs}

    lines = [
        "import gurobipy as gp",
        "from gurobipy import GRB",
        "",
        "# Datos del problema",
        "tickers      = " + repr(tickers),
        "returns_scen = " + repr(returns_scen),
        "probs        = " + repr(probs),
        "prev_weights = " + repr(prev_weights or {}),
        "alpha        = " + repr(alpha),
        "",
        "# Modelo 2-SLP",
        "_model = gp.Model(" + repr(model_name) + ")",
        "_model.Params.TimeLimit    = " + repr(time_limit),
        "_model.Params.OutputFlag   = 0",
        "_model.Params.LogToConsole = 0",
        "",
        "# Stage 1: variables de peso (decision aqui y ahora)",
        "_weights = {t: _model.addVar(lb=0.0, ub=" + repr(max_weight) + ", name='w_' + t) for t in tickers}",
        "_cash = _model.addVar(lb=0.0, ub=1.0, name='w_cash')",
        "_model.update()",
        "",
    ]

    if use_commissions:
        lines += [
            "# Linealizacion comisiones R4",
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
        "# Objetivo 2-SLP: max E_s[sum_i pi_s * r_i^s * w_i]",
        "expected_return = gp.quicksum(",
        "    probs.get(s, 1/3) * returns_scen[s].get(t, 0.0) * _weights[t]",
        "    for s in returns_scen",
        "    for t in tickers",
        ")",
        "_model.setObjective(expected_return - commission_cost, GRB.MAXIMIZE)",
        "",
        "# R1: Presupuesto",
        "_model.addConstr(gp.quicksum(_weights[t] for t in tickers) + _cash == 1.0, name='budget')",
        "",
        "# R3: Tolerancia de perdida (escenario desfavorable)",
        "if 'desf' in returns_scen:",
        "    _model.addConstr(",
        "        gp.quicksum(returns_scen['desf'].get(t, 0.0) * _weights[t] for t in tickers) >= -alpha,",
        "        name='loss_tolerance'",
        "    )",
        "",
    ]

    if max_weight < 1.0:
        lines += [
            "for t in tickers:",
            "    _model.addConstr(_weights[t] <= " + repr(max_weight) + ", name='maxw_' + t)",
            "",
        ]

    lines += [
        "# Resolver",
        "_model.optimize()",
    ]

    return "\n".join(lines)


def generate_latex_formulation(
    alpha: float,
    probs: Dict[str, float],
    commission_k: float,
) -> str:
    """Formulacion LaTeX del modelo 2-SLP para reportes."""
    p_desf   = probs.get("desf",   0.25)
    p_neutro = probs.get("neutro", 0.50)
    p_fav    = probs.get("fav",    0.25)
    return (
        "\\begin{align}\n"
        "  \\max_{\\mathbf{w}, w_0}\\;\n"
        "    & \\sum_{s \\in \\mathcal{S}} \\pi_s \\sum_{i} r_i^s w_i"
        " - k \\sum_{i} (\\Delta^+_i + \\Delta^-_i) \\\\\n"
        "  \\text{s.a.}\\quad\n"
        "  & \\sum_{i} w_i + w_0 = 1 \\tag{R1} \\\\\n"
        "  & w_i \\geq 0 \\quad \\forall i \\tag{R2} \\\\\n"
        f"  & \\sum_{{i}} r_i^{{\\text{{desf}}}} w_i \\geq -{alpha:.2f} \\tag{{R3}} \\\\\n"
        "  & \\Delta^+_i - \\Delta^-_i = w_i - w_i^{(t-1)} \\quad \\forall i \\tag{R4a} \\\\\n"
        "  & \\Delta^+_i, \\Delta^-_i \\geq 0 \\quad \\forall i \\tag{R4b}\n"
        "\\end{align}\n"
        f"% pi_desf={p_desf:.2f}, pi_neutro={p_neutro:.2f}, pi_fav={p_fav:.2f}\n"
        f"% k={commission_k:.4f}"
    )
