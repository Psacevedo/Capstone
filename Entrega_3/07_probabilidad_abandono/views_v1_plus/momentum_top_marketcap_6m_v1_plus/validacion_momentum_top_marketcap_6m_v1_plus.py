"""
Validacion de Black-Litterman con tres horizontes temporales para FinPUC.

Este script vive en una carpeta segura y no modifica los scripts originales.
Parte desde la copia local `calibracion_secuencial_bl_base_copiada.py` y agrega:

1. Rolling windows cronologicas.
2. Separacion estricta de roles: calibracion, validacion y test_p4.
3. Calibracion secuencial solo con ventanas de calibracion.
4. Validacion de parametros congelados en ventanas no vistas.
5. Test limpio para Monte Carlo P4.
6. Metricas de dinamica del portafolio:
   turnover semestral, estabilidad inicial-final y concentracion sectorial.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

import calibracion_secuencial_bl_base_copiada as base


WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs"
CALIB_DIR = OUTPUT_DIR / "calibration"
VALIDATION_DIR = OUTPUT_DIR / "validation"
TEST_DIR = OUTPUT_DIR / "test_p4"
DYNAMICS_DIR = OUTPUT_DIR / "portfolio_dynamics"
BEHAVIOR_DIR = OUTPUT_DIR / "behavior"
for directory in [OUTPUT_DIR, CALIB_DIR, VALIDATION_DIR, TEST_DIR, DYNAMICS_DIR, BEHAVIOR_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

HISTORICAL_YEARS = 7
FUTURE_YEARS = 2
REBALANCE_DAYS = base.REBALANCE_DAYS
ROLLING_STEP_DAYS = 63
CALIBRATION_SHARE = 0.60
VALIDATION_SHARE = 0.20
TOP_K_OVERLAP = 10
RNG_SEED_P4 = 20260611
REBALANCE_WEEKS = 26
MONTH_WEEKS = 4
RUIN_WEALTH = 0.0
COMPANY_MONTHLY_FEE_RATE = 0.005
COMPANY_WEEKLY_FEE_RATE = COMPANY_MONTHLY_FEE_RATE * 12.0 / 52.0
ABANDONMENT_VERSION = "v1_plus"
ABANDONMENT_FORMULA = "threshold_logistic_unscaled_with_ruin"

ROLE_CALIBRATION = "calibracion"
ROLE_VALIDATION = "validacion"
ROLE_TEST = "test_p4"
FORCED_VIEW_KEY = "momentum_top_marketcap_6m"
FORCED_VIEW_CONFIG_IDS = {
    "desempleo_macro": "stage1_desempleo",
    "momentum_general": "stage1_momentum",
    "momentum_top_marketcap_6m": "stage1_mcap20_6m",
    "momentum_top_bottom_1y": "stage1_mcap40_1y",
}


def stage1_configs_for_view() -> List[base.ViewConfig]:
    """Devuelve la familia de view que se calibra en esta iteracion comparativa."""
    target_id = FORCED_VIEW_CONFIG_IDS[FORCED_VIEW_KEY]
    configs = [config for config in base.BASE_VIEW_CONFIGS if config.config_id == target_id]
    if len(configs) != 1:
        raise ValueError(f"No se encontro una unica configuracion stage1 para {FORCED_VIEW_KEY}.")
    return configs


@dataclass(frozen=True)
class WindowSpec:
    scenario: str
    window_id: str
    role: str
    start_idx: int
    train_end_idx: int
    test_end_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def log(message: str) -> None:
    print(f"[BL-3H] {message}", flush=True)


def pctile_10(x: pd.Series) -> float:
    return float(x.quantile(0.10))


def pctile_25(x: pd.Series) -> float:
    return float(x.quantile(0.25))


def generate_rolling_windows(
    returns: pd.DataFrame,
    scenario: str,
    historical_years: int = HISTORICAL_YEARS,
    future_years: int = FUTURE_YEARS,
    step_days: int = ROLLING_STEP_DAYS,
) -> List[WindowSpec]:
    """Genera ventanas h7_f2 desplazadas cronologicamente.

    El paso se fija en 63 dias habiles para obtener al menos tres roles incluso
    en la base sin pandemia, que tiene menos observaciones que la base completa.
    El rebalanceo interno sigue siendo semestral.
    """
    historical_days = int(historical_years * base.TRADING_DAYS)
    future_days = int(future_years * base.TRADING_DAYS)
    total_days = historical_days + future_days
    max_start = len(returns) - total_days
    if max_start < 0:
        raise ValueError(f"{scenario}: observaciones insuficientes para h{historical_years}_f{future_years}")

    starts = list(range(0, max_start + 1, step_days))
    if starts[-1] != max_start:
        starts.append(max_start)

    raw_windows: List[Tuple[int, int, int]] = []
    for start in starts:
        train_end = start + historical_days
        test_end = train_end + future_days
        raw_windows.append((start, train_end, test_end))

    n = len(raw_windows)
    if n < 3:
        raise ValueError(f"{scenario}: se requieren al menos 3 ventanas para separar calibracion/validacion/test")

    cal_end = max(1, int(math.floor(n * CALIBRATION_SHARE)))
    val_end = max(cal_end + 1, int(math.floor(n * (CALIBRATION_SHARE + VALIDATION_SHARE))))
    if val_end >= n:
        val_end = n - 1

    windows: List[WindowSpec] = []
    for j, (start, train_end, test_end) in enumerate(raw_windows):
        if j < cal_end:
            role = ROLE_CALIBRATION
        elif j < val_end:
            role = ROLE_VALIDATION
        else:
            role = ROLE_TEST
        train_index = returns.index[start:train_end]
        test_index = returns.index[train_end:test_end]
        windows.append(
            WindowSpec(
                scenario=scenario,
                window_id=f"{scenario}_w{j:02d}",
                role=role,
                start_idx=start,
                train_end_idx=train_end,
                test_end_idx=test_end,
                train_start=str(train_index.min().date()),
                train_end=str(train_index.max().date()),
                test_start=str(test_index.min().date()),
                test_end=str(test_index.max().date()),
            )
        )
    return windows


def write_windows_roles(datasets: Dict[str, pd.DataFrame]) -> List[WindowSpec]:
    all_windows: List[WindowSpec] = []
    for scenario, returns in datasets.items():
        scenario_windows = generate_rolling_windows(returns, scenario)
        all_windows.extend(scenario_windows)
    rows = [w.__dict__ for w in all_windows]
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "00_windows_roles.csv", index=False)
    return all_windows


def split_from_window(returns: pd.DataFrame, window: WindowSpec) -> Tuple[pd.DataFrame, pd.DataFrame]:
    historical = returns.iloc[window.start_idx : window.train_end_idx]
    future = returns.iloc[window.train_end_idx : window.test_end_idx]
    return historical, future


def drift_weights(weights: np.ndarray, test_returns: pd.DataFrame) -> np.ndarray:
    gross = (1.0 + test_returns).prod(axis=0).to_numpy(dtype=float)
    drifted = weights * gross
    total = drifted.sum()
    if not np.isfinite(total) or total <= 0:
        return weights.copy()
    return drifted / total


def sector_weights(weights: np.ndarray, tickers: Sequence[str], meta: pd.DataFrame) -> pd.Series:
    sectors = meta.set_index("ticker").reindex(tickers)["sector"].fillna("Sin sector")
    df = pd.DataFrame({"sector": sectors.to_numpy(), "weight": weights})
    return df.groupby("sector")["weight"].sum().sort_values(ascending=False)


def append_weight_rows(
    rows: List[Dict[str, object]],
    metadata: Dict[str, object],
    tickers: Sequence[str],
    weights: np.ndarray,
    meta: pd.DataFrame,
) -> None:
    meta_idx = meta.set_index("ticker").reindex(tickers)
    sectors = meta_idx["sector"].fillna("Sin sector")
    market_caps = meta_idx["marketCap"].fillna(0.0)
    for ticker, weight in zip(tickers, weights):
        rows.append(
            {
                **metadata,
                "ticker": ticker,
                "sector": sectors.loc[ticker],
                "marketCap": float(market_caps.loc[ticker]),
                "weight": float(weight),
            }
        )


def evaluate_config_on_windows(
    datasets: Dict[str, pd.DataFrame],
    meta: pd.DataFrame,
    config: Optional[base.ViewConfig],
    profiles: Sequence[base.RiskProfile],
    windows: Sequence[WindowSpec],
    stage: str,
    model_label: str,
    collect_dynamics: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evalua una configuracion sobre una lista explicita de ventanas."""
    metric_rows: List[Dict[str, object]] = []
    view_rows: List[Dict[str, object]] = []
    weight_rows: List[Dict[str, object]] = []
    rebalance_rows: List[Dict[str, object]] = []
    sector_return_rows: List[Dict[str, object]] = []
    config_id = config.config_id if config else "markowitz_base"

    for window in windows:
        returns = datasets[window.scenario]
        historical, future = split_from_window(returns, window)
        tickers = list(historical.columns)
        combined_returns: Dict[str, List[pd.Series]] = {p.label: [] for p in profiles}
        previous_weights: Dict[str, np.ndarray] = {}
        previous_tests: Dict[str, pd.DataFrame] = {}
        notes: Dict[str, str] = {}

        for segment_id, train, test in base.rebalance_segments(historical, future):
            mu_model, sigma_model, view_record = base.black_litterman_model(train, meta, config)
            view_record.update(
                {
                    "stage": stage,
                    "modelo": model_label,
                    "config_id": config_id,
                    "scenario": window.scenario,
                    "window_id": window.window_id,
                    "window_role": window.role,
                    "segment_id": segment_id,
                    "train_start": str(train.index.min().date()),
                    "train_end": str(train.index.max().date()),
                    "test_start": str(test.index.min().date()),
                    "test_end": str(test.index.max().date()),
                }
            )
            view_rows.append(view_record)

            for profile in profiles:
                weights, note = base.optimize_profile(mu_model, sigma_model, profile)
                notes[profile.label] = note
                segment_returns = base.portfolio_returns(test, weights)
                combined_returns[profile.label].append(segment_returns)

                if collect_dynamics:
                    turnover = np.nan
                    if profile.label in previous_weights:
                        drifted = drift_weights(previous_weights[profile.label], previous_tests[profile.label])
                        turnover = 0.5 * float(np.abs(weights - drifted).sum())
                    hhi = float(np.square(weights).sum())
                    n_eff = 1.0 / hhi if hhi > 1e-12 else np.nan
                    sector_w = sector_weights(weights, tickers, meta)
                    sector_hhi = float(np.square(sector_w.to_numpy()).sum())
                    top_sector = str(sector_w.index[0]) if len(sector_w) else ""
                    top_sector_weight = float(sector_w.iloc[0]) if len(sector_w) else np.nan
                    common_meta = {
                        "stage": stage,
                        "modelo": model_label,
                        "config_id": config_id,
                        "scenario": window.scenario,
                        "window_id": window.window_id,
                        "window_role": window.role,
                        "portfolio": profile.label,
                        "profile_key": profile.key,
                        "segment_id": segment_id,
                        "rebalance_date": str(test.index.min().date()),
                        "test_start": str(test.index.min().date()),
                        "test_end": str(test.index.max().date()),
                    }
                    rebalance_rows.append(
                        {
                            **common_meta,
                            "turnover": turnover,
                            "hhi_assets": hhi,
                            "n_effective_assets": n_eff,
                            "max_weight": float(weights.max()),
                            "sector_hhi": sector_hhi,
                            "top_sector": top_sector,
                            "top_sector_weight": top_sector_weight,
                        }
                    )
                    append_weight_rows(weight_rows, common_meta, tickers, weights, meta)
                    sector_series = pd.Series(0.0, index=sorted(meta["sector"].fillna("Sin sector").unique()))
                    sectors = meta.set_index("ticker").reindex(tickers)["sector"].fillna("Sin sector")
                    weighted_asset_returns = test.to_numpy(dtype=float) * weights.reshape(1, -1)
                    contrib_df = pd.DataFrame(weighted_asset_returns, columns=tickers, index=test.index)
                    for sector, sector_tickers in sectors.groupby(sectors).groups.items():
                        cols = [t for t in sector_tickers if t in contrib_df.columns]
                        if cols:
                            sector_series.loc[sector] = float(contrib_df[cols].sum(axis=1).sum())
                    abs_total = float(np.abs(sector_series).sum())
                    for sector, contribution in sector_series.items():
                        sector_return_rows.append(
                            {
                                **common_meta,
                                "sector": sector,
                                "return_contribution": float(contribution),
                                "abs_return_contribution": abs(float(contribution)),
                                "share_abs_return_contribution": abs(float(contribution)) / abs_total if abs_total > 0 else np.nan,
                            }
                        )

                    previous_weights[profile.label] = weights
                    previous_tests[profile.label] = test

        for profile in profiles:
            realised_returns = pd.concat(combined_returns[profile.label]).sort_index()
            metrics = base.metrics_from_returns(realised_returns)
            row = {
                "stage": stage,
                "modelo": model_label,
                "config_id": config_id,
                "view_label": config.view_label if config else "Markowitz base",
                "family": config.family if config else "markowitz",
                "scenario": window.scenario,
                "window_id": window.window_id,
                "window_role": window.role,
                "train_start": window.train_start,
                "train_end": window.train_end,
                "test_start": window.test_start,
                "test_end": window.test_end,
                "portfolio": profile.label,
                "profile_key": profile.key,
                "optimizer_note": notes.get(profile.label, ""),
            }
            if config:
                row.update(base.config_to_record(config))
            row.update(metrics)
            metric_rows.append(row)

    return (
        pd.DataFrame(metric_rows),
        pd.DataFrame(view_rows),
        pd.DataFrame(weight_rows),
        pd.DataFrame(rebalance_rows),
        pd.DataFrame(sector_return_rows),
    )


