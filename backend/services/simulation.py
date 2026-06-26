"""
simulation.py — Simulacion Monte Carlo del cliente (Entrega 2, P4).

Replica exactamente el notebook p4_montecarlo_recomendador_portafolios.ipynb:
- 5000 trayectorias, 260 semanas (5 anos)
- Rebalanceo semanal, turnover 5% del capital actual
- P1 y P2 logisticas con sensibilidad s=20
- Score P4 = E[Wealth] + E[Utility] - C0 * WithdrawalRate
- Semilla determinista por combinacion via SHA-256
"""
import hashlib
import logging
from typing import Dict, Optional

import numpy as np

log = logging.getLogger(__name__)

LOGISTIC_SENSITIVITY = 20.0
TURNOVER_FRACTION = 0.05
DEFAULT_WEEKS = 260
DEFAULT_SIMULATIONS = 5000
RECOMMENDATION_INTERVAL_WEEKS = 1

WEEKLY_RETURN_CLIP = (-0.95, 1.50)
SEMESTER_WEEKS = 26


def _deterministic_seed(*args) -> int:
    raw = "|".join(str(a) for a in args).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16) % (2**31)


def _p1_withdrawal(loss_pct: np.ndarray, tolerance: float) -> np.ndarray:
    p = np.zeros_like(loss_pct, dtype=float)
    mask = loss_pct > tolerance
    z = np.clip(LOGISTIC_SENSITIVITY * (loss_pct[mask] - tolerance), -60, 60)
    p[mask] = 0.10 / (1.0 + np.exp(-z))
    return p


def _p2_acceptance(offered_return: float, tolerance: float) -> float:
    z = np.clip(LOGISTIC_SENSITIVITY * (offered_return - tolerance), -60, 60)
    return float(1.0 / (1.0 + np.exp(-z)))


