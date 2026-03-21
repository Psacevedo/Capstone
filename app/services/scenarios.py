"""
scenarios.py — Proyección de retornos futuros bajo tres escenarios.

Épica 1: el cliente visualiza escenarios favorable, neutro y desfavorable
antes de comprometer su dinero.

Metodología:
  - Favorable:    retorno_anual = E[r] + 1.5 · σ
  - Neutro:       retorno_anual = E[r]
  - Desfavorable: retorno_anual = E[r] - 1.5 · σ

  El capital al final del año t es: C_t = C_0 · (1 + r_neto)^t
  donde r_neto = r_escenario - comisión_anual.
"""
from typing import Dict


SCENARIO_SIGMAS = {
    "favorable":    1.5,
    "neutro":       0.0,
    "desfavorable": -1.5,
}


def project_scenarios(
    initial_capital: float,
    expected_return: float,
    volatility: float,
    years: int = 5,
    commission_rate: float = 0.01,
) -> Dict:
    """
    Proyecta el capital final para cada escenario al cabo de 1..years años.

    Returns:
        {
          "favorable":    {"annual_return_pct": x, "capital_by_year": {"1": c1, ...}},
          "neutro":       {...},
          "desfavorable": {...},
        }
    """
    result: Dict = {}
    for name, sigma_mult in SCENARIO_SIGMAS.items():
        scenario_return = expected_return + sigma_mult * volatility
        net_return = scenario_return - commission_rate

        capital_by_year = {}
        for y in range(1, years + 1):
            capital_by_year[str(y)] = round(initial_capital * ((1 + net_return) ** y), 2)

        result[name] = {
            "annual_return_pct": round(net_return * 100, 2),
            "capital_by_year": capital_by_year,
            "total_return_pct": round(((1 + net_return) ** years - 1) * 100, 2),
        }
    return result


def project_scenarios_timeseries(
    initial_capital: float,
    expected_return: float,
    volatility: float,
    years: int = 5,
    commission_rate: float = 0.01,
) -> Dict:
    """
    Genera series mensuales de capital para graficar en el frontend.

    Returns:
        {
          "months": [0, 1, 2, ...],
          "favorable": [c0, c1, ...],
          "neutro": [...],
          "desfavorable": [...],
        }
    """
    n_months = years * 12
    months = list(range(n_months + 1))

    series: Dict = {"months": months}
    for name, sigma_mult in SCENARIO_SIGMAS.items():
        scenario_return = expected_return + sigma_mult * volatility
        net_monthly = (scenario_return - commission_rate) / 12
        series[name] = [
            round(initial_capital * ((1 + net_monthly) ** m), 2)
            for m in months
        ]
    return series