def score_candidates_rolling(df: pd.DataFrame, base_df: pd.DataFrame, stage: str) -> pd.DataFrame:
    merge_cols = ["scenario", "window_id", "window_role", "portfolio"]
    merged = df.merge(
        base_df[
            merge_cols + ["sharpe", "retorno_anual", "max_drawdown", "cvar_95_diario"]
        ].rename(
            columns={
                "sharpe": "base_sharpe",
                "retorno_anual": "base_retorno_anual",
                "max_drawdown": "base_drawdown",
                "cvar_95_diario": "base_cvar",
            }
        ),
        on=merge_cols,
        how="left",
    )
    merged["delta_sharpe_vs_markowitz"] = merged["sharpe"] - merged["base_sharpe"]
    merged["delta_retorno_vs_markowitz"] = merged["retorno_anual"] - merged["base_retorno_anual"]
    merged["delta_drawdown_vs_markowitz"] = merged["max_drawdown"] - merged["base_drawdown"]
    merged["delta_cvar_vs_markowitz"] = merged["cvar_95_diario"] - merged["base_cvar"]
    merged.to_csv(CALIB_DIR / f"{stage}_detalle_vs_markowitz.csv", index=False)

    group_cols = ["config_id", "view_label", "family"]
    optional_cols = [
        "lookback_days",
        "top_bottom_size",
        "market_cap_universe_size",
        "long_short_size",
        "p_weighting",
        "q_scale",
        "confidence",
        "tau",
        "unemployment_assumed",
        "macro_beta",
    ]
    group_cols += [c for c in optional_cols if c in merged.columns]
    summary = (
        merged.groupby(group_cols, dropna=False)
        .agg(
            sharpe_mean=("sharpe", "mean"),
            sharpe_std=("sharpe", "std"),
            sharpe_p10=("sharpe", pctile_10),
            sharpe_p25=("sharpe", pctile_25),
            retorno_anual_mean=("retorno_anual", "mean"),
            drawdown_mean=("max_drawdown", "mean"),
            worst_drawdown=("max_drawdown", "min"),
            cvar_mean=("cvar_95_diario", "mean"),
            delta_sharpe_mean=("delta_sharpe_vs_markowitz", "mean"),
            delta_drawdown_mean=("delta_drawdown_vs_markowitz", "mean"),
            pct_windows_beats_sharpe=("delta_sharpe_vs_markowitz", lambda x: float((x > 0).mean())),
            pct_windows_beats_drawdown=("delta_drawdown_vs_markowitz", lambda x: float((x > 0).mean())),
            n_obs=("sharpe", "count"),
        )
        .reset_index()
    )
    summary["sharpe_std"] = summary["sharpe_std"].fillna(0.0)
    summary["score_robusto"] = base.robust_score(summary)
    summary = summary.sort_values("score_robusto", ascending=False).reset_index(drop=True)
    summary.to_csv(CALIB_DIR / f"{stage}_ranking.csv", index=False)
    return summary