def simulate_client_behavior(
    initial_capital: float,
    expected_return: float,
    volatility: float,
    max_loss_pct: float,
    years: int = 5,
    commission_rate: float = 0.01,
    accept_prob: Optional[float] = None,
    n_simulations: int = DEFAULT_SIMULATIONS,
    rebalance_freq_weeks: int = RECOMMENDATION_INTERVAL_WEEKS,
    rebalance_return_boost: float = 0.0,
    withdraw_eval_freq_weeks: int = 1,
    random_seed: Optional[int] = None,
    abandonment_policy: str = "legacy",
    company_monthly_fee_rate: Optional[float] = None,
    ruin_wealth: float = 0.0,
    return_semesters: bool = False,
) -> Dict:
    """
    Simula Monte Carlo para P4.

    - abandonment_policy="legacy": replica el modelo actual (P1/P2 logísticas escaladas con s=20), con comisiones que afectan al capital.
    - abandonment_policy="v1_plus": replica la versión V1+ del módulo P4 usada en Entrega 3:
        * aceptación inicial: sigmoid(ann_return - loss_tolerance) (sin sensibilidad)
        * abandono semanal: si loss_initial_pct > loss_tolerance, withdraw_prob = sigmoid(loss_initial_pct - loss_tolerance)
          y si wealth <= ruin_wealth => withdraw_prob=1
        * utilidad de la empresa: comisión mensual fija (por saldo administrado activo), sin restar la comisión al capital.

    Returns dict con:
        - periods, capital_mean/p10/p90 (trayectorias de riqueza)
        - final_capital_mean/p10/p90
        - total_commissions_mean (utilidad empresa)
        - withdrawal_rate (%)
        - accepted_recommendations_mean
        - score_p4
        - recommendation_acceptance_rate
    """
    if random_seed is None:
        random_seed = _deterministic_seed(
            initial_capital, expected_return, volatility, max_loss_pct,
            n_simulations, years,
        )
    rng = np.random.default_rng(random_seed)

    n_weeks = years * 52

    # ============================================================
    # V1+ (Entrega 3) — abandono con umbral logístico sin sensibilidad
    # y utilidad de empresa como comisión mensual fija sobre saldo activo.
    # ============================================================
    if abandonment_policy == "v1_plus":
        if company_monthly_fee_rate is None:
            company_monthly_fee_rate = 0.005  # 0,5% mensual (propuesta)

        # Conversión anual -> semanal
        weekly_mu = (1.0 + expected_return) ** (1.0 / 52.0) - 1.0 if expected_return > -1.0 else expected_return / 52.0
        weekly_sigma = volatility / np.sqrt(52.0)

        company_weekly_fee_rate = float(company_monthly_fee_rate) * 12.0 / 52.0

        def sigmoid(x: np.ndarray) -> np.ndarray:
            return 1.0 / (1.0 + np.exp(-x))

        # Aceptación inicial del portafolio
        # p_accept = sigmoid(ann_return - loss_tolerance)
        p_accept = float(sigmoid(np.array([expected_return - max_loss_pct], dtype=float))[0])

        wealth = np.full(n_simulations, initial_capital, dtype=float)
        active = rng.random(n_simulations) < p_accept
        withdrew = np.zeros(n_simulations, dtype=bool)
        company = np.zeros(n_simulations, dtype=float)

        # Para respuesta necesitamos series (submuestreo)
        capitals = np.full((n_simulations, n_weeks + 1), initial_capital, dtype=float)
        capitals[:, 0] = wealth

        # Desglose semestral
        if return_semesters:
            n_semesters = n_weeks // SEMESTER_WEEKS
            company_semester = np.zeros((n_simulations, n_semesters), dtype=float)
            semester_withdrew_snap = np.zeros((n_simulations, n_semesters), dtype=bool)

        for t in range(1, n_weeks + 1):
            idx = active & ~withdrew
            if idx.any():
                full_idx = np.where(idx)[0]
                n_active_start = full_idx.size

                rets = rng.normal(weekly_mu, weekly_sigma, n_active_start)
                # Regla de ruina (en V1+ se fuerza retiro cuando wealth <= ruin_wealth)
                wealth[idx] *= np.maximum(1.0 + rets, ruin_wealth)

                # Utilidad de empresa depende solo del saldo administrado activo
                company[idx] += wealth[idx] * company_weekly_fee_rate

                # Acumular por semestre
                if return_semesters:
                    current_sem = (t - 1) // SEMESTER_WEEKS
                    company_semester[idx, current_sem] += wealth[idx] * company_weekly_fee_rate

                loss_initial_money = np.maximum(initial_capital - wealth[idx], 0.0)
                loss_initial_pct = loss_initial_money / initial_capital

                behavioral_p = np.where(
                    loss_initial_pct > max_loss_pct,
                    sigmoid(loss_initial_pct - max_loss_pct),
                    0.0,
                )
                ruined = wealth[idx] <= ruin_wealth
                p_withdraw = np.where(ruined, 1.0, behavioral_p)
                withdraw_now = rng.random(n_active_start) < p_withdraw
                withdrew[full_idx[withdraw_now]] = True

            # Los retirados mantienen su riqueza (no reciben retornos futuros)
            capitals[:, t] = wealth

            # Snapshot de retiros al final de cada semestre
            if return_semesters and (t % SEMESTER_WEEKS == 0):
                sem_idx = t // SEMESTER_WEEKS - 1
                semester_withdrew_snap[:, sem_idx] = withdrew

        # ---- Submuestreo para respuesta (~61 puntos) ----
        step = max(1, n_weeks // 60)
        sampled_idx = list(range(0, n_weeks + 1, step))
        if n_weeks not in sampled_idx:
            sampled_idx.append(n_weeks)
        sampled = capitals[:, sampled_idx]

        final = capitals[:, -1]
        wealth_mean = float(final.mean())
        utility_mean = float(company.mean())
        wd_rate = float(withdrew.mean())
        score_p4 = round(wealth_mean + utility_mean - initial_capital * wd_rate, 2)

        # En V1+ la aceptación modela cuántos clientes inician activos
        acceptance_rate = p_accept

        # Desglose semestral V1+
        if return_semesters:
            n_semesters = n_weeks // SEMESTER_WEEKS
            semester_company_mean = [round(float(company_semester[:, s].mean()), 2) for s in range(n_semesters)]
            semester_wealth_mean = [round(float(capitals[:, (s + 1) * SEMESTER_WEEKS].mean()), 2) for s in range(n_semesters)]
            semester_active_rate = []
            for s in range(n_semesters):
                still_active = active & ~semester_withdrew_snap[:, s]
                active_count = float(still_active.sum())
                semester_active_rate.append(round(active_count / n_simulations * 100, 2))
            semester_labels = [f"Sem {(s * 6) + 1}-{((s + 1) * 6)}m" for s in range(n_semesters)]

        result = {
            "periods": sampled_idx,
            "period_unit": "week",
            "period_label": "Semana",
            "capital_mean": [round(float(v), 2) for v in sampled.mean(axis=0)],
            "capital_p10": [round(float(v), 2) for v in np.percentile(sampled, 10, axis=0)],
            "capital_p90": [round(float(v), 2) for v in np.percentile(sampled, 90, axis=0)],
            "final_capital_mean": round(wealth_mean, 2),
            "final_capital_p10": round(float(np.percentile(final, 10)), 2),
            "final_capital_p90": round(float(np.percentile(final, 90)), 2),
            "total_commissions_mean": round(utility_mean, 2),
            "withdrawal_rate": round(wd_rate * 100, 2),
            "accepted_recommendations_mean": round(float(active.mean()), 1),
            "total_recommendations": 0,
            "recommendation_acceptance_rate": round(acceptance_rate * 100, 2),
            "score_p4": score_p4,
            "p2_acceptance_prob_pct": round(p_accept * 100, 2),
            "rebalance_frequency": "weekly",
            "withdrawal_frequency": "weekly",
            "horizon_weeks": n_weeks,
            "horizon_years": years,
            "n_simulations": n_simulations,
            "turnover_fraction": TURNOVER_FRACTION,
            "logistic_sensitivity": 1.0,
            "abandonment_policy": abandonment_policy,
        }
        if return_semesters:
            result["semester_labels"] = semester_labels
            result["semester_company_mean"] = semester_company_mean
            result["semester_wealth_mean"] = semester_wealth_mean
            result["semester_active_rate"] = semester_active_rate
        return result

    # ============================================================
    # Legacy (modelo actual)
    # ============================================================
    # Conversion anual -> semanal
    weekly_return = (1.0 + expected_return) ** (1.0 / 52.0) - 1.0 if expected_return > -1.0 else expected_return / 52.0
    weekly_vol = volatility / np.sqrt(52)

    # Comision semanal base + por recomendacion aceptada
    weekly_commission_base = commission_rate / 52.0

    # P2 analitica: probabilidad de aceptar la recomendacion neutra
    neutral_accept_prob = _p2_acceptance(expected_return, max_loss_pct)

    capitals = np.full((n_simulations, n_weeks + 1), initial_capital, dtype=float)
    withdrew = np.zeros(n_simulations, dtype=bool)
    total_commissions = np.zeros(n_simulations)
    accepted_recs = np.zeros(n_simulations, dtype=int)
    total_recs = np.zeros(n_simulations, dtype=int)

    if return_semesters:
        n_semesters_legacy = n_weeks // SEMESTER_WEEKS
        commissions_semester = np.zeros((n_simulations, n_semesters_legacy), dtype=float)
        semester_withdrew_snap_legacy = np.zeros((n_simulations, n_semesters_legacy), dtype=bool)

    for t in range(1, n_weeks + 1):
        prev = capitals[:, t - 1]

        # Retornos estocasticos
        weekly_ret = rng.normal(weekly_return, weekly_vol, n_simulations)
        weekly_ret = np.clip(weekly_ret, *WEEKLY_RETURN_CLIP)

        current_sem_legacy = (t - 1) // SEMESTER_WEEKS

        # Comision base sobre capital gestionado
        total_commissions += prev * weekly_commission_base
        if return_semesters:
            commissions_semester[:, current_sem_legacy] += prev * weekly_commission_base

        # Recomendacion periodica
        if t % rebalance_freq_weeks == 0:
            total_recs += 1
            if accept_prob is not None:
                accepted = rng.random(n_simulations) < accept_prob
            else:
                accepted = rng.random(n_simulations) < neutral_accept_prob
            accepted_recs += accepted.astype(int)
            # Comision extra por turnover sobre capital aceptado
            turnover_commission = accepted.astype(float) * prev * TURNOVER_FRACTION * commission_rate
            total_commissions += turnover_commission
            if return_semesters:
                commissions_semester[:, current_sem_legacy] += turnover_commission
            # Boost de retorno si acepta
            weekly_ret += accepted.astype(float) * rebalance_return_boost

        # Nuevo capital
        new_cap = prev * (1.0 + weekly_ret) - prev * weekly_commission_base
        new_cap = np.maximum(new_cap, 0.0)

        # Evaluar retiro (P1) medido contra capital inicial (Entrega 2)
        if t % withdraw_eval_freq_weeks == 0:
            loss = (initial_capital - new_cap) / initial_capital
            withdraw_prob = _p1_withdrawal(loss, max_loss_pct)
            newly_withdrawn = (~withdrew) & (rng.random(n_simulations) < withdraw_prob)
            withdrew |= newly_withdrawn

        new_cap[withdrew] = prev[withdrew]
        capitals[:, t] = new_cap

        # Snapshot de retiros al final de cada semestre
        if return_semesters and (t % SEMESTER_WEEKS == 0):
            sem_idx = t // SEMESTER_WEEKS - 1
            semester_withdrew_snap_legacy[:, sem_idx] = withdrew

    # ---- Submuestreo para respuesta (~61 puntos) ----
    step = max(1, n_weeks // 60)
    sampled_idx = list(range(0, n_weeks + 1, step))
    if n_weeks not in sampled_idx:
        sampled_idx.append(n_weeks)
    sampled = capitals[:, sampled_idx]

    final = capitals[:, -1]
    wealth_mean = float(final.mean())
    utility_mean = float(total_commissions.mean())
    wd_rate = float(withdrew.mean())
    acceptance_rate = float(accepted_recs.sum()) / max(float(total_recs.sum()), 1)

    score_p4 = round(wealth_mean + utility_mean - initial_capital * wd_rate, 2)

    result = {
        "periods": sampled_idx,
        "period_unit": "week",
        "period_label": "Semana",
        "capital_mean": [round(float(v), 2) for v in sampled.mean(axis=0)],
        "capital_p10": [round(float(v), 2) for v in np.percentile(sampled, 10, axis=0)],
        "capital_p90": [round(float(v), 2) for v in np.percentile(sampled, 90, axis=0)],
        "final_capital_mean": round(wealth_mean, 2),
        "final_capital_p10": round(float(np.percentile(final, 10)), 2),
        "final_capital_p90": round(float(np.percentile(final, 90)), 2),
        "total_commissions_mean": round(utility_mean, 2),
        "withdrawal_rate": round(wd_rate * 100, 2),
        "accepted_recommendations_mean": round(float(accepted_recs.mean()), 1),
        "total_recommendations": int(total_recs.mean()),
        "recommendation_acceptance_rate": round(acceptance_rate * 100, 2),
        "score_p4": score_p4,
        "p2_acceptance_prob_pct": round(neutral_accept_prob * 100, 2),
        "rebalance_frequency": "weekly" if rebalance_freq_weeks == 1 else f"every_{rebalance_freq_weeks}w",
        "withdrawal_frequency": "weekly" if withdraw_eval_freq_weeks == 1 else f"every_{withdraw_eval_freq_weeks}w",
        "horizon_weeks": n_weeks,
        "horizon_years": years,
        "n_simulations": n_simulations,
        "turnover_fraction": TURNOVER_FRACTION,
        "logistic_sensitivity": LOGISTIC_SENSITIVITY,
        "abandonment_policy": abandonment_policy,
    }
    if return_semesters:
        result["semester_labels"] = [f"Sem {(s * 6) + 1}-{((s + 1) * 6)}m" for s in range(n_semesters_legacy)]
        result["semester_company_mean"] = [round(float(commissions_semester[:, s].mean()), 2) for s in range(n_semesters_legacy)]
        result["semester_wealth_mean"] = [round(float(capitals[:, (s + 1) * SEMESTER_WEEKS].mean()), 2) for s in range(n_semesters_legacy)]
        result["semester_active_rate"] = [
            round(float((~(semester_withdrew_snap_legacy[:, s])).mean()) * 100, 2)
            for s in range(n_semesters_legacy)
        ]
    return result


    
