"""
Simulacion P4 con panoramas proyectados de retorno para FinPUC.

Esta iteracion reutiliza la configuracion ganadora de Momentum general ya
calibrada en views_v1_plus. No recalibra Black-Litterman: toma como insumo los
retornos y volatilidades anuales del test P4 limpio y re-simula Monte Carlo bajo
tres panoramas de retorno esperado:

    desfavorable: R_base - 0.5 * sigma_base
    neutro:       R_base
    favorable:   R_base + 0.5 * sigma_base
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

import calibracion_secuencial_bl_base_copiada as base


WORK_DIR = Path(__file__).resolve().parent
INPUT_DIR = WORK_DIR / "inputs"
OUTPUT_DIR = WORK_DIR / "outputs"
TEST_DIR = OUTPUT_DIR / "test_p4"
BEHAVIOR_DIR = OUTPUT_DIR / "behavior"
for directory in [INPUT_DIR, OUTPUT_DIR, TEST_DIR, BEHAVIOR_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

BASE_P4_INPUT = INPUT_DIR / "p4_base_neutro_detalle.csv"

RNG_SEED_P4 = 20260611
REBALANCE_WEEKS = 26
MONTH_WEEKS = 4
RUIN_WEALTH = 0.0
COMPANY_MONTHLY_FEE_RATE = 0.005
COMPANY_WEEKLY_FEE_RATE = COMPANY_MONTHLY_FEE_RATE * 12.0 / 52.0
ABANDONMENT_VERSION = "v1_plus_panoramas"
ABANDONMENT_FORMULA = "threshold_logistic_unscaled_with_ruin"

PANORAMAS_RETORNO: Dict[str, float] = {
    "desfavorable": -0.5,
    "neutro": 0.0,
    "favorable": 0.5,
}

LOSS_COLS = [
    "loss_initial_pct",
    "loss_initial_money",
    "cumulative_loss_initial_week_pct",
    "cumulative_loss_initial_week_money",
    "cumulative_loss_initial_month_pct",
    "cumulative_loss_initial_month_money",
    "cumulative_loss_initial_semester_pct",
    "cumulative_loss_initial_semester_money",
    "period_loss_wealth_week_pct",
    "period_loss_wealth_week_money",
    "period_loss_wealth_month_pct",
    "period_loss_wealth_month_money",
    "period_loss_wealth_semester_pct",
    "period_loss_wealth_semester_money",
    "cumulative_period_loss_wealth_week_pct",
    "cumulative_period_loss_wealth_week_money",
    "cumulative_period_loss_wealth_month_pct",
    "cumulative_period_loss_wealth_month_money",
    "cumulative_period_loss_wealth_semester_pct",
    "cumulative_period_loss_wealth_semester_money",
]


def log(message: str) -> None:
    print(f"[P4-PANORAMAS] {message}", flush=True)


def pctile_10(values: pd.Series) -> float:
    return float(np.percentile(values.dropna().to_numpy(dtype=float), 10)) if values.notna().any() else np.nan


def prepare_p4_input() -> pd.DataFrame:
    if not BASE_P4_INPUT.exists():
        raise FileNotFoundError(
            f"No existe {BASE_P4_INPUT}. Copia p4_test_limpio_detalle.csv desde momentum_general_v1_plus antes de ejecutar."
        )
    raw = pd.read_csv(BASE_P4_INPUT)
    required = {
        "modelo",
        "scenario",
        "window_id",
        "window_role",
        "portfolio",
        "retorno_anual_input",
        "volatilidad_anual_input",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"Faltan columnas en insumo P4 base: {missing}")

    base_rows = (
        raw[list(required)]
        .rename(
            columns={
                "retorno_anual_input": "retorno_anual_base",
                "volatilidad_anual_input": "volatilidad_anual_base",
            }
        )
        .drop_duplicates()
        .reset_index(drop=True)
    )

    rows: List[Dict[str, object]] = []
    for _, row in base_rows.iterrows():
        for panorama, factor in PANORAMAS_RETORNO.items():
            ann_return_base = float(row["retorno_anual_base"])
            ann_vol_base = max(float(row["volatilidad_anual_base"]), 1e-6)
            ann_return_projected = max(ann_return_base + factor * ann_vol_base, -0.99)
            rows.append(
                {
                    **row.to_dict(),
                    "panorama_retorno": panorama,
                    "panorama_factor": factor,
                    "retorno_anual_proyectado": ann_return_projected,
                    "volatilidad_anual_proyectada": ann_vol_base,
                }
            )
    return pd.DataFrame(rows)


def simulate_p4_panoramas(metrics_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    weekly_rows: List[Dict[str, object]] = []
    rng = np.random.default_rng(RNG_SEED_P4)

    for _, row in metrics_df.iterrows():
        profile = base.PROFILE_BY_LABEL[row["portfolio"]]
        ann_return_base = float(row["retorno_anual_base"])
        ann_vol_base = max(float(row["volatilidad_anual_base"]), 1e-6)
        ann_return = float(row["retorno_anual_proyectado"])
        ann_vol = max(float(row["volatilidad_anual_proyectada"]), 1e-6)
        weekly_mu = (1.0 + ann_return) ** (1.0 / 52.0) - 1.0
        weekly_sigma = ann_vol / math.sqrt(52.0)
        p_accept = 1.0 / (1.0 + math.exp(-(ann_return - profile.loss_tolerance)))

        wealth = np.full(base.N_SIMULATIONS, base.INITIAL_CAPITAL)
        active = rng.random(base.N_SIMULATIONS) < p_accept
        company = np.zeros(base.N_SIMULATIONS, dtype=float)
        withdrawn = np.zeros(base.N_SIMULATIONS, dtype=bool)
        withdraw_probability_sum = 0.0
        withdraw_probability_count = 0
        withdraw_probability_max = 0.0

        month_start_wealth = wealth.copy()
        semester_start_wealth = wealth.copy()
        cum_loss_initial_week_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_loss_initial_week_pct = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_loss_initial_month_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_loss_initial_month_pct = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_loss_initial_semester_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_loss_initial_semester_pct = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_week_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_week_pct = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_month_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_month_pct = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_semester_money = np.zeros(base.N_SIMULATIONS, dtype=float)
        cum_period_loss_semester_pct = np.zeros(base.N_SIMULATIONS, dtype=float)

        for week_idx in range(base.N_WEEKS):
            week_number = int(week_idx + 1)
            if week_idx % MONTH_WEEKS == 0:
                month_start_wealth[active & ~withdrawn] = wealth[active & ~withdrawn]
            if week_idx % REBALANCE_WEEKS == 0:
                semester_start_wealth[active & ~withdrawn] = wealth[active & ~withdrawn]

            idx = active & ~withdrawn
            week_withdrawals = 0
            mean_weekly_p = 0.0
            realized_weekly_rate = 0.0
            loss_metrics = {col: 0.0 for col in LOSS_COLS}

            if idx.any():
                n_active_start = int(idx.sum())
                full_idx = np.where(idx)[0]
                wealth_start_week = wealth[idx].copy()
                wealth_start_month = month_start_wealth[idx].copy()
                wealth_start_semester = semester_start_wealth[idx].copy()

                rets = rng.normal(weekly_mu, weekly_sigma, n_active_start)
                wealth[idx] *= np.maximum(1.0 + rets, RUIN_WEALTH)
                company[idx] += wealth[idx] * COMPANY_WEEKLY_FEE_RATE

                loss_initial_money = np.maximum(base.INITIAL_CAPITAL - wealth[idx], 0.0)
                loss_initial_pct = loss_initial_money / base.INITIAL_CAPITAL
                period_loss_week_money = np.maximum(wealth_start_week - wealth[idx], 0.0)
                period_loss_week_pct = np.divide(
                    period_loss_week_money,
                    wealth_start_week,
                    out=np.zeros_like(period_loss_week_money),
                    where=wealth_start_week > 0,
                )
                period_loss_month_money = np.maximum(wealth_start_month - wealth[idx], 0.0)
                period_loss_month_pct = np.divide(
                    period_loss_month_money,
                    wealth_start_month,
                    out=np.zeros_like(period_loss_month_money),
                    where=wealth_start_month > 0,
                )
                period_loss_semester_money = np.maximum(wealth_start_semester - wealth[idx], 0.0)
                period_loss_semester_pct = np.divide(
                    period_loss_semester_money,
                    wealth_start_semester,
                    out=np.zeros_like(period_loss_semester_money),
                    where=wealth_start_semester > 0,
                )

                cum_loss_initial_week_money[full_idx] += loss_initial_money
                cum_loss_initial_week_pct[full_idx] += loss_initial_pct
                cum_period_loss_week_money[full_idx] += period_loss_week_money
                cum_period_loss_week_pct[full_idx] += period_loss_week_pct
                if week_number % MONTH_WEEKS == 0:
                    cum_loss_initial_month_money[full_idx] += loss_initial_money
                    cum_loss_initial_month_pct[full_idx] += loss_initial_pct
                    cum_period_loss_month_money[full_idx] += period_loss_month_money
                    cum_period_loss_month_pct[full_idx] += period_loss_month_pct
                if week_number % REBALANCE_WEEKS == 0:
                    cum_loss_initial_semester_money[full_idx] += loss_initial_money
                    cum_loss_initial_semester_pct[full_idx] += loss_initial_pct
                    cum_period_loss_semester_money[full_idx] += period_loss_semester_money
                    cum_period_loss_semester_pct[full_idx] += period_loss_semester_pct

                behavioral_p = np.where(
                    loss_initial_pct > profile.loss_tolerance,
                    1.0 / (1.0 + np.exp(-(loss_initial_pct - profile.loss_tolerance))),
                    0.0,
                )
                ruined = wealth[idx] <= RUIN_WEALTH
                p_withdraw = np.where(ruined, 1.0, behavioral_p)
                withdraw_probability_sum += float(p_withdraw.sum())
                withdraw_probability_count += int(len(p_withdraw))
                withdraw_probability_max = max(withdraw_probability_max, float(p_withdraw.max(initial=0.0)))
                mean_weekly_p = float(p_withdraw.mean()) if len(p_withdraw) else 0.0
                withdraw_now = rng.random(n_active_start) < p_withdraw
                week_withdrawals = int(withdraw_now.sum())
                realized_weekly_rate = week_withdrawals / n_active_start if n_active_start else 0.0
                withdrawn[full_idx[withdraw_now]] = True

                loss_metrics.update(
                    {
                        "period_loss_wealth_week_pct": float(period_loss_week_pct.mean()),
                        "period_loss_wealth_week_money": float(period_loss_week_money.mean()),
                        "period_loss_wealth_month_pct": float(period_loss_month_pct.mean()),
                        "period_loss_wealth_month_money": float(period_loss_month_money.mean()),
                        "period_loss_wealth_semester_pct": float(period_loss_semester_pct.mean()),
                        "period_loss_wealth_semester_money": float(period_loss_semester_money.mean()),
                    }
                )

            active_end_mask = active & ~withdrawn
            active_end = int(active_end_mask.sum())
            mean_active_wealth = float(wealth[active_end_mask].mean()) if active_end else 0.0
            mean_active_gain = mean_active_wealth - base.INITIAL_CAPITAL if active_end else -base.INITIAL_CAPITAL
            loss_metrics.update(
                {
                    "loss_initial_pct": float(
                        np.maximum((base.INITIAL_CAPITAL - wealth[active_end_mask]) / base.INITIAL_CAPITAL, 0.0).mean()
                    )
                    if active_end
                    else 1.0,
                    "loss_initial_money": float(np.maximum(base.INITIAL_CAPITAL - wealth[active_end_mask], 0.0).mean())
                    if active_end
                    else base.INITIAL_CAPITAL,
                    "cumulative_loss_initial_week_pct": float(cum_loss_initial_week_pct[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_loss_initial_week_money": float(cum_loss_initial_week_money[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_loss_initial_month_pct": float(cum_loss_initial_month_pct[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_loss_initial_month_money": float(cum_loss_initial_month_money[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_loss_initial_semester_pct": float(cum_loss_initial_semester_pct[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_loss_initial_semester_money": float(
                        cum_loss_initial_semester_money[active_end_mask].mean()
                    )
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_week_pct": float(cum_period_loss_week_pct[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_week_money": float(cum_period_loss_week_money[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_month_pct": float(cum_period_loss_month_pct[active_end_mask].mean())
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_month_money": float(
                        cum_period_loss_month_money[active_end_mask].mean()
                    )
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_semester_pct": float(
                        cum_period_loss_semester_pct[active_end_mask].mean()
                    )
                    if active_end
                    else 0.0,
                    "cumulative_period_loss_wealth_semester_money": float(
                        cum_period_loss_semester_money[active_end_mask].mean()
                    )
                    if active_end
                    else 0.0,
                }
            )
            company_revenue_cumulative_mean = float(company.mean())
            company_revenue_active_mean = float(company[active_end_mask].mean()) if active_end else 0.0
            common = {
                "modelo": row["modelo"],
                "abandonment_version": ABANDONMENT_VERSION,
                "abandonment_formula": ABANDONMENT_FORMULA,
                "scenario": row["scenario"],
                "panorama_retorno": row["panorama_retorno"],
                "panorama_factor": row["panorama_factor"],
                "window_id": row["window_id"],
                "window_role": row["window_role"],
                "portfolio": row["portfolio"],
            }
            weekly_rows.append(
                {
                    **common,
                    "week": week_number,
                    "month": int(math.ceil(week_number / MONTH_WEEKS)),
                    "semester": int(math.ceil(week_number / REBALANCE_WEEKS)),
                    "active_clients": active_end,
                    "weekly_withdrawals": week_withdrawals,
                    "p_accept_rebalance": float(p_accept),
                    "mean_weekly_abandon_probability": float(mean_weekly_p),
                    "realized_weekly_abandon_rate": float(realized_weekly_rate),
                    "mean_active_wealth": mean_active_wealth,
                    "mean_active_gain": mean_active_gain,
                    "mean_active_loss": loss_metrics["loss_initial_pct"],
                    "company_revenue_cumulative_mean": company_revenue_cumulative_mean,
                    "company_revenue_active_mean": company_revenue_active_mean,
                    **loss_metrics,
                }
            )

        initial_active_clients = int(active.sum())
        final_active_clients = int((active & ~withdrawn).sum())
        mean_withdraw_probability = (
            withdraw_probability_sum / withdraw_probability_count if withdraw_probability_count else 0.0
        )
        monthly_withdraw_probability = 1.0 - (1.0 - mean_withdraw_probability) ** MONTH_WEEKS
        semiannual_withdraw_probability = 1.0 - (1.0 - mean_withdraw_probability) ** REBALANCE_WEEKS
        max_monthly_withdraw_probability = 1.0 - (1.0 - withdraw_probability_max) ** MONTH_WEEKS
        max_semiannual_withdraw_probability = 1.0 - (1.0 - withdraw_probability_max) ** REBALANCE_WEEKS
        rows.append(
            {
                "modelo": row["modelo"],
                "abandonment_version": ABANDONMENT_VERSION,
                "abandonment_formula": ABANDONMENT_FORMULA,
                "scenario": row["scenario"],
                "panorama_retorno": row["panorama_retorno"],
                "panorama_factor": row["panorama_factor"],
                "window_id": row["window_id"],
                "window_role": row["window_role"],
                "portfolio": row["portfolio"],
                "retorno_anual_base": ann_return_base,
                "volatilidad_anual_base": ann_vol_base,
                "retorno_anual_proyectado": ann_return,
                "volatilidad_anual_proyectada": ann_vol,
                "initial_clients_total": int(base.N_SIMULATIONS),
                "initial_active_clients": initial_active_clients,
                "final_active_clients": final_active_clients,
                "p_accept_initial_portfolio": float(p_accept),
                "p_accept_rebalance": float(p_accept),
                "n_rebalance_opportunities": int(base.N_WEEKS // REBALANCE_WEEKS),
                "mean_weekly_abandon_probability": float(mean_withdraw_probability),
                "max_weekly_abandon_probability": float(withdraw_probability_max),
                "mean_monthly_abandon_probability": float(monthly_withdraw_probability),
                "max_monthly_abandon_probability": float(max_monthly_withdraw_probability),
                "mean_semiannual_abandon_probability": float(semiannual_withdraw_probability),
                "max_semiannual_abandon_probability": float(max_semiannual_withdraw_probability),
                "terminal_wealth_mean": float(wealth.mean()),
                "prob_profit": float((wealth > base.INITIAL_CAPITAL).mean()),
                "withdrawal_rate": float(withdrawn.mean()),
                "company_revenue_mean": float(company.mean()),
                "p4_score": float(wealth.mean() + company.mean() - base.INITIAL_CAPITAL * withdrawn.mean()),
            }
        )

    return pd.DataFrame(rows).sort_values("p4_score", ascending=False), pd.DataFrame(weekly_rows)


def summarize_p4(p4: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    group_cols = ["modelo", "scenario", "portfolio", "panorama_retorno"]
    summary = (
        p4.groupby(group_cols, as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            simulated_clients_total=("initial_clients_total", "sum"),
            retorno_anual_base_mean=("retorno_anual_base", "mean"),
            volatilidad_anual_base_mean=("volatilidad_anual_base", "mean"),
            retorno_anual_proyectado_mean=("retorno_anual_proyectado", "mean"),
            initial_active_clients_mean=("initial_active_clients", "mean"),
            final_active_clients_mean=("final_active_clients", "mean"),
            p_accept_initial_portfolio_mean=("p_accept_initial_portfolio", "mean"),
            p_accept_rebalance_mean=("p_accept_rebalance", "mean"),
            mean_weekly_abandon_probability=("mean_weekly_abandon_probability", "mean"),
            max_weekly_abandon_probability=("max_weekly_abandon_probability", "max"),
            mean_semiannual_abandon_probability=("mean_semiannual_abandon_probability", "mean"),
            max_semiannual_abandon_probability=("max_semiannual_abandon_probability", "max"),
            terminal_wealth_mean=("terminal_wealth_mean", "mean"),
            terminal_wealth_p10=("terminal_wealth_mean", pctile_10),
            prob_profit_mean=("prob_profit", "mean"),
            withdrawal_rate_mean=("withdrawal_rate", "mean"),
            company_revenue_mean=("company_revenue_mean", "mean"),
            p4_score_mean=("p4_score", "mean"),
        )
        .sort_values(["modelo", "scenario", "portfolio", "panorama_retorno"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_behavior(p4: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    group_cols = ["modelo", "scenario", "portfolio", "panorama_retorno"]
    summary = (
        p4.groupby(group_cols, as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            initial_active_clients_mean=("initial_active_clients", "mean"),
            final_active_clients_mean=("final_active_clients", "mean"),
            p_accept_initial_portfolio=("p_accept_initial_portfolio", "mean"),
            p_accept_rebalance=("p_accept_rebalance", "mean"),
            mean_weekly_abandon_probability=("mean_weekly_abandon_probability", "mean"),
            max_weekly_abandon_probability=("max_weekly_abandon_probability", "max"),
            mean_semiannual_abandon_probability=("mean_semiannual_abandon_probability", "mean"),
            max_semiannual_abandon_probability=("max_semiannual_abandon_probability", "max"),
            realized_abandon_rate_260w=("withdrawal_rate", "mean"),
        )
        .sort_values(group_cols)
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_weekly_behavior(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        timeline.groupby(["modelo", "scenario", "portfolio", "panorama_retorno", "week"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            active_clients_mean=("active_clients", "mean"),
            active_clients_total=("active_clients", "sum"),
            p_accept_rebalance=("p_accept_rebalance", "mean"),
            mean_weekly_abandon_probability=("mean_weekly_abandon_probability", "mean"),
            realized_weekly_abandon_rate=("realized_weekly_abandon_rate", "mean"),
            weekly_withdrawals_mean=("weekly_withdrawals", "mean"),
            mean_active_wealth=("mean_active_wealth", "mean"),
            mean_active_gain=("mean_active_gain", "mean"),
            mean_active_loss=("mean_active_loss", "mean"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "mean"),
            company_revenue_active_mean=("company_revenue_active_mean", "mean"),
            **{col: (col, "mean") for col in LOSS_COLS},
        )
        .sort_values(["modelo", "scenario", "portfolio", "panorama_retorno", "week"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_monthly_behavior(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    detail = (
        timeline.sort_values(["modelo", "scenario", "portfolio", "panorama_retorno", "window_id", "month", "week"])
        .groupby(["modelo", "scenario", "portfolio", "panorama_retorno", "window_id", "month"], as_index=False)
        .agg(
            week_end=("week", "max"),
            active_clients=("active_clients", "last"),
            p_accept_rebalance=("p_accept_rebalance", "last"),
            monthly_abandon_probability=(
                "mean_weekly_abandon_probability",
                lambda x: float(1.0 - np.prod(1.0 - np.clip(x.to_numpy(dtype=float), 0.0, 1.0))),
            ),
            realized_monthly_abandon_rate=(
                "realized_weekly_abandon_rate",
                lambda x: float(1.0 - np.prod(1.0 - np.clip(x.to_numpy(dtype=float), 0.0, 1.0))),
            ),
            monthly_withdrawals=("weekly_withdrawals", "sum"),
            mean_active_wealth=("mean_active_wealth", "last"),
            mean_active_gain=("mean_active_gain", "last"),
            mean_active_loss=("mean_active_loss", "last"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "last"),
            company_revenue_active_mean=("company_revenue_active_mean", "last"),
            **{col: (col, "last") for col in LOSS_COLS},
        )
    )
    summary = (
        detail.groupby(["modelo", "scenario", "portfolio", "panorama_retorno", "month", "week_end"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            active_clients_mean=("active_clients", "mean"),
            active_clients_total=("active_clients", "sum"),
            p_accept_rebalance=("p_accept_rebalance", "mean"),
            monthly_abandon_probability=("monthly_abandon_probability", "mean"),
            realized_monthly_abandon_rate=("realized_monthly_abandon_rate", "mean"),
            monthly_withdrawals_mean=("monthly_withdrawals", "mean"),
            mean_active_wealth=("mean_active_wealth", "mean"),
            mean_active_gain=("mean_active_gain", "mean"),
            mean_active_loss=("mean_active_loss", "mean"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "mean"),
            company_revenue_active_mean=("company_revenue_active_mean", "mean"),
            **{col: (col, "mean") for col in LOSS_COLS},
        )
        .sort_values(["modelo", "scenario", "portfolio", "panorama_retorno", "month"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_semiannual_behavior(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    detail = (
        timeline.sort_values(["modelo", "scenario", "portfolio", "panorama_retorno", "window_id", "semester", "week"])
        .groupby(["modelo", "scenario", "portfolio", "panorama_retorno", "window_id", "semester"], as_index=False)
        .agg(
            week_end=("week", "max"),
            active_clients=("active_clients", "last"),
            mean_active_wealth=("mean_active_wealth", "last"),
            mean_active_gain=("mean_active_gain", "last"),
            mean_active_loss=("mean_active_loss", "last"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "last"),
            company_revenue_active_mean=("company_revenue_active_mean", "last"),
            **{col: (col, "last") for col in LOSS_COLS},
        )
    )
    summary = (
        detail.groupby(["modelo", "scenario", "portfolio", "panorama_retorno", "semester", "week_end"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            active_clients_mean=("active_clients", "mean"),
            mean_active_wealth=("mean_active_wealth", "mean"),
            mean_active_gain=("mean_active_gain", "mean"),
            mean_active_loss=("mean_active_loss", "mean"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "mean"),
            company_revenue_active_mean=("company_revenue_active_mean", "mean"),
            **{col: (col, "mean") for col in LOSS_COLS},
        )
        .sort_values(["modelo", "scenario", "portfolio", "panorama_retorno", "semester"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def main() -> None:
    start = time.perf_counter()
    log("Preparando insumo P4 base y panoramas proyectados")
    p4_input = prepare_p4_input()
    p4_input.to_csv(INPUT_DIR / "p4_input_panoramas.csv", index=False)

    log(f"Ejecutando Monte Carlo P4 para {len(p4_input)} combinaciones")
    p4, weekly = simulate_p4_panoramas(p4_input)
    p4.to_csv(TEST_DIR / "p4_test_limpio_detalle.csv", index=False)
    weekly.to_csv(BEHAVIOR_DIR / "weekly_behavior_timeseries_detail.csv", index=False)

    p4_summary = summarize_p4(p4, TEST_DIR / "p4_test_limpio_resumen.csv")
    behavior_summary = summarize_behavior(p4, BEHAVIOR_DIR / "behavior_probabilities_clients_summary.csv")
    p4.to_csv(BEHAVIOR_DIR / "behavior_probabilities_clients_detail.csv", index=False)
    weekly_summary = summarize_weekly_behavior(weekly, BEHAVIOR_DIR / "weekly_behavior_timeseries_summary.csv")
    monthly_summary = summarize_monthly_behavior(weekly, BEHAVIOR_DIR / "monthly_behavior_timeseries_summary.csv")
    semiannual_summary = summarize_semiannual_behavior(weekly, BEHAVIOR_DIR / "semiannual_gain_timeseries_summary.csv")

    checks = {
        "input_base_rows": int(len(pd.read_csv(BASE_P4_INPUT))),
        "input_panoramas_rows": int(len(p4_input)),
        "p4_rows": int(len(p4)),
        "p4_summary_rows": int(len(p4_summary)),
        "behavior_rows": int(len(behavior_summary)),
        "weekly_rows": int(len(weekly_summary)),
        "monthly_rows": int(len(monthly_summary)),
        "semiannual_rows": int(len(semiannual_summary)),
        "panoramas": ",".join(sorted(p4["panorama_retorno"].unique())),
        "elapsed_seconds": round(time.perf_counter() - start, 1),
    }
    pd.DataFrame([checks]).to_csv(OUTPUT_DIR / "99_checks_panoramas.csv", index=False)
    log(f"Listo en {checks['elapsed_seconds']}s. Outputs en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