def run_stage_rolling(
    name: str,
    configs: Sequence[base.ViewConfig],
    datasets: Dict[str, pd.DataFrame],
    meta: pd.DataFrame,
    markowitz_base: pd.DataFrame,
    calibration_windows: Sequence[WindowSpec],
    profiles: Sequence[base.RiskProfile],
) -> Tuple[base.ViewConfig, pd.DataFrame, pd.DataFrame]:
    frames = []
    views = []
    for ix, config in enumerate(configs, start=1):
        log(f"{name}: {ix}/{len(configs)} {config.config_id}")
        df, view_df, _, _, _ = evaluate_config_on_windows(
            datasets,
            meta,
            config,
            profiles,
            calibration_windows,
            name,
            "BL candidato",
            collect_dynamics=False,
        )
        frames.append(df)
        views.append(view_df)
    stage_df = pd.concat(frames, ignore_index=True)
    stage_views = pd.concat(views, ignore_index=True)
    stage_df.to_csv(CALIB_DIR / f"{name}_resultados.csv", index=False)
    stage_views.to_csv(CALIB_DIR / f"{name}_views_segmentos.csv", index=False)
    ranking = score_candidates_rolling(stage_df, markowitz_base, name)
    winner_id = ranking.iloc[0]["config_id"]
    winner = next(c for c in configs if c.config_id == winner_id)
    log(f"{name}: ganador {winner.config_id}, score={ranking.iloc[0]['score_robusto']:.3f}")
    return winner, stage_df, ranking


