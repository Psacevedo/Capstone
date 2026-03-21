"""
simulation.py — Simulación probabilística del comportamiento del cliente.

Épica 2 & 3:
  - Genera recomendaciones periódicas de rebalanceo.
  - El cliente acepta o rechaza cada recomendación con probabilidad base.
  - Si las pérdidas superan la tolerancia máxima, el cliente puede retirar
    su capital (probabilidad proporcional al exceso de pérdida).
  - La empresa cobra una comisión del ~1% anual sobre el capital gestionado.
  - Se realizan N simulaciones Monte Carlo para obtener distribuciones de
    capital, comisiones y tasas de retiro.
"""
import logging
from typing import Dict

import numpy as np

log = logging.getLogger(__name__)


def simulate_client_behavior(
    initial_capital: float,
    expected_return: float,
    volatility: float,
    max_loss_pct: float,
    years: int = 3,
    commission_rate: float = 0.01,
    accept_prob: float = 0.70,
    n_simulations: int = 500,
    rebalance_freq_weeks: int = 4,
    rebalance_return_boost: float = 0.001,
    random_seed: int = 42,
) -> Dict:
    """
    Simula el comportamiento del cliente en un horizonte de ``years`` años.

    Parámetros
    ----------
    initial_capital : float
        Capital inicial invertido.
    expected_return : float
        Retorno esperado anual del portafolio (decimal, e.g. 0.10 = 10%).
    volatility : float
        Volatilidad anual del portafolio (decimal).
    max_loss_pct : float
        Tolerancia máxima de pérdida desde el pico (decimal, e.g. 0.20 = 20%).
    years : int
        Horizonte de simulación en años.
    commission_rate : float
        Comisión anual cobrada sobre el capital (decimal, e.g. 0.01 = 1%).
    accept_prob : float
        Probabilidad base de que el cliente acepte una recomendación.
    n_simulations : int
        Número de trayectorias Monte Carlo.
    rebalance_freq_weeks : int
        Cada cuántas semanas se emite una recomendación de rebalanceo.
    rebalance_return_boost : float
        Mejora incremental en retorno cuando el cliente acepta el rebalanceo.
    random_seed : int
        Semilla para reproducibilidad.

    Returns
    -------
    dict con:
        periods           : lista de índices de semana (submuestreados para la UI)
        capital_mean      : capital promedio por período
        capital_p10       : percentil 10 del capital
        capital_p90       : percentil 90 del capital
        final_capital_mean / _p10 / _p90 : capital final
        total_commissions_mean : comisiones totales promedio cobradas
        withdrawal_rate   : % de simulaciones donde el cliente retiró
        accepted_recommendations_mean : recomendaciones aceptadas en promedio
        total_recommendations : total de recomendaciones emitidas
    """
    rng = np.random.default_rng(random_seed)

    n_periods = years * 52          # semanas totales
    weekly_return = expected_return / 52
    weekly_vol = volatility / np.sqrt(52)
    weekly_commission = commission_rate / 52

    # Matrices de estado: filas=simulaciones, cols=períodos
    capitals = np.full((n_simulations, n_periods + 1), initial_capital, dtype=float)
    peak_capitals = np.full(n_simulations, initial_capital, dtype=float)

    total_commissions = np.zeros(n_simulations)
    withdrew = np.zeros(n_simulations, dtype=bool)
    accepted_recs = np.zeros(n_simulations, dtype=float)

    for t in range(1, n_periods + 1):
        prev = capitals[:, t - 1]

        # Retornos estocásticos del período
        period_returns = rng.normal(weekly_return, weekly_vol, n_simulations)

        # Recomendación de rebalanceo periódica
        if t % rebalance_freq_weeks == 0:
            accepted = rng.random(n_simulations) < accept_prob
            accepted_recs += accepted
            period_returns += accepted * rebalance_return_boost

        # Comisión del período
        commission = prev * weekly_commission
        total_commissions += commission

        # Nuevo capital
        new_cap = prev * (1.0 + period_returns) - commission
        new_cap = np.maximum(new_cap, 0.0)

        # Actualizar pico de capital
        peak_capitals = np.maximum(peak_capitals, new_cap)

        # Probabilidad de retiro según drawdown excedente
        drawdown = np.where(
            peak_capitals > 0,
            (peak_capitals - new_cap) / peak_capitals,
            0.0,
        )
        excess = drawdown - max_loss_pct
        withdraw_prob = np.clip(excess / max_loss_pct, 0.0, 1.0)

        newly_withdrawn = (~withdrew) & (rng.random(n_simulations) < withdraw_prob)
        withdrew |= newly_withdrawn

        # Clientes que retiraron congelan su capital en el valor previo
        new_cap[withdrew] = prev[withdrew]
        capitals[:, t] = new_cap

    # ---- Submuestreo para la respuesta (≤53 puntos) ----
    step = max(1, n_periods // 52)
    idx = list(range(0, n_periods + 1, step))
    if n_periods not in idx:
        idx.append(n_periods)

    sampled = capitals[:, idx]

    return {
        "periods": idx,
        "capital_mean": [round(float(v), 2) for v in sampled.mean(axis=0)],
        "capital_p10":  [round(float(v), 2) for v in np.percentile(sampled, 10, axis=0)],
        "capital_p90":  [round(float(v), 2) for v in np.percentile(sampled, 90, axis=0)],
        "final_capital_mean": round(float(capitals[:, -1].mean()), 2),
        "final_capital_p10":  round(float(np.percentile(capitals[:, -1], 10)), 2),
        "final_capital_p90":  round(float(np.percentile(capitals[:, -1], 90)), 2),
        "total_commissions_mean": round(float(total_commissions.mean()), 2),
        "withdrawal_rate": round(float(withdrew.mean() * 100), 2),
        "accepted_recommendations_mean": round(float(accepted_recs.mean()), 1),
        "total_recommendations": int(n_periods / rebalance_freq_weeks),
    }