def aggregate_window_metrics(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        df.groupby(["window_role", "modelo", "scenario", "portfolio"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            sharpe_mean=("sharpe", "mean"),
            sharpe_median=("sharpe", "median"),
            sharpe_p10=("sharpe", pctile_10),
            sharpe_p25=("sharpe", pctile_25),
            sharpe_min=("sharpe", "min"),
            sharpe_std=("sharpe", "std"),
            retorno_anual_mean=("retorno_anual", "mean"),
            drawdown_mean=("max_drawdown", "mean"),
            worst_drawdown=("max_drawdown", "min"),
            cvar_mean=("cvar_95_diario", "mean"),
            volatilidad_anual_mean=("volatilidad_anual", "mean"),
        )
        .fillna({"sharpe_std": 0.0})
    )
    summary.to_csv(out_path, index=False)
    return summary


def compare_against_markowitz(bl: pd.DataFrame, mk: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    merge_cols = ["window_role", "scenario", "window_id", "portfolio"]
    comparison = bl.merge(
        mk[
            merge_cols + ["sharpe", "retorno_anual", "max_drawdown", "cvar_95_diario", "volatilidad_anual"]
        ].rename(
            columns={
                "sharpe": "sharpe_markowitz",
                "retorno_anual": "retorno_anual_markowitz",
                "max_drawdown": "drawdown_markowitz",
                "cvar_95_diario": "cvar_markowitz",
                "volatilidad_anual": "volatilidad_markowitz",
            }
        ),
        on=merge_cols,
        how="left",
    )
    comparison["mejora_pct_sharpe_vs_markowitz"] = (
        (comparison["sharpe"] - comparison["sharpe_markowitz"])
        / comparison["sharpe_markowitz"].abs().replace(0, np.nan)
    )
    comparison["delta_drawdown_vs_markowitz"] = comparison["max_drawdown"] - comparison["drawdown_markowitz"]
    comparison["delta_cvar_vs_markowitz"] = comparison["cvar_95_diario"] - comparison["cvar_markowitz"]
    comparison["recomendacion"] = np.where(
        (comparison["mejora_pct_sharpe_vs_markowitz"] > 0)
        & (comparison["delta_drawdown_vs_markowitz"] > -0.03),
        "Recomendado",
        "No dominante",
    )
    comparison.to_csv(out_path, index=False)
    return comparison


def summarize_comparison(comparison: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        comparison.groupby(["window_role", "scenario", "portfolio"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            sharpe_bl_mean=("sharpe", "mean"),
            sharpe_mk_mean=("sharpe_markowitz", "mean"),
            mejora_pct_sharpe_mean=("mejora_pct_sharpe_vs_markowitz", "mean"),
            drawdown_bl_mean=("max_drawdown", "mean"),
            drawdown_mk_mean=("drawdown_markowitz", "mean"),
            delta_drawdown_mean=("delta_drawdown_vs_markowitz", "mean"),
            pct_recomendado=("recomendacion", lambda x: float((x == "Recomendado").mean())),
        )
    )
    summary.to_csv(out_path, index=False)
    return summary


def composition_stability(weights_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    group_cols = ["modelo", "window_role", "scenario", "window_id", "portfolio"]
    if weights_df.empty:
        pd.DataFrame().to_csv(out_path, index=False)
        return pd.DataFrame()

    for keys, group in weights_df.groupby(group_cols):
        group = group.sort_values(["segment_id", "ticker"])
        first_segment = int(group["segment_id"].min())
        last_segment = int(group["segment_id"].max())
        first = group[group["segment_id"] == first_segment].set_index("ticker")["weight"]
        last = group[group["segment_id"] == last_segment].set_index("ticker")["weight"]
        tickers = first.index.union(last.index)
        first = first.reindex(tickers).fillna(0.0)
        last = last.reindex(tickers).fillna(0.0)
        top_first = set(first.sort_values(ascending=False).head(TOP_K_OVERLAP).index)
        top_last = set(last.sort_values(ascending=False).head(TOP_K_OVERLAP).index)
        rows.append(
            {
                "modelo": keys[0],
                "window_role": keys[1],
                "scenario": keys[2],
                "window_id": keys[3],
                "portfolio": keys[4],
                "distance_l1_initial_final": 0.5 * float(np.abs(last - first).sum()),
                "top10_overlap_initial_final": len(top_first & top_last) / TOP_K_OVERLAP,
                "hhi_initial": float(np.square(first).sum()),
                "hhi_final": float(np.square(last).sum()),
                "n_effective_initial": 1.0 / float(np.square(first).sum()),
                "n_effective_final": 1.0 / float(np.square(last).sum()),
                "max_weight_initial": float(first.max()),
                "max_weight_final": float(last.max()),
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(out_path, index=False)
    return result


def summarize_sector_returns(sector_df: pd.DataFrame, out_path_detail: Path, out_path_summary: Path) -> pd.DataFrame:
    if sector_df.empty:
        pd.DataFrame().to_csv(out_path_detail, index=False)
        pd.DataFrame().to_csv(out_path_summary, index=False)
        return pd.DataFrame()

    group_cols = ["modelo", "window_role", "scenario", "window_id", "portfolio", "sector"]
    detail = (
        sector_df.groupby(group_cols, as_index=False)
        .agg(return_contribution=("return_contribution", "sum"))
    )
    totals = detail.groupby(["modelo", "window_role", "scenario", "window_id", "portfolio"])["return_contribution"].transform(
        lambda x: np.abs(x).sum()
    )
    detail["abs_return_contribution"] = detail["return_contribution"].abs()
    detail["share_abs_return_contribution"] = np.where(
        totals > 0,
        detail["abs_return_contribution"] / totals,
        np.nan,
    )
    detail.to_csv(out_path_detail, index=False)

    rows = []
    for keys, group in detail.groupby(["modelo", "window_role", "scenario", "window_id", "portfolio"]):
        ordered = group.sort_values("share_abs_return_contribution", ascending=False)
        rows.append(
            {
                "modelo": keys[0],
                "window_role": keys[1],
                "scenario": keys[2],
                "window_id": keys[3],
                "portfolio": keys[4],
                "top_sector": ordered.iloc[0]["sector"] if len(ordered) else "",
                "top_sector_share_abs_return": float(ordered.iloc[0]["share_abs_return_contribution"]) if len(ordered) else np.nan,
                "top3_sector_share_abs_return": float(ordered.head(3)["share_abs_return_contribution"].sum()),
                "n_sectors_active_return": int((ordered["abs_return_contribution"] > 1e-10).sum()),
            }
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(out_path_summary, index=False)
    return summary


def summarize_rebalance_dynamics(rebalance_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    if rebalance_df.empty:
        pd.DataFrame().to_csv(out_path, index=False)
        return pd.DataFrame()
    summary = (
        rebalance_df.groupby(["modelo", "window_role", "scenario", "portfolio"], as_index=False)
        .agg(
            n_rebalances=("segment_id", "count"),
            turnover_mean=("turnover", "mean"),
            turnover_median=("turnover", "median"),
            turnover_max=("turnover", "max"),
            pct_turnover_gt_20=("turnover", lambda x: float((x > 0.20).mean())),
            pct_turnover_gt_40=("turnover", lambda x: float((x > 0.40).mean())),
            hhi_assets_mean=("hhi_assets", "mean"),
            n_effective_assets_mean=("n_effective_assets", "mean"),
            max_weight_mean=("max_weight", "mean"),
            sector_hhi_mean=("sector_hhi", "mean"),
            top_sector_weight_mean=("top_sector_weight", "mean"),
        )
    )
    summary.to_csv(out_path, index=False)
    return summary


def simulate_p4_clean(metrics_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    weekly_rows: List[Dict[str, object]] = []
    rng = np.random.default_rng(RNG_SEED_P4)
    for _, row in metrics_df.iterrows():
        profile = base.PROFILE_BY_LABEL[row["portfolio"]]
        ann_return = base.safe_float(row["retorno_anual"])
        ann_vol = max(base.safe_float(row["volatilidad_anual"]), 1e-6)
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

        for _week in range(base.N_WEEKS):
            week_number = int(_week + 1)
            if _week % MONTH_WEEKS == 0:
                month_start_wealth[active & ~withdrawn] = wealth[active & ~withdrawn]
            if _week % REBALANCE_WEEKS == 0:
                semester_start_wealth[active & ~withdrawn] = wealth[active & ~withdrawn]

            idx = active & ~withdrawn
            week_withdrawals = 0
            mean_weekly_p = 0.0
            realized_weekly_rate = 0.0
            loss_metrics = {col: 0.0 for col in ['loss_initial_pct', 'loss_initial_money', 'cumulative_loss_initial_week_pct', 'cumulative_loss_initial_week_money', 'cumulative_loss_initial_month_pct', 'cumulative_loss_initial_month_money', 'cumulative_loss_initial_semester_pct', 'cumulative_loss_initial_semester_money', 'period_loss_wealth_week_pct', 'period_loss_wealth_week_money', 'period_loss_wealth_month_pct', 'period_loss_wealth_month_money', 'period_loss_wealth_semester_pct', 'period_loss_wealth_semester_money', 'cumulative_period_loss_wealth_week_pct', 'cumulative_period_loss_wealth_week_money', 'cumulative_period_loss_wealth_month_pct', 'cumulative_period_loss_wealth_month_money', 'cumulative_period_loss_wealth_semester_pct', 'cumulative_period_loss_wealth_semester_money']}

            if idx.any():
                n_active_start = int(idx.sum())
                full_idx = np.where(idx)[0]
                wealth_start_week = wealth[idx].copy()
                wealth_start_month = month_start_wealth[idx].copy()
                wealth_start_semester = semester_start_wealth[idx].copy()

                rets = rng.normal(weekly_mu, weekly_sigma, n_active_start)
                wealth[idx] *= np.maximum(1.0 + rets, RUIN_WEALTH)
                # La utilidad de empresa depende solo del saldo administrado activo.
                # No se cobra comision adicional por aceptar rebalanceos/recomendaciones.
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
                    "loss_initial_pct": float(np.maximum((base.INITIAL_CAPITAL - wealth[active_end_mask]) / base.INITIAL_CAPITAL, 0.0).mean()) if active_end else 1.0,
                    "loss_initial_money": float(np.maximum(base.INITIAL_CAPITAL - wealth[active_end_mask], 0.0).mean()) if active_end else base.INITIAL_CAPITAL,
                    "cumulative_loss_initial_week_pct": float(cum_loss_initial_week_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_loss_initial_week_money": float(cum_loss_initial_week_money[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_loss_initial_month_pct": float(cum_loss_initial_month_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_loss_initial_month_money": float(cum_loss_initial_month_money[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_loss_initial_semester_pct": float(cum_loss_initial_semester_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_loss_initial_semester_money": float(cum_loss_initial_semester_money[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_week_pct": float(cum_period_loss_week_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_week_money": float(cum_period_loss_week_money[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_month_pct": float(cum_period_loss_month_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_month_money": float(cum_period_loss_month_money[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_semester_pct": float(cum_period_loss_semester_pct[active_end_mask].mean()) if active_end else 0.0,
                    "cumulative_period_loss_wealth_semester_money": float(cum_period_loss_semester_money[active_end_mask].mean()) if active_end else 0.0,
                }
            )
            company_revenue_cumulative_mean = float(company.mean())
            company_revenue_active_mean = float(company[active_end_mask].mean()) if active_end else 0.0
            weekly_rows.append(
                {
                    "modelo": row["modelo"],
                    "abandonment_version": ABANDONMENT_VERSION,
                    "abandonment_formula": ABANDONMENT_FORMULA,
                    "scenario": row["scenario"],
                    "window_id": row["window_id"],
                    "window_role": row["window_role"],
                    "portfolio": row["portfolio"],
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
                "window_id": row["window_id"],
                "window_role": row["window_role"],
                "portfolio": row["portfolio"],
                "retorno_anual_input": ann_return,
                "volatilidad_anual_input": ann_vol,
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
                "terminal_wealth_median": float(np.median(wealth)),
                "prob_profit": float((wealth > base.INITIAL_CAPITAL).mean()),
                "withdrawal_rate": float(withdrawn.mean()),
                "company_revenue_mean": float(company.mean()),
                "company_revenue_median": float(np.median(company)),
                "p4_score": float(wealth.mean() + company.mean() - base.INITIAL_CAPITAL * withdrawn.mean()),
                "p4_score_median": float(
                    np.median(wealth + company - base.INITIAL_CAPITAL * withdrawn.astype(float))
                ),
            }
        )
    p4 = pd.DataFrame(rows).sort_values("p4_score", ascending=False)
    weekly = pd.DataFrame(weekly_rows)
    return p4, weekly


def summarize_weekly_behavior(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        timeline.groupby(["modelo", "scenario", "portfolio", "week"], as_index=False)
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
            loss_initial_pct=("loss_initial_pct", "mean"),
            loss_initial_money=("loss_initial_money", "mean"),
            cumulative_loss_initial_week_pct=("cumulative_loss_initial_week_pct", "mean"),
            cumulative_loss_initial_week_money=("cumulative_loss_initial_week_money", "mean"),
            cumulative_loss_initial_month_pct=("cumulative_loss_initial_month_pct", "mean"),
            cumulative_loss_initial_month_money=("cumulative_loss_initial_month_money", "mean"),
            cumulative_loss_initial_semester_pct=("cumulative_loss_initial_semester_pct", "mean"),
            cumulative_loss_initial_semester_money=("cumulative_loss_initial_semester_money", "mean"),
            period_loss_wealth_week_pct=("period_loss_wealth_week_pct", "mean"),
            period_loss_wealth_week_money=("period_loss_wealth_week_money", "mean"),
            period_loss_wealth_month_pct=("period_loss_wealth_month_pct", "mean"),
            period_loss_wealth_month_money=("period_loss_wealth_month_money", "mean"),
            period_loss_wealth_semester_pct=("period_loss_wealth_semester_pct", "mean"),
            period_loss_wealth_semester_money=("period_loss_wealth_semester_money", "mean"),
            cumulative_period_loss_wealth_week_pct=("cumulative_period_loss_wealth_week_pct", "mean"),
            cumulative_period_loss_wealth_week_money=("cumulative_period_loss_wealth_week_money", "mean"),
            cumulative_period_loss_wealth_month_pct=("cumulative_period_loss_wealth_month_pct", "mean"),
            cumulative_period_loss_wealth_month_money=("cumulative_period_loss_wealth_month_money", "mean"),
            cumulative_period_loss_wealth_semester_pct=("cumulative_period_loss_wealth_semester_pct", "mean"),
            cumulative_period_loss_wealth_semester_money=("cumulative_period_loss_wealth_semester_money", "mean"),
        )
        .sort_values(["modelo", "scenario", "portfolio", "week"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_monthly_behavior(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    detail = (
        timeline.sort_values(["modelo", "scenario", "portfolio", "window_id", "month", "week"])
        .groupby(["modelo", "scenario", "portfolio", "window_id", "month"], as_index=False)
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
            loss_initial_pct=("loss_initial_pct", "last"),
            loss_initial_money=("loss_initial_money", "last"),
            cumulative_loss_initial_week_pct=("cumulative_loss_initial_week_pct", "last"),
            cumulative_loss_initial_week_money=("cumulative_loss_initial_week_money", "last"),
            cumulative_loss_initial_month_pct=("cumulative_loss_initial_month_pct", "last"),
            cumulative_loss_initial_month_money=("cumulative_loss_initial_month_money", "last"),
            cumulative_loss_initial_semester_pct=("cumulative_loss_initial_semester_pct", "last"),
            cumulative_loss_initial_semester_money=("cumulative_loss_initial_semester_money", "last"),
            period_loss_wealth_week_pct=("period_loss_wealth_week_pct", "last"),
            period_loss_wealth_week_money=("period_loss_wealth_week_money", "last"),
            period_loss_wealth_month_pct=("period_loss_wealth_month_pct", "last"),
            period_loss_wealth_month_money=("period_loss_wealth_month_money", "last"),
            period_loss_wealth_semester_pct=("period_loss_wealth_semester_pct", "last"),
            period_loss_wealth_semester_money=("period_loss_wealth_semester_money", "last"),
            cumulative_period_loss_wealth_week_pct=("cumulative_period_loss_wealth_week_pct", "last"),
            cumulative_period_loss_wealth_week_money=("cumulative_period_loss_wealth_week_money", "last"),
            cumulative_period_loss_wealth_month_pct=("cumulative_period_loss_wealth_month_pct", "last"),
            cumulative_period_loss_wealth_month_money=("cumulative_period_loss_wealth_month_money", "last"),
            cumulative_period_loss_wealth_semester_pct=("cumulative_period_loss_wealth_semester_pct", "last"),
            cumulative_period_loss_wealth_semester_money=("cumulative_period_loss_wealth_semester_money", "last"),
        )
    )
    summary = (
        detail.groupby(["modelo", "scenario", "portfolio", "month", "week_end"], as_index=False)
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
            loss_initial_pct=("loss_initial_pct", "mean"),
            loss_initial_money=("loss_initial_money", "mean"),
            cumulative_loss_initial_week_pct=("cumulative_loss_initial_week_pct", "mean"),
            cumulative_loss_initial_week_money=("cumulative_loss_initial_week_money", "mean"),
            cumulative_loss_initial_month_pct=("cumulative_loss_initial_month_pct", "mean"),
            cumulative_loss_initial_month_money=("cumulative_loss_initial_month_money", "mean"),
            cumulative_loss_initial_semester_pct=("cumulative_loss_initial_semester_pct", "mean"),
            cumulative_loss_initial_semester_money=("cumulative_loss_initial_semester_money", "mean"),
            period_loss_wealth_week_pct=("period_loss_wealth_week_pct", "mean"),
            period_loss_wealth_week_money=("period_loss_wealth_week_money", "mean"),
            period_loss_wealth_month_pct=("period_loss_wealth_month_pct", "mean"),
            period_loss_wealth_month_money=("period_loss_wealth_month_money", "mean"),
            period_loss_wealth_semester_pct=("period_loss_wealth_semester_pct", "mean"),
            period_loss_wealth_semester_money=("period_loss_wealth_semester_money", "mean"),
            cumulative_period_loss_wealth_week_pct=("cumulative_period_loss_wealth_week_pct", "mean"),
            cumulative_period_loss_wealth_week_money=("cumulative_period_loss_wealth_week_money", "mean"),
            cumulative_period_loss_wealth_month_pct=("cumulative_period_loss_wealth_month_pct", "mean"),
            cumulative_period_loss_wealth_month_money=("cumulative_period_loss_wealth_month_money", "mean"),
            cumulative_period_loss_wealth_semester_pct=("cumulative_period_loss_wealth_semester_pct", "mean"),
            cumulative_period_loss_wealth_semester_money=("cumulative_period_loss_wealth_semester_money", "mean"),
        )
        .sort_values(["modelo", "scenario", "portfolio", "month"])
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_semiannual_gain(timeline: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    detail = (
        timeline.sort_values(["modelo", "scenario", "portfolio", "window_id", "semester", "week"])
        .groupby(["modelo", "scenario", "portfolio", "window_id", "semester"], as_index=False)
        .agg(
            week_end=("week", "max"),
            active_clients=("active_clients", "last"),
            mean_active_wealth=("mean_active_wealth", "last"),
            mean_active_gain=("mean_active_gain", "last"),
            mean_active_loss=("mean_active_loss", "last"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "last"),
            company_revenue_active_mean=("company_revenue_active_mean", "last"),
            loss_initial_pct=("loss_initial_pct", "last"),
            loss_initial_money=("loss_initial_money", "last"),
            cumulative_loss_initial_week_pct=("cumulative_loss_initial_week_pct", "last"),
            cumulative_loss_initial_week_money=("cumulative_loss_initial_week_money", "last"),
            cumulative_loss_initial_month_pct=("cumulative_loss_initial_month_pct", "last"),
            cumulative_loss_initial_month_money=("cumulative_loss_initial_month_money", "last"),
            cumulative_loss_initial_semester_pct=("cumulative_loss_initial_semester_pct", "last"),
            cumulative_loss_initial_semester_money=("cumulative_loss_initial_semester_money", "last"),
            period_loss_wealth_week_pct=("period_loss_wealth_week_pct", "last"),
            period_loss_wealth_week_money=("period_loss_wealth_week_money", "last"),
            period_loss_wealth_month_pct=("period_loss_wealth_month_pct", "last"),
            period_loss_wealth_month_money=("period_loss_wealth_month_money", "last"),
            period_loss_wealth_semester_pct=("period_loss_wealth_semester_pct", "last"),
            period_loss_wealth_semester_money=("period_loss_wealth_semester_money", "last"),
            cumulative_period_loss_wealth_week_pct=("cumulative_period_loss_wealth_week_pct", "last"),
            cumulative_period_loss_wealth_week_money=("cumulative_period_loss_wealth_week_money", "last"),
            cumulative_period_loss_wealth_month_pct=("cumulative_period_loss_wealth_month_pct", "last"),
            cumulative_period_loss_wealth_month_money=("cumulative_period_loss_wealth_month_money", "last"),
            cumulative_period_loss_wealth_semester_pct=("cumulative_period_loss_wealth_semester_pct", "last"),
            cumulative_period_loss_wealth_semester_money=("cumulative_period_loss_wealth_semester_money", "last"),
        )
    )
    summary = (
        detail.groupby(["modelo", "scenario", "portfolio", "semester", "week_end"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            active_clients_mean=("active_clients", "mean"),
            mean_active_wealth=("mean_active_wealth", "mean"),
            mean_active_gain=("mean_active_gain", "mean"),
            mean_active_loss=("mean_active_loss", "mean"),
            company_revenue_cumulative_mean=("company_revenue_cumulative_mean", "mean"),
            company_revenue_active_mean=("company_revenue_active_mean", "mean"),
            loss_initial_pct=("loss_initial_pct", "mean"),
            loss_initial_money=("loss_initial_money", "mean"),
            cumulative_loss_initial_week_pct=("cumulative_loss_initial_week_pct", "mean"),
            cumulative_loss_initial_week_money=("cumulative_loss_initial_week_money", "mean"),
            cumulative_loss_initial_month_pct=("cumulative_loss_initial_month_pct", "mean"),
            cumulative_loss_initial_month_money=("cumulative_loss_initial_month_money", "mean"),
            cumulative_loss_initial_semester_pct=("cumulative_loss_initial_semester_pct", "mean"),
            cumulative_loss_initial_semester_money=("cumulative_loss_initial_semester_money", "mean"),
            period_loss_wealth_week_pct=("period_loss_wealth_week_pct", "mean"),
            period_loss_wealth_week_money=("period_loss_wealth_week_money", "mean"),
            period_loss_wealth_month_pct=("period_loss_wealth_month_pct", "mean"),
            period_loss_wealth_month_money=("period_loss_wealth_month_money", "mean"),
            period_loss_wealth_semester_pct=("period_loss_wealth_semester_pct", "mean"),
            period_loss_wealth_semester_money=("period_loss_wealth_semester_money", "mean"),
            cumulative_period_loss_wealth_week_pct=("cumulative_period_loss_wealth_week_pct", "mean"),
            cumulative_period_loss_wealth_week_money=("cumulative_period_loss_wealth_week_money", "mean"),
            cumulative_period_loss_wealth_month_pct=("cumulative_period_loss_wealth_month_pct", "mean"),
            cumulative_period_loss_wealth_month_money=("cumulative_period_loss_wealth_month_money", "mean"),
            cumulative_period_loss_wealth_semester_pct=("cumulative_period_loss_wealth_semester_pct", "mean"),
            cumulative_period_loss_wealth_semester_money=("cumulative_period_loss_wealth_semester_money", "mean"),
        )
        .sort_values(["modelo", "scenario", "portfolio", "semester"])
    )
    summary.to_csv(out_path, index=False)
    return summary

def summarize_p4(p4: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        p4.groupby(["modelo", "scenario", "portfolio"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            simulated_clients_total=("initial_clients_total", "sum"),
            initial_active_clients_mean=("initial_active_clients", "mean"),
            initial_active_clients_total=("initial_active_clients", "sum"),
            final_active_clients_mean=("final_active_clients", "mean"),
            final_active_clients_total=("final_active_clients", "sum"),
            p_accept_initial_portfolio_mean=("p_accept_initial_portfolio", "mean"),
            p_accept_rebalance_mean=("p_accept_rebalance", "mean"),
            mean_weekly_abandon_probability=("mean_weekly_abandon_probability", "mean"),
            max_weekly_abandon_probability=("max_weekly_abandon_probability", "max"),
            mean_semiannual_abandon_probability=("mean_semiannual_abandon_probability", "mean"),
            max_semiannual_abandon_probability=("max_semiannual_abandon_probability", "max"),
            terminal_wealth_mean=("terminal_wealth_mean", "mean"),
            terminal_wealth_median=("terminal_wealth_median", "mean"),
            terminal_wealth_p10=("terminal_wealth_mean", pctile_10),
            prob_profit_mean=("prob_profit", "mean"),
            withdrawal_rate_mean=("withdrawal_rate", "mean"),
            company_revenue_mean=("company_revenue_mean", "mean"),
            company_revenue_median=("company_revenue_median", "mean"),
            p4_score_mean=("p4_score", "mean"),
            p4_score_median=("p4_score_median", "mean"),
        )
        .sort_values("p4_score_median", ascending=False)
    )
    summary.to_csv(out_path, index=False)
    return summary


def summarize_behavior(p4: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    summary = (
        p4.groupby(["modelo", "scenario", "portfolio"], as_index=False)
        .agg(
            n_windows=("window_id", "nunique"),
            simulated_clients_total=("initial_clients_total", "sum"),
            initial_active_clients_mean=("initial_active_clients", "mean"),
            initial_active_clients_total=("initial_active_clients", "sum"),
            final_active_clients_mean=("final_active_clients", "mean"),
            final_active_clients_total=("final_active_clients", "sum"),
            p_accept_initial_portfolio=("p_accept_initial_portfolio", "mean"),
            p_accept_rebalance=("p_accept_rebalance", "mean"),
            mean_weekly_abandon_probability=("mean_weekly_abandon_probability", "mean"),
            max_weekly_abandon_probability=("max_weekly_abandon_probability", "max"),
            mean_semiannual_abandon_probability=("mean_semiannual_abandon_probability", "mean"),
            max_semiannual_abandon_probability=("max_semiannual_abandon_probability", "max"),
            realized_abandon_rate_260w=("withdrawal_rate", "mean"),
        )
    )
    summary["client_retention_rate"] = (
        summary["final_active_clients_total"] / summary["initial_active_clients_total"].replace(0, np.nan)
    )
    summary.to_csv(out_path, index=False)
    return summary


def _chart_font(size: int = 13, bold: bool = False) -> ImageFont.ImageFont:
    font_path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def draw_behavior_probability_chart(summary: pd.DataFrame, scenario: str, out_path: Path) -> None:
    profiles = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]
    models = ["BL calibrado", "Markowitz base"]
    subset = summary[summary["scenario"] == scenario].copy()
    width, height = 1250, 720
    margin_l, margin_r, margin_t, margin_b = 110, 40, 85, 160
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = _chart_font(13)
    small = _chart_font(10)
    title_font = _chart_font(20, bold=True)
    scenario_label = "Con pandemia" if scenario == "con_pandemia" else "Sin pandemia"
    draw.text((margin_l, 25), f"Probabilidades conductuales P4 - {scenario_label}", fill=(25, 30, 35), font=title_font)

    ymax = 1.0
    plot_h = height - margin_t - margin_b
    plot_w = width - margin_l - margin_r
    for j in range(6):
        y = margin_t + j * plot_h / 5
        draw.line((margin_l, y, width - margin_r, y), fill=(225, 230, 235))
        draw.text((35, y - 8), f"{1.0 - j / 5:.0%}", fill=(75, 75, 75), font=small)
    draw.line((margin_l, margin_t, margin_l, height - margin_b), fill=(50, 50, 50), width=2)
    draw.line((margin_l, height - margin_b, width - margin_r, height - margin_b), fill=(50, 50, 50), width=2)

    colors = {
        ("BL calibrado", "accept"): (35, 111, 161),
        ("BL calibrado", "withdraw"): (120, 170, 205),
        ("Markowitz base", "accept"): (190, 84, 45),
        ("Markowitz base", "withdraw"): (230, 150, 105),
    }
    group_gap = plot_w / len(profiles)
    bar_w = group_gap * 0.13
    for i, profile in enumerate(profiles):
        x0 = margin_l + i * group_gap + group_gap * 0.08
        bars: List[Tuple[str, str, float]] = []
        for model in models:
            row = subset[(subset["modelo"] == model) & (subset["portfolio"] == profile)]
            if row.empty:
                continue
            r = row.iloc[0]
            bars.append((model, "accept", float(r["p_accept_rebalance"])))
            bars.append((model, "withdraw", float(r["mean_semiannual_abandon_probability"])))
        for j, (model, metric, value) in enumerate(bars):
            x = x0 + j * (bar_w + 4)
            y = height - margin_b - value * plot_h / ymax
            draw.rectangle((x, y, x + bar_w, height - margin_b), fill=colors[(model, metric)])
        draw.text((x0 - 12, height - margin_b + 12), profile.replace(" ", "\n"), fill=(45, 45, 45), font=small)

    legend = [
        ("BL acepta", colors[("BL calibrado", "accept")]),
        ("BL abandono sem.", colors[("BL calibrado", "withdraw")]),
        ("MK acepta", colors[("Markowitz base", "accept")]),
        ("MK abandono sem.", colors[("Markowitz base", "withdraw")]),
    ]
    lx = margin_l
    for label, color in legend:
        draw.rectangle((lx, height - 48, lx + 18, height - 30), fill=color)
        draw.text((lx + 25, height - 50), label, fill=(45, 45, 45), font=font)
        lx += 170
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def draw_behavior_clients_chart(summary: pd.DataFrame, scenario: str, out_path: Path) -> None:
    profiles = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]
    models = ["BL calibrado", "Markowitz base"]
    subset = summary[summary["scenario"] == scenario].copy()
    width, height = 1250, 720
    margin_l, margin_r, margin_t, margin_b = 110, 40, 85, 160
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = _chart_font(13)
    small = _chart_font(10)
    title_font = _chart_font(20, bold=True)
    scenario_label = "Con pandemia" if scenario == "con_pandemia" else "Sin pandemia"
    draw.text((margin_l, 25), f"Clientes activos iniciales y finales - {scenario_label}", fill=(25, 30, 35), font=title_font)

    ymax = max(float(subset["initial_active_clients_mean"].max()), 1.0) * 1.15
    plot_h = height - margin_t - margin_b
    plot_w = width - margin_l - margin_r
    for j in range(6):
        y = margin_t + j * plot_h / 5
        val = ymax - j * ymax / 5
        draw.line((margin_l, y, width - margin_r, y), fill=(225, 230, 235))
        draw.text((30, y - 8), f"{val:.0f}", fill=(75, 75, 75), font=small)
    draw.line((margin_l, margin_t, margin_l, height - margin_b), fill=(50, 50, 50), width=2)
    draw.line((margin_l, height - margin_b, width - margin_r, height - margin_b), fill=(50, 50, 50), width=2)

    colors = {
        ("BL calibrado", "initial"): (35, 111, 161),
        ("BL calibrado", "final"): (120, 170, 205),
        ("Markowitz base", "initial"): (190, 84, 45),
        ("Markowitz base", "final"): (230, 150, 105),
    }
    group_gap = plot_w / len(profiles)
    bar_w = group_gap * 0.13
    for i, profile in enumerate(profiles):
        x0 = margin_l + i * group_gap + group_gap * 0.08
        bars: List[Tuple[str, str, float]] = []
        for model in models:
            row = subset[(subset["modelo"] == model) & (subset["portfolio"] == profile)]
            if row.empty:
                continue
            r = row.iloc[0]
            bars.append((model, "initial", float(r["initial_active_clients_mean"])))
            bars.append((model, "final", float(r["final_active_clients_mean"])))
        for j, (model, metric, value) in enumerate(bars):
            x = x0 + j * (bar_w + 4)
            y = height - margin_b - value * plot_h / ymax
            draw.rectangle((x, y, x + bar_w, height - margin_b), fill=colors[(model, metric)])
        draw.text((x0 - 12, height - margin_b + 12), profile.replace(" ", "\n"), fill=(45, 45, 45), font=small)

    legend = [
        ("BL inicial", colors[("BL calibrado", "initial")]),
        ("BL final", colors[("BL calibrado", "final")]),
        ("MK inicial", colors[("Markowitz base", "initial")]),
        ("MK final", colors[("Markowitz base", "final")]),
    ]
    lx = margin_l
    for label, color in legend:
        draw.rectangle((lx, height - 48, lx + 18, height - 30), fill=color)
        draw.text((lx + 25, height - 50), label, fill=(45, 45, 45), font=font)
        lx += 170
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def write_search_space() -> None:
    stage1_config = stage1_configs_for_view()[0]
    rows = [
        ("1_familia_view", "familia/P/Q base", stage1_config.view_label, "tau=.05, confianza base", "view fijada para comparacion individual"),
        ("2_estructura_P", "estructura interna de P", "desempleo {4%,5%,6%}; beta {0.5,1.0,1.5}", "familia ganadora fija", "perfil Neutro, ventanas de calibracion"),
        ("3_intensidad_Q", "q_scale", "{0.5,1.0,1.5}", "P ganador fijo", "score robusto rolling"),
        ("4_Omega", "confidence", "desempleo {0.20,0.35,0.50}", "P y Q fijos", "balance prior-view"),
        ("5_tau", "tau", "{0.01,0.025,0.05,0.10,0.20}", "P,Q,Omega fijos", "sensibilidad final"),
    ]
    pd.DataFrame(rows, columns=["etapa", "parametro", "valores_probados", "valores_fijos", "criterio"]).to_csv(
        OUTPUT_DIR / "01_espacio_busqueda_3h.csv", index=False
    )


def write_execution_summary(
    windows: Sequence[WindowSpec],
    winners: Dict[str, base.ViewConfig],
    rankings: Dict[str, pd.DataFrame],
    validation_summary: pd.DataFrame,
    test_summary: pd.DataFrame,
    dynamics_summary: pd.DataFrame,
    p4_summary: pd.DataFrame,
    elapsed_seconds: float,
) -> None:
    lines = [
        "# Validacion tres horizontes Black-Litterman",
        "",
        "## Ventanas",
    ]
    role_counts = pd.DataFrame([w.__dict__ for w in windows]).groupby(["scenario", "role"]).size().reset_index(name="n")
    for _, row in role_counts.iterrows():
        lines.append(f"- {row['scenario']} / {row['role']}: {int(row['n'])} ventanas.")
    lines.extend(["", "## Ganadores de calibracion"])
    for stage, config in winners.items():
        row = rankings[stage].iloc[0]
        lines.append(
            f"- {stage}: {config.config_id}, Sharpe medio {row['sharpe_mean']:.3f}, "
            f"delta Sharpe {row['delta_sharpe_mean']:.3f}, score {row['score_robusto']:.3f}."
        )
    final = winners["stage5_tau"]
    lines.extend(
        [
            "",
            "## Configuracion congelada",
            f"- family={final.family}; unemployment_assumed={final.unemployment_assumed:.2%}; "
            f"macro_beta={final.macro_beta}; q_scale={final.q_scale}; confidence={final.confidence}; tau={final.tau}.",
            "",
            "## Validacion y test",
        ]
    )
    for label, df in [("validacion", validation_summary), ("test_p4", test_summary)]:
        subset = df[df["window_role"] == label] if "window_role" in df.columns else df
        if subset.empty:
            continue
        best = subset.sort_values("mejora_pct_sharpe_mean", ascending=False).head(5)
        for _, row in best.iterrows():
            lines.append(
                f"- {label} / {row['scenario']} / {row['portfolio']}: mejora Sharpe media "
                f"{row['mejora_pct_sharpe_mean']:.1%}, delta drawdown {row['delta_drawdown_mean']:.1%}, "
                f"pct recomendado {row['pct_recomendado']:.1%}."
            )
    lines.extend(["", "## Dinamica de portafolio"])
    if not dynamics_summary.empty:
        for _, row in dynamics_summary.head(8).iterrows():
            lines.append(
                f"- {row['modelo']} / {row['window_role']} / {row['scenario']} / {row['portfolio']}: "
                f"turnover medio {row['turnover_mean']:.1%}, N efectivo {row['n_effective_assets_mean']:.1f}, "
                f"sector HHI {row['sector_hhi_mean']:.3f}."
            )
    lines.extend(["", "## P4 limpio"])
    for _, row in p4_summary.head(8).iterrows():
        lines.append(
            f"- {row['modelo']} / {row['scenario']} / {row['portfolio']}: riqueza "
            f"{row['terminal_wealth_mean']:.0f}, retiro {row['withdrawal_rate_mean']:.1%}, "
            f"utilidad {row['company_revenue_mean']:.0f}, score {row['p4_score_mean']:.0f}."
        )
    lines.append(f"\nTiempo total: {elapsed_seconds:.1f} segundos.")
    (OUTPUT_DIR / "resumen_ejecucion_3h.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    t0 = time.perf_counter()
    write_search_space()
    log("Cargando metadata y retornos")
    meta = base.read_metadata()
    datasets = {
        "sin_pandemia": base.load_returns_for_scenario(meta, "sin_pandemia"),
        "con_pandemia": base.load_returns_for_scenario(meta, "con_pandemia"),
    }
    common = [
        ticker
        for ticker in meta["ticker"].tolist()
        if ticker in datasets["sin_pandemia"].columns and ticker in datasets["con_pandemia"].columns
    ]
    datasets = {scenario: df[common].copy() for scenario, df in datasets.items()}
    meta = meta.set_index("ticker").reindex(common).reset_index()
    log(f"Universo comun: {len(common)} activos")

    windows = write_windows_roles(datasets)
    windows_df = pd.DataFrame([w.__dict__ for w in windows])
    log("Ventanas por rol:")
    for _, row in windows_df.groupby(["scenario", "role"]).size().reset_index(name="n").iterrows():
        log(f"  {row['scenario']} / {row['role']}: {int(row['n'])}")

    calibration_windows = [w for w in windows if w.role == ROLE_CALIBRATION]
    validation_windows = [w for w in windows if w.role == ROLE_VALIDATION]
    test_windows = [w for w in windows if w.role == ROLE_TEST]
    validation_test_windows = validation_windows + test_windows

    log("Calculando Markowitz base en todas las ventanas")
    markowitz_base, _, _, _, _ = evaluate_config_on_windows(
        datasets,
        meta,
        None,
        base.RISK_PROFILES,
        windows,
        "00_markowitz_base",
        "Markowitz base",
        collect_dynamics=False,
    )
    markowitz_base.to_csv(OUTPUT_DIR / "02_markowitz_base_rolling.csv", index=False)

    markowitz_calibration = markowitz_base[
        (markowitz_base["window_role"] == ROLE_CALIBRATION) & (markowitz_base["portfolio"] == "Neutro")
    ].copy()

    winners: Dict[str, base.ViewConfig] = {}
    rankings: Dict[str, pd.DataFrame] = {}
    stage1_configs = stage1_configs_for_view()
    log(f"View fijada para comparacion: {stage1_configs[0].view_label} ({FORCED_VIEW_KEY})")

    winner1, _, ranking1 = run_stage_rolling(
        "stage1_familia_view",
        stage1_configs,
        datasets,
        meta,
        markowitz_calibration,
        calibration_windows,
        base.CALIBRATION_PROFILES,
    )
    winners["stage1_familia_view"] = winner1
    rankings["stage1_familia_view"] = ranking1

    stage2_configs = base.generate_stage2_configs(winner1)
    winner2, _, ranking2 = run_stage_rolling(
        "stage2_estructura_P",
        stage2_configs,
        datasets,
        meta,
        markowitz_calibration,
        calibration_windows,
        base.CALIBRATION_PROFILES,
    )
    winners["stage2_estructura_P"] = winner2
    rankings["stage2_estructura_P"] = ranking2

    q_configs = [replace(winner2, config_id=f"stage3_q_scale_{q:.1f}", q_scale=q) for q in [0.5, 1.0, 1.5]]
    winner3, _, ranking3 = run_stage_rolling(
        "stage3_intensidad_Q",
        q_configs,
        datasets,
        meta,
        markowitz_calibration,
        calibration_windows,
        base.CALIBRATION_PROFILES,
    )
    winners["stage3_intensidad_Q"] = winner3
    rankings["stage3_intensidad_Q"] = ranking3

    confidence_grid = [0.20, 0.35, 0.50] if winner3.family == "unemployment" else [0.35, 0.50, 0.65, 0.80]
    conf_configs = [replace(winner3, config_id=f"stage4_conf_{c:.2f}", confidence=c) for c in confidence_grid]
    winner4, _, ranking4 = run_stage_rolling(
        "stage4_confianza_Omega",
        conf_configs,
        datasets,
        meta,
        markowitz_calibration,
        calibration_windows,
        base.CALIBRATION_PROFILES,
    )
    winners["stage4_confianza_Omega"] = winner4
    rankings["stage4_confianza_Omega"] = ranking4

    tau_configs = [replace(winner4, config_id=f"stage5_tau_{tau:.3f}", tau=tau) for tau in [0.01, 0.025, 0.05, 0.10, 0.20]]
    winner5, _, ranking5 = run_stage_rolling(
        "stage5_tau",
        tau_configs,
        datasets,
        meta,
        markowitz_calibration,
        calibration_windows,
        base.CALIBRATION_PROFILES,
    )
    winners["stage5_tau"] = winner5
    rankings["stage5_tau"] = ranking5

    frozen_rows = [base.config_to_record(winner5)]
    frozen_rows[0].update({"view_key": FORCED_VIEW_KEY, "config_id": winner5.config_id, "family": winner5.family, "view_label": winner5.view_label})
    pd.DataFrame(frozen_rows).to_csv(OUTPUT_DIR / "03_configuracion_congelada.csv", index=False)

    log("Evaluando configuracion congelada en validacion y test limpio")
    final_bl, final_views, bl_weights, bl_rebalance, bl_sector = evaluate_config_on_windows(
        datasets,
        meta,
        winner5,
        base.RISK_PROFILES,
        validation_test_windows,
        "final_bl_congelado",
        "BL calibrado",
        collect_dynamics=True,
    )
    final_bl.to_csv(OUTPUT_DIR / "04_bl_congelado_validacion_test.csv", index=False)
    final_views.to_csv(OUTPUT_DIR / "04_bl_congelado_views_validacion_test.csv", index=False)

    mk_valtest, _, mk_weights, mk_rebalance, mk_sector = evaluate_config_on_windows(
        datasets,
        meta,
        None,
        base.RISK_PROFILES,
        validation_test_windows,
        "markowitz_validacion_test",
        "Markowitz base",
        collect_dynamics=True,
    )
    mk_valtest.to_csv(OUTPUT_DIR / "05_markowitz_validacion_test.csv", index=False)

    validation_metrics = final_bl[final_bl["window_role"] == ROLE_VALIDATION]
    test_metrics = final_bl[final_bl["window_role"] == ROLE_TEST]
    aggregate_window_metrics(pd.concat([final_bl, mk_valtest], ignore_index=True), VALIDATION_DIR / "metricas_rolling_validacion_test_resumen.csv")

    comparison = compare_against_markowitz(
        final_bl,
        mk_valtest,
        OUTPUT_DIR / "06_comparacion_bl_vs_markowitz_validacion_test.csv",
    )
    validation_summary = summarize_comparison(
        comparison[comparison["window_role"] == ROLE_VALIDATION],
        VALIDATION_DIR / "validacion_configuracion_congelada_resumen.csv",
    )
    test_summary = summarize_comparison(
        comparison[comparison["window_role"] == ROLE_TEST],
        TEST_DIR / "test_limpio_comparacion_resumen.csv",
    )
    validation_metrics.to_csv(VALIDATION_DIR / "validacion_configuracion_congelada_detalle.csv", index=False)
    test_metrics.to_csv(TEST_DIR / "kpis_financieros_test_limpio_bl.csv", index=False)
    mk_valtest[mk_valtest["window_role"] == ROLE_TEST].to_csv(TEST_DIR / "kpis_financieros_test_limpio_markowitz.csv", index=False)

    log("Calculando dinamica de portafolio")
    weights_all = pd.concat([bl_weights, mk_weights], ignore_index=True)
    rebalance_all = pd.concat([bl_rebalance, mk_rebalance], ignore_index=True)
    sector_all = pd.concat([bl_sector, mk_sector], ignore_index=True)
    weights_all.to_csv(DYNAMICS_DIR / "weights_by_rebalance.csv", index=False)
    rebalance_all.to_csv(DYNAMICS_DIR / "rebalance_dynamics_detail.csv", index=False)
    dynamics_summary = summarize_rebalance_dynamics(rebalance_all, DYNAMICS_DIR / "turnover_summary.csv")
    composition_stability(weights_all, DYNAMICS_DIR / "composition_stability.csv")
    summarize_sector_returns(
        sector_all,
        DYNAMICS_DIR / "sector_return_contribution.csv",
        DYNAMICS_DIR / "sector_return_concentration_summary.csv",
    )

    log("Ejecutando P4 solo sobre ventanas test_p4")
    p4_input = pd.concat(
        [
            final_bl[final_bl["window_role"] == ROLE_TEST][
                ["modelo", "scenario", "window_id", "window_role", "portfolio", "retorno_anual", "volatilidad_anual"]
            ],
            mk_valtest[mk_valtest["window_role"] == ROLE_TEST][
                ["modelo", "scenario", "window_id", "window_role", "portfolio", "retorno_anual", "volatilidad_anual"]
            ],
        ],
        ignore_index=True,
    )
    p4, p4_weekly = simulate_p4_clean(p4_input)
    p4.to_csv(TEST_DIR / "p4_test_limpio_detalle.csv", index=False)
    p4_weekly.to_csv(BEHAVIOR_DIR / "weekly_behavior_timeseries_detail.csv", index=False)
    p4_summary = summarize_p4(p4, TEST_DIR / "p4_test_limpio_resumen.csv")
    behavior_summary = summarize_behavior(p4, BEHAVIOR_DIR / "behavior_probabilities_clients_summary.csv")
    weekly_behavior_summary = summarize_weekly_behavior(
        p4_weekly,
        BEHAVIOR_DIR / "weekly_behavior_timeseries_summary.csv",
    )
    monthly_behavior_summary = summarize_monthly_behavior(
        p4_weekly,
        BEHAVIOR_DIR / "monthly_behavior_timeseries_summary.csv",
    )
    semiannual_gain_summary = summarize_semiannual_gain(
        p4_weekly,
        BEHAVIOR_DIR / "semiannual_gain_timeseries_summary.csv",
    )
    p4.to_csv(BEHAVIOR_DIR / "behavior_probabilities_clients_detail.csv", index=False)
    draw_behavior_probability_chart(
        behavior_summary,
        "con_pandemia",
        BEHAVIOR_DIR / "fig_probabilidades_con_pandemia.png",
    )
    draw_behavior_probability_chart(
        behavior_summary,
        "sin_pandemia",
        BEHAVIOR_DIR / "fig_probabilidades_sin_pandemia.png",
    )
    draw_behavior_clients_chart(
        behavior_summary,
        "con_pandemia",
        BEHAVIOR_DIR / "fig_clientes_con_pandemia.png",
    )
    draw_behavior_clients_chart(
        behavior_summary,
        "sin_pandemia",
        BEHAVIOR_DIR / "fig_clientes_sin_pandemia.png",
    )

    checks = {
        "activos": len(common),
        "windows_total": len(windows),
        "windows_calibracion": len(calibration_windows),
        "windows_validacion": len(validation_windows),
        "windows_test_p4": len(test_windows),
        "view_key": FORCED_VIEW_KEY,
        "abandonment_version": ABANDONMENT_VERSION,
        "abandonment_formula": ABANDONMENT_FORMULA,
        "stage1_configs": len(stage1_configs),
        "stage2_configs": len(stage2_configs),
        "final_bl_rows_validacion_test": len(final_bl),
        "weights_rows": len(weights_all),
        "p4_rows": len(p4),
        "behavior_rows": len(behavior_summary),
        "weekly_behavior_rows": len(weekly_behavior_summary),
        "monthly_behavior_rows": len(monthly_behavior_summary),
        "semiannual_gain_rows": len(semiannual_gain_summary),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    pd.DataFrame([checks]).to_csv(OUTPUT_DIR / "99_checks_validacion_3h.csv", index=False)
    write_execution_summary(
        windows,
        winners,
        rankings,
        validation_summary,
        test_summary,
        dynamics_summary,
        p4_summary,
        checks["elapsed_seconds"],
    )
    log(f"Listo en {checks['elapsed_seconds']}s. Outputs en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
