"""
Calibracion secuencial de Black-Litterman para FinPUC.

Este script implementa la heuristica defendible acordada para Entrega 3:
1. Seleccion de familia de view.
2. Calibracion estructural de P.
3. Calibracion de intensidad Q.
4. Calibracion de Omega via confianza.
5. Sensibilidad final de tau.
6. Validacion robusta y evaluacion P4 posterior.

No requiere cvxpy ni matplotlib. Usa numpy/pandas y genera CSV, PNG simples
con PIL, y un resumen Markdown listo para el informe.
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


TRADING_DAYS = 252
RISK_FREE_RATE = 0.02
SHRINKAGE = 0.20
HISTORICAL_YEARS = 7
FUTURE_YEARS = 2
REBALANCE_DAYS = 126
INITIAL_CAPITAL = 1000.0
N_SIMULATIONS = 2000
N_WEEKS = 260
K_PERCENT = 1.0
COMPANY_FEE_RATE = K_PERCENT / 100.0
COMPANY_MONTHLY_FEE_RATE = 0.005
COMPANY_WEEKLY_FEE_RATE = COMPANY_MONTHLY_FEE_RATE * 12.0 / 52.0
ABANDONMENT_VERSION = "v1_plus"
ABANDONMENT_FORMULA = "threshold_logistic_unscaled_with_ruin"
TURNOVER_FRACTION = 0.05


WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_capstone_root(start: Path) -> Path:
    """Encuentra la raiz del proyecto aun cuando el script viva en subcarpetas."""
    for candidate in [start, *start.parents]:
        data_dir = candidate / "Entrega 2" / "Desarrollo modelo Markowitz" / "Data"
        if data_dir.exists():
            return candidate
    raise FileNotFoundError("No se encontro la carpeta de datos del proyecto Capstone.")


CAPSTONE_ROOT = find_capstone_root(WORK_DIR)
DATA_ROOT = CAPSTONE_ROOT / "Entrega 2" / "Desarrollo modelo Markowitz" / "Data"
META_PATH = DATA_ROOT / "Historical_Stocks_filtrado_sin_pandemia" / "tickers_filtrados_F5.csv"
SIN_PANDEMIA_DIR = DATA_ROOT / "Historical_Stocks_filtrado_sin_pandemia" / "Historical_Stocks_sin_pandemia"
CON_PANDEMIA_DIR = DATA_ROOT / "Historical Stocks"


@dataclass(frozen=True)
class RiskProfile:
    key: str
    label: str
    gamma: float
    max_weight: float
    annual_vol_cap: Optional[float]
    loss_tolerance: float


@dataclass(frozen=True)
class ViewConfig:
    config_id: str
    family: str
    view_label: str
    lookback_days: int = 252
    top_bottom_size: int = 20
    market_cap_universe_size: int = 0
    long_short_size: int = 20
    p_weighting: str = "equal"
    q_scale: float = 1.0
    confidence: float = 0.50
    tau: float = 0.05
    unemployment_assumed: float = 0.04
    unemployment_neutral: float = 0.05
    macro_beta: float = 1.0


RISK_PROFILES: List[RiskProfile] = [
    RiskProfile("muy_conservador", "Muy conservador", 80.0, 0.05, 0.08, 0.00),
    RiskProfile("conservador", "Conservador", 45.0, 0.07, 0.12, 0.05),
    RiskProfile("neutro", "Neutro", 20.0, 0.10, 0.18, 0.15),
    RiskProfile("arriesgado", "Arriesgado", 8.0, 0.15, 0.28, 0.30),
    RiskProfile("muy_arriesgado", "Muy arriesgado", 3.0, 0.20, 0.40, 0.40),
]
PROFILE_BY_LABEL = {p.label: p for p in RISK_PROFILES}
CALIBRATION_PROFILES = [PROFILE_BY_LABEL["Neutro"]]

BASE_VIEW_CONFIGS: List[ViewConfig] = [
    ViewConfig("stage1_momentum", "momentum", "Momentum general", 252, 20, 0, 20, "equal", 1.0, 0.50, 0.05),
    ViewConfig("stage1_mcap20_6m", "marketcap_momentum", "Momentum top market-cap 6M", 126, 20, 20, 10, "equal", 1.0, 0.50, 0.05),
    ViewConfig("stage1_mcap40_1y", "marketcap_momentum", "Momentum top/bottom market-cap 1Y", 252, 20, 40, 20, "equal", 1.0, 0.50, 0.05),
    ViewConfig("stage1_desempleo", "unemployment", "Desempleo macro asumido", 252, 20, 0, 20, "equal", 1.0, 0.35, 0.05),
]

CYCLICAL_SECTORS = {
    "Technology",
    "Consumer Cyclical",
    "Industrials",
    "Financial Services",
    "Communication Services",
    "Energy",
    "Basic Materials",
}
DEFENSIVE_SECTORS = {"Healthcare", "Consumer Defensive", "Utilities", "Real Estate"}


def log(message: str) -> None:
    print(f"[BL-CAL] {message}", flush=True)


def safe_float(x: float, default: float = 0.0) -> float:
    try:
        if math.isfinite(float(x)):
            return float(x)
    except Exception:
        pass
    return default


def read_metadata() -> pd.DataFrame:
    meta = pd.read_csv(META_PATH)
    meta["ticker"] = meta["ticker"].astype(str).str.upper().str.strip()
    meta["marketCap"] = pd.to_numeric(meta["marketCap"], errors="coerce").fillna(0.0)
    meta = meta.drop_duplicates("ticker").sort_values("marketCap", ascending=False).reset_index(drop=True)
    return meta.head(601).copy()


def load_returns_for_scenario(meta: pd.DataFrame, scenario: str) -> pd.DataFrame:
    cache_path = OUTPUT_DIR / f"cache_returns_{scenario}.pkl"
    if cache_path.exists():
        return pd.read_pickle(cache_path)

    data_dir = SIN_PANDEMIA_DIR if scenario == "sin_pandemia" else CON_PANDEMIA_DIR
    series = []
    tickers = meta["ticker"].tolist()
    t0 = time.perf_counter()
    for idx, ticker in enumerate(tickers, start=1):
        path = data_dir / f"stock_return_{ticker}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["Date", "Close", "Dividends"])
        df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_localize(None).dt.normalize()
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df["Dividends"] = pd.to_numeric(df["Dividends"], errors="coerce").fillna(0.0)
        total_return = (df["Close"] + df["Dividends"]) / df["Close"].shift(1) - 1.0
        s = pd.Series(total_return.to_numpy(), index=df["Date"], name=ticker).replace([np.inf, -np.inf], np.nan)
        series.append(s)
        if idx % 150 == 0:
            log(f"  {scenario}: {idx}/{len(tickers)} activos leidos")
    if not series:
        raise RuntimeError(f"No se pudieron leer retornos para {scenario} en {data_dir}")
    returns = pd.concat(series, axis=1, join="inner").dropna(how="any")
    returns = returns.loc[:, [t for t in tickers if t in returns.columns]]
    returns.to_pickle(cache_path)
    log(f"{scenario}: matriz {returns.shape} creada en {time.perf_counter() - t0:.1f}s")
    return returns


def latest_split(returns: pd.DataFrame, historical_years: int, future_years: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    future_days = int(future_years * TRADING_DAYS)
    historical_days = int(historical_years * TRADING_DAYS)
    if len(returns) < future_days + historical_days:
        raise ValueError(f"Observaciones insuficientes: {len(returns)}")
    window = returns.iloc[-(future_days + historical_days):]
    return window.iloc[:historical_days], window.iloc[historical_days:]


def rolling_split(returns: pd.DataFrame, historical_years: int, future_years: int, offset_segments: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    future_days = int(future_years * TRADING_DAYS)
    historical_days = int(historical_years * TRADING_DAYS)
    total = future_days + historical_days
    end = len(returns) - offset_segments * REBALANCE_DAYS
    start = end - total
    if start < 0:
        raise ValueError("Ventana robusta fuera de rango")
    window = returns.iloc[start:end]
    return window.iloc[:historical_days], window.iloc[historical_days:]


def rebalance_segments(historical: pd.DataFrame, future: pd.DataFrame) -> Iterable[Tuple[int, pd.DataFrame, pd.DataFrame]]:
    starts = list(range(0, len(future), REBALANCE_DAYS))
    if starts[-1] != len(future):
        starts.append(len(future))
    for segment_id, start in enumerate(starts[:-1], start=1):
        end = starts[segment_id]
        train = pd.concat([historical, future.iloc[:start]], axis=0)
        test = future.iloc[start:end]
        yield segment_id, train, test


def estimate_parameters(train: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    mu = train.mean(axis=0).to_numpy(dtype=float)
    sigma = train.cov().to_numpy(dtype=float)
    diag = np.diag(np.diag(sigma))
    sigma = (1.0 - SHRINKAGE) * sigma + SHRINKAGE * diag
    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    sigma += np.eye(sigma.shape[0]) * 1e-10
    return mu, sigma


def market_weights(meta: pd.DataFrame, tickers: Sequence[str]) -> np.ndarray:
    caps = meta.set_index("ticker").reindex(tickers)["marketCap"].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
    if caps.sum() <= 0:
        return np.ones(len(tickers)) / len(tickers)
    return caps / caps.sum()


def weighted_side_weights(names: Sequence[str], meta: pd.DataFrame, mode: str) -> np.ndarray:
    n = len(names)
    if n == 0:
        return np.array([], dtype=float)
    if mode == "rank":
        raw = np.arange(n, 0, -1, dtype=float)
        return raw / raw.sum()
    if mode == "marketcap":
        caps = meta.set_index("ticker").reindex(names)["marketCap"].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
        if caps.sum() > 0:
            return caps / caps.sum()
    return np.ones(n, dtype=float) / n


def build_momentum_view(
    train: pd.DataFrame,
    sigma: np.ndarray,
    tickers: Sequence[str],
    meta: pd.DataFrame,
    config: ViewConfig,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, object]]:
    recent = train.iloc[-min(config.lookback_days, len(train)) :]
    momentum = (1.0 + recent).prod(axis=0) - 1.0
    if config.family == "marketcap_momentum":
        top_market = meta.set_index("ticker").reindex(tickers).sort_values("marketCap", ascending=False)
        universe = [t for t in top_market.head(config.market_cap_universe_size).index if t in recent.columns]
        ranked = momentum.reindex(universe).dropna().sort_values(ascending=False)
        k = min(config.long_short_size, max(1, len(ranked) // 2))
    else:
        ranked = momentum.dropna().sort_values(ascending=False)
        k = min(config.top_bottom_size, max(1, len(ranked) // 2))
        universe = ranked.index.tolist()
    long_names = ranked.head(k).index.tolist()
    short_names = ranked.tail(k).index.tolist()
    p = np.zeros(len(tickers), dtype=float)
    idx = {t: i for i, t in enumerate(tickers)}
    long_w = weighted_side_weights(long_names, meta, config.p_weighting)
    short_w = weighted_side_weights(short_names, meta, config.p_weighting)
    for name, weight in zip(long_names, long_w):
        p[idx[name]] = weight
    for name, weight in zip(short_names, short_w):
        p[idx[name]] = -weight
    q_value = float((recent.to_numpy(dtype=float) @ p).mean() * config.q_scale)
    P = p.reshape(1, -1)
    Q = np.array([q_value], dtype=float)
    Omega = omega_from_view(P, sigma, config.tau, config.confidence)
    record = {
        "n_long": len(long_names),
        "n_short": len(short_names),
        "long_side": ";".join(long_names[:20]),
        "short_side": ";".join(short_names[:20]),
        "q_daily": q_value,
        "omega": float(Omega[0, 0]),
        "marketcap_universe_size_real": len(universe),
    }
    return P, Q, Omega, record


def build_unemployment_view(
    sigma: np.ndarray,
    tickers: Sequence[str],
    meta: pd.DataFrame,
    config: ViewConfig,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, object]]:
    meta_idx = meta.set_index("ticker").reindex(tickers)
    sectors = meta_idx["sector"].fillna("")
    cyc = [t for t, s in sectors.items() if s in CYCLICAL_SECTORS]
    defensive = [t for t, s in sectors.items() if s in DEFENSIVE_SECTORS]
    low_unemployment = config.unemployment_assumed < config.unemployment_neutral
    long_names, short_names = (cyc, defensive) if low_unemployment else (defensive, cyc)
    p = np.zeros(len(tickers), dtype=float)
    idx = {t: i for i, t in enumerate(tickers)}
    for name, weight in zip(long_names, weighted_side_weights(long_names, meta, "marketcap")):
        p[idx[name]] = weight
    for name, weight in zip(short_names, weighted_side_weights(short_names, meta, "marketcap")):
        p[idx[name]] = -weight
    signal = abs(config.unemployment_neutral - config.unemployment_assumed)
    q_value = float(signal * config.macro_beta * config.q_scale / TRADING_DAYS)
    P = p.reshape(1, -1)
    Q = np.array([q_value], dtype=float)
    Omega = omega_from_view(P, sigma, config.tau, config.confidence)
    record = {
        "n_long": len(long_names),
        "n_short": len(short_names),
        "long_side": ";".join(long_names[:20]),
        "short_side": ";".join(short_names[:20]),
        "q_daily": q_value,
        "omega": float(Omega[0, 0]),
        "unemployment_assumed": config.unemployment_assumed,
        "unemployment_neutral": config.unemployment_neutral,
    }
    return P, Q, Omega, record


def omega_from_view(P: np.ndarray, sigma: np.ndarray, tau: float, confidence: float) -> np.ndarray:
    base = P @ (tau * sigma) @ P.T
    value = float(base[0, 0]) / max(confidence, 1e-8)
    return np.array([[max(value, 1e-12)]], dtype=float)


def black_litterman_model(
    train: pd.DataFrame,
    meta: pd.DataFrame,
    config: Optional[ViewConfig],
) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
    tickers = list(train.columns)
    mu_hist, sigma = estimate_parameters(train)
    if config is None:
        return mu_hist, sigma, {"view_label": "Markowitz base", "q_daily": np.nan, "omega": np.nan}
    w_mkt = market_weights(meta, tickers)
    market_returns = train.to_numpy(dtype=float) @ w_mkt
    market_ret_ann = float(market_returns.mean() * TRADING_DAYS)
    market_var_ann = float(market_returns.var(ddof=1) * TRADING_DAYS)
    delta = max((market_ret_ann - RISK_FREE_RATE) / max(market_var_ann, 1e-10), 0.1)
    pi = delta * sigma @ w_mkt
    if config.family == "unemployment":
        P, Q, Omega, record = build_unemployment_view(sigma, tickers, meta, config)
    else:
        P, Q, Omega, record = build_momentum_view(train, sigma, tickers, meta, config)
    tau_sigma = config.tau * sigma
    middle = float((P @ tau_sigma @ P.T + Omega)[0, 0])
    innovation = float(Q[0] - (P @ pi)[0])
    adjustment = (tau_sigma @ P.T).ravel() * (innovation / max(middle, 1e-12))
    mu_bl = pi + adjustment
    sigma_bl = (1.0 + config.tau) * sigma - np.outer((tau_sigma @ P.T).ravel(), (P @ tau_sigma).ravel()) / max(middle, 1e-12)
    sigma_bl = 0.5 * (sigma_bl + sigma_bl.T) + np.eye(len(tickers)) * 1e-10
    record.update(
        {
            "view_label": config.view_label,
            "family": config.family,
            "tau": config.tau,
            "confidence": config.confidence,
            "q_scale": config.q_scale,
            "delta": delta,
            "market_return_annual": market_ret_ann,
            "market_variance_annual": market_var_ann,
        }
    )
    return mu_bl, sigma_bl, record


def project_capped_simplex(v: np.ndarray, cap: float) -> np.ndarray:
    if cap * len(v) < 1.0 - 1e-12:
        raise ValueError("La cota de peso es infactible")
    lo, hi = float(v.min() - cap), float(v.max())
    for _ in range(60):
        theta = (lo + hi) / 2.0
        w = np.clip(v - theta, 0.0, cap)
        if w.sum() > 1.0:
            lo = theta
        else:
            hi = theta
    w = np.clip(v - hi, 0.0, cap)
    total = w.sum()
    if total <= 0:
        w = np.ones_like(v) / len(v)
        w = np.minimum(w, cap)
        w /= w.sum()
    else:
        w /= total
    return w


def min_variance_weights(sigma: np.ndarray, cap: float, iterations: int = 90) -> np.ndarray:
    n = sigma.shape[0]
    w = project_capped_simplex(np.ones(n) / n, cap)
    l_bound = max(float(np.abs(sigma).sum(axis=1).max()), 1e-8)
    step = 0.8 / l_bound
    for _ in range(iterations):
        grad = sigma @ w
        w = project_capped_simplex(w - step * grad, cap)
    return w


def optimize_profile(mu: np.ndarray, sigma: np.ndarray, profile: RiskProfile, iterations: int = 120) -> Tuple[np.ndarray, str]:
    n = len(mu)
    w = project_capped_simplex(np.ones(n) / n, profile.max_weight)
    l_bound = max(profile.gamma * float(np.abs(sigma).sum(axis=1).max()), 1e-8)
    step = 0.8 / l_bound
    for _ in range(iterations):
        grad = mu - profile.gamma * (sigma @ w)
        w = project_capped_simplex(w + step * grad, profile.max_weight)
    note = "projected_gradient"
    if profile.annual_vol_cap is not None:
        vol = annual_vol(w, sigma)
        if vol > profile.annual_vol_cap:
            w_min = min_variance_weights(sigma, profile.max_weight, iterations=80)
            vol_min = annual_vol(w_min, sigma)
            if vol_min <= profile.annual_vol_cap:
                lo, hi = 0.0, 1.0
                for _ in range(45):
                    alpha = (lo + hi) / 2.0
                    candidate = (1.0 - alpha) * w_min + alpha * w
                    if annual_vol(candidate, sigma) <= profile.annual_vol_cap:
                        lo = alpha
                    else:
                        hi = alpha
                w = (1.0 - lo) * w_min + lo * w
                w = project_capped_simplex(w, profile.max_weight)
                note = "projected_gradient_volcap_blend"
            else:
                note = "projected_gradient_volcap_relaxed"
    return w, note


def annual_vol(w: np.ndarray, sigma: np.ndarray) -> float:
    return math.sqrt(max(float(w @ sigma @ w), 0.0) * TRADING_DAYS)


def portfolio_returns(test: pd.DataFrame, w: np.ndarray) -> pd.Series:
    return pd.Series(test.to_numpy(dtype=float) @ w, index=test.index)


def metrics_from_returns(r: pd.Series) -> Dict[str, float]:
    r = r.dropna()
    if len(r) == 0:
        return {}
    wealth = (1.0 + r).cumprod()
    total_return = float(wealth.iloc[-1] - 1.0)
    years = len(r) / TRADING_DAYS
    annual_return = float((1.0 + total_return) ** (1.0 / max(years, 1e-8)) - 1.0)
    daily_vol = float(r.std(ddof=1))
    vol_ann = daily_vol * math.sqrt(TRADING_DAYS)
    sharpe = (annual_return - RISK_FREE_RATE) / vol_ann if vol_ann > 1e-12 else np.nan
    running_max = wealth.cummax()
    drawdown = wealth / running_max - 1.0
    losses = -r
    threshold = losses.quantile(0.95)
    cvar = float(losses[losses >= threshold].mean()) if len(losses) else np.nan
    return {
        "retorno_total": total_return,
        "retorno_anual": annual_return,
        "volatilidad_anual": vol_ann,
        "max_drawdown": float(drawdown.min()),
        "cvar_95_diario": cvar,
        "sharpe": float(sharpe),
    }


def evaluate_rebalanced_config(
    datasets: Dict[str, pd.DataFrame],
    meta: pd.DataFrame,
    config: Optional[ViewConfig],
    profiles: Sequence[RiskProfile],
    stage: str,
    historical_years: int = HISTORICAL_YEARS,
    future_years: int = FUTURE_YEARS,
    robust_offset: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    view_rows: List[Dict[str, object]] = []
    config_id = config.config_id if config else "markowitz_base"
    for scenario, returns in datasets.items():
        if robust_offset is None:
            historical, future = latest_split(returns, historical_years, future_years)
        else:
            historical, future = rolling_split(returns, historical_years, future_years, robust_offset)
        combined: Dict[str, List[pd.Series]] = {p.label: [] for p in profiles}
        notes: Dict[str, str] = {}
        for segment_id, train, test in rebalance_segments(historical, future):
            mu_model, sigma_model, view_record = black_litterman_model(train, meta, config)
            view_record.update(
                {
                    "stage": stage,
                    "config_id": config_id,
                    "scenario": scenario,
                    "segment_id": segment_id,
                    "train_start": str(train.index.min().date()),
                    "train_end": str(train.index.max().date()),
                    "test_start": str(test.index.min().date()),
                    "test_end": str(test.index.max().date()),
                }
            )
            view_rows.append(view_record)
            for profile in profiles:
                w, note = optimize_profile(mu_model, sigma_model, profile)
                combined[profile.label].append(portfolio_returns(test, w))
                notes[profile.label] = note
        for profile in profiles:
            ret = pd.concat(combined[profile.label]).sort_index()
            m = metrics_from_returns(ret)
            row = {
                "stage": stage,
                "config_id": config_id,
                "view_label": config.view_label if config else "Markowitz base",
                "family": config.family if config else "markowitz",
                "scenario": scenario,
                "historical_years": historical_years,
                "future_years": future_years,
                "robust_offset": robust_offset if robust_offset is not None else 0,
                "portfolio": profile.label,
                "profile_key": profile.key,
                "optimizer_note": notes.get(profile.label, ""),
            }
            if config:
                row.update(config_to_record(config))
            row.update(m)
            rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(view_rows)


def config_to_record(config: ViewConfig) -> Dict[str, object]:
    return {
        "lookback_days": config.lookback_days,
        "top_bottom_size": config.top_bottom_size,
        "market_cap_universe_size": config.market_cap_universe_size,
        "long_short_size": config.long_short_size,
        "p_weighting": config.p_weighting,
        "q_scale": config.q_scale,
        "confidence": config.confidence,
        "tau": config.tau,
        "unemployment_assumed": config.unemployment_assumed,
        "macro_beta": config.macro_beta,
    }


def score_candidates(df: pd.DataFrame, base_df: pd.DataFrame, stage: str) -> pd.DataFrame:
    merged = df.merge(
        base_df[["scenario", "portfolio", "sharpe", "retorno_anual", "max_drawdown", "cvar_95_diario"]].rename(
            columns={
                "sharpe": "base_sharpe",
                "retorno_anual": "base_retorno_anual",
                "max_drawdown": "base_drawdown",
                "cvar_95_diario": "base_cvar",
            }
        ),
        on=["scenario", "portfolio"],
        how="left",
    )
    merged["delta_sharpe_vs_markowitz"] = merged["sharpe"] - merged["base_sharpe"]
    merged["delta_retorno_vs_markowitz"] = merged["retorno_anual"] - merged["base_retorno_anual"]
    merged["delta_drawdown_vs_markowitz"] = merged["max_drawdown"] - merged["base_drawdown"]
    detail_path = OUTPUT_DIR / f"{stage}_detalle_vs_markowitz.csv"
    merged.to_csv(detail_path, index=False)

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
            retorno_anual_mean=("retorno_anual", "mean"),
            drawdown_mean=("max_drawdown", "mean"),
            cvar_mean=("cvar_95_diario", "mean"),
            delta_sharpe_mean=("delta_sharpe_vs_markowitz", "mean"),
            delta_drawdown_mean=("delta_drawdown_vs_markowitz", "mean"),
            n_obs=("sharpe", "count"),
        )
        .reset_index()
    )
    summary["sharpe_std"] = summary["sharpe_std"].fillna(0.0)
    summary["score_robusto"] = robust_score(summary)
    summary = summary.sort_values("score_robusto", ascending=False).reset_index(drop=True)
    summary.to_csv(OUTPUT_DIR / f"{stage}_ranking.csv", index=False)
    return summary


def robust_score(summary: pd.DataFrame) -> pd.Series:
    def norm(col: str, higher_is_better: bool = True) -> pd.Series:
        s = summary[col].astype(float)
        if not higher_is_better:
            s = -s
        span = s.max() - s.min()
        if abs(span) < 1e-12:
            return pd.Series(np.ones(len(s)) * 0.5, index=summary.index)
        return (s - s.min()) / span

    base_score = (
        0.35 * norm("sharpe_mean")
        + 0.25 * norm("delta_sharpe_mean")
        + 0.15 * norm("drawdown_mean")
        + 0.10 * norm("cvar_mean", higher_is_better=False)
        + 0.10 * norm("sharpe_std", higher_is_better=False)
        + 0.05 * norm("retorno_anual_mean")
    )
    # El feedback del profesor pide resiliencia, no solo ganar en Sharpe.
    # Regla: si el drawdown empeora mas de 3 pp vs Markowitz, la configuracion
    # queda degradada en el ranking aunque tenga mayor retorno.
    delta_drawdown = summary["delta_drawdown_mean"].astype(float)
    excess_drawdown = np.maximum(0.0, -0.03 - delta_drawdown)
    drawdown_penalty = np.minimum(excess_drawdown / 0.08, 1.0)
    degraded_score = 0.45 * base_score - 0.25 * drawdown_penalty
    return pd.Series(np.where(delta_drawdown >= -0.03, base_score, degraded_score), index=summary.index)


def generate_stage2_configs(winner: ViewConfig) -> List[ViewConfig]:
    configs: List[ViewConfig] = []
    if winner.family == "marketcap_momentum":
        for lookback in [63, 126, 252]:
            for universe in [20, 40, 60]:
                for long_short in [5, 10, 20]:
                    if 2 * long_short > universe:
                        continue
                    for weighting in ["equal", "marketcap"]:
                        configs.append(
                            replace(
                                winner,
                                config_id=f"stage2_mcap_L{lookback}_U{universe}_K{long_short}_{weighting}",
                                lookback_days=lookback,
                                market_cap_universe_size=universe,
                                long_short_size=long_short,
                                p_weighting=weighting,
                            )
                        )
    elif winner.family == "momentum":
        for lookback in [63, 126, 252]:
            for k in [10, 20, 30]:
                for weighting in ["equal", "rank"]:
                    configs.append(
                        replace(
                            winner,
                            config_id=f"stage2_mom_L{lookback}_K{k}_{weighting}",
                            lookback_days=lookback,
                            top_bottom_size=k,
                            p_weighting=weighting,
                        )
                    )
    else:
        for assumed in [0.04, 0.05, 0.06]:
            for beta in [0.5, 1.0, 1.5]:
                configs.append(
                    replace(
                        winner,
                        config_id=f"stage2_unemp_U{assumed:.2f}_B{beta:.1f}",
                        unemployment_assumed=assumed,
                        macro_beta=beta,
                    )
                )
    return configs


def run_stage(
    name: str,
    configs: Sequence[ViewConfig],
    datasets: Dict[str, pd.DataFrame],
    meta: pd.DataFrame,
    base_df: pd.DataFrame,
    profiles: Sequence[RiskProfile],
) -> Tuple[ViewConfig, pd.DataFrame, pd.DataFrame]:
    frames = []
    view_frames = []
    log(f"{name}: evaluando {len(configs)} configuraciones con {len(profiles)} perfil(es)")
    for i, config in enumerate(configs, start=1):
        log(f"  {name} {i}/{len(configs)}: {config.config_id}")
        df, views = evaluate_rebalanced_config(datasets, meta, config, profiles, name)
        frames.append(df)
        view_frames.append(views)
    stage_df = pd.concat(frames, ignore_index=True)
    stage_views = pd.concat(view_frames, ignore_index=True)
    stage_df.to_csv(OUTPUT_DIR / f"{name}_resultados.csv", index=False)
    stage_views.to_csv(OUTPUT_DIR / f"{name}_views_segmentos.csv", index=False)
    ranking = score_candidates(stage_df, base_df, name)
    winner_id = str(ranking.iloc[0]["config_id"])
    winner = next(c for c in configs if c.config_id == winner_id)
    log(f"{name}: ganador {winner.config_id} score={ranking.iloc[0]['score_robusto']:.3f}")
    return winner, stage_df, ranking


def draw_bar_chart(path: Path, labels: List[str], values: List[float], title: str, ylabel: str) -> None:
    width, height = 1000, 620
    margin_l, margin_r, margin_t, margin_b = 90, 40, 80, 150
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((margin_l, 25), title, fill=(20, 25, 35), font=font)
    vals = np.array(values, dtype=float)
    vmin = min(0.0, float(vals.min()))
    vmax = max(0.0, float(vals.max()))
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    zero_y = margin_t + int((vmax / (vmax - vmin)) * plot_h)
    draw.line((margin_l, margin_t, margin_l, margin_t + plot_h), fill=(90, 90, 90))
    draw.line((margin_l, zero_y, margin_l + plot_w, zero_y), fill=(120, 120, 120))
    bar_w = max(12, int(plot_w / max(len(labels), 1) * 0.62))
    for i, (label, value) in enumerate(zip(labels, values)):
        cx = margin_l + int((i + 0.5) * plot_w / len(labels))
        y = margin_t + int((vmax - value) / (vmax - vmin) * plot_h)
        color = (42, 157, 143) if value >= 0 else (231, 111, 81)
        draw.rectangle((cx - bar_w // 2, min(y, zero_y), cx + bar_w // 2, max(y, zero_y)), fill=color)
        draw.text((cx - 24, min(y, zero_y) - 18), f"{value:.2f}", fill=(20, 25, 35), font=font)
        short = label[:18]
        draw.text((cx - 45, margin_t + plot_h + 15), short, fill=(20, 25, 35), font=font)
    draw.text((15, margin_t + 10), ylabel, fill=(20, 25, 35), font=font)
    img.save(path)


def draw_heatmap(path: Path, df: pd.DataFrame, x_col: str, y_col: str, value_col: str, title: str) -> None:
    pivot = df.pivot_table(index=y_col, columns=x_col, values=value_col, aggfunc="mean")
    xs = list(pivot.columns)
    ys = list(pivot.index)
    cell_w, cell_h = 120, 60
    margin_l, margin_t = 180, 80
    width = margin_l + cell_w * len(xs) + 60
    height = margin_t + cell_h * len(ys) + 80
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((margin_l, 25), title, fill=(20, 25, 35), font=font)
    values = pivot.to_numpy(dtype=float)
    vmin = float(np.nanmin(values))
    vmax = float(np.nanmax(values))
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    for ix, x in enumerate(xs):
        draw.text((margin_l + ix * cell_w + 30, margin_t - 25), str(x), fill=(20, 25, 35), font=font)
    for iy, y in enumerate(ys):
        draw.text((20, margin_t + iy * cell_h + 20), str(y), fill=(20, 25, 35), font=font)
        for ix, x in enumerate(xs):
            val = pivot.loc[y, x]
            ratio = (float(val) - vmin) / (vmax - vmin) if pd.notna(val) else 0.0
            color = (int(250 - 200 * ratio), int(235 - 120 * ratio), int(215 - 170 * ratio))
            rect = (margin_l + ix * cell_w, margin_t + iy * cell_h, margin_l + (ix + 1) * cell_w, margin_t + (iy + 1) * cell_h)
            draw.rectangle(rect, fill=color, outline=(240, 240, 240))
            if pd.notna(val):
                draw.text((rect[0] + 35, rect[1] + 22), f"{float(val):.2f}", fill=(20, 25, 35), font=font)
    img.save(path)


def simulate_p4(metrics_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(20260607)
    neutral = metrics_df.copy()
    for _, row in neutral.iterrows():
        profile = PROFILE_BY_LABEL[row["portfolio"]]
        ann_return = safe_float(row["retorno_anual"])
        ann_vol = max(safe_float(row["volatilidad_anual"]), 1e-6)
        weekly_mu = (1.0 + ann_return) ** (1.0 / 52.0) - 1.0
        weekly_sigma = ann_vol / math.sqrt(52.0)
        p_accept = 1.0 / (1.0 + math.exp(-(ann_return - profile.loss_tolerance)))
        wealth = np.full(N_SIMULATIONS, INITIAL_CAPITAL)
        active = rng.random(N_SIMULATIONS) < p_accept
        company = np.zeros(N_SIMULATIONS, dtype=float)
        withdrawn = np.zeros(N_SIMULATIONS, dtype=bool)
        for _week in range(N_WEEKS):
            idx = active & ~withdrawn
            if not idx.any():
                break
            rets = rng.normal(weekly_mu, weekly_sigma, idx.sum())
            wealth[idx] *= np.maximum(1.0 + rets, 0.01)
            # La utilidad de empresa depende solo del saldo administrado activo.
            # No se cobra comision adicional por aceptar rebalanceos/recomendaciones.
            company[idx] += wealth[idx] * COMPANY_WEEKLY_FEE_RATE
            loss = np.maximum((INITIAL_CAPITAL - wealth[idx]) / INITIAL_CAPITAL, 0.0)
            p_withdraw = np.where(
                loss > profile.loss_tolerance,
                1.0 / (1.0 + np.exp(-(loss - profile.loss_tolerance))),
                0.0,
            )
            withdraw_now = rng.random(idx.sum()) < p_withdraw
            full_idx = np.where(idx)[0]
            withdrawn[full_idx[withdraw_now]] = True
        rows.append(
            {
                "modelo": row["modelo"],
                "scenario": row["scenario"],
                "portfolio": row["portfolio"],
                "terminal_wealth_mean": float(wealth.mean()),
                "prob_profit": float((wealth > INITIAL_CAPITAL).mean()),
                "withdrawal_rate": float(withdrawn.mean()),
                "company_revenue_mean": float(company.mean()),
                "p4_score": float(wealth.mean() + company.mean() - INITIAL_CAPITAL * withdrawn.mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("p4_score", ascending=False)


def final_recommendation(final_bl: pd.DataFrame, markowitz: pd.DataFrame) -> pd.DataFrame:
    bl = final_bl.copy()
    mk = markowitz.copy()
    merged = bl.merge(
        mk[["scenario", "portfolio", "sharpe", "retorno_anual", "max_drawdown", "cvar_95_diario"]].rename(
            columns={
                "sharpe": "sharpe_markowitz",
                "retorno_anual": "retorno_anual_markowitz",
                "max_drawdown": "drawdown_markowitz",
                "cvar_95_diario": "cvar_markowitz",
            }
        ),
        on=["scenario", "portfolio"],
        how="left",
    )
    merged["mejora_pct_sharpe_vs_markowitz"] = (
        (merged["sharpe"] - merged["sharpe_markowitz"]) / merged["sharpe_markowitz"].abs().replace(0, np.nan)
    )
    merged["delta_drawdown_vs_markowitz"] = merged["max_drawdown"] - merged["drawdown_markowitz"]
    merged["recomendacion"] = np.where(
        (merged["mejora_pct_sharpe_vs_markowitz"] > 0) & (merged["delta_drawdown_vs_markowitz"] > -0.03),
        "Recomendado",
        "No dominante",
    )
    return merged.sort_values(["scenario", "portfolio"])


def write_search_space() -> None:
    rows = [
        ("1_familia_view", "familia/P/Q base", "momentum, market-cap momentum 6M, market-cap momentum 1Y, desempleo", "tau=.05, confianza base", "score robusto vs Markowitz"),
        ("2_estructura_P", "lookback/universo/long-short/pesos", "lookback {63,126,252}; universo {20,40,60}; k {5,10,20}; pesos {equal,marketcap}", "Q=spread empirico, tau=.05", "score robusto con perfil Neutro"),
        ("3_intensidad_Q", "q_scale", "{0.5,1.0,1.5}", "P ganador, confianza base", "evitar sobre-reaccion de la view"),
        ("4_Omega", "confidence", "momentum {0.35,0.50,0.65,0.80}; desempleo {0.20,0.35,0.50}", "P y Q fijos", "balance prior-view"),
        ("5_tau", "tau", "{0.01,0.025,0.05,0.10,0.20}", "P,Q,Omega fijos", "sensibilidad final del prior"),
    ]
    pd.DataFrame(rows, columns=["etapa", "parametro", "valores_probados", "valores_fijos", "criterio"]).to_csv(
        OUTPUT_DIR / "01_espacio_busqueda.csv", index=False
    )


def write_markdown_summary(
    winners: Dict[str, ViewConfig],
    rankings: Dict[str, pd.DataFrame],
    recommendation: pd.DataFrame,
    robust: pd.DataFrame,
    p4: pd.DataFrame,
) -> None:
    lines = ["# Calibracion secuencial Black-Litterman", ""]
    lines.append("## Ganadores por etapa")
    for stage, config in winners.items():
        row = rankings[stage].iloc[0]
        lines.append(
            f"- {stage}: **{config.view_label}** (`{config.config_id}`), score robusto {row['score_robusto']:.3f}, "
            f"Sharpe medio {row['sharpe_mean']:.3f}, delta Sharpe vs Markowitz {row['delta_sharpe_mean']:.3f}."
        )
    lines.extend(["", "## Configuracion final"])
    final = winners["stage5_tau"]
    if final.family == "unemployment":
        lines.append(
            f"- Familia: unemployment; desempleo asumido={final.unemployment_assumed:.1%}; "
            f"desempleo neutral={final.unemployment_neutral:.1%}; beta macro={final.macro_beta}; "
            f"q_scale={final.q_scale}; confianza={final.confidence}; tau={final.tau}. "
            "La matriz P favorece sectores ciclicos frente a defensivos bajo desempleo menor al neutral."
        )
    else:
        active_size = final.top_bottom_size if final.family == "momentum" else final.long_short_size
        universe = "601 activos" if final.family == "momentum" else str(final.market_cap_universe_size)
        lines.append(
            f"- Familia: {final.family}; lookback={final.lookback_days}; universo={universe}; "
            f"long/short={active_size}; pesos P={final.p_weighting}; q_scale={final.q_scale}; "
            f"confianza={final.confidence}; tau={final.tau}."
        )
    lines.extend(["", "## Recomendacion por perfil"])
    for _, row in recommendation.iterrows():
        mejora = row["mejora_pct_sharpe_vs_markowitz"]
        lines.append(
            f"- {row['scenario']} / {row['portfolio']}: Sharpe BL {row['sharpe']:.2f} vs Markowitz "
            f"{row['sharpe_markowitz']:.2f}; mejora {mejora:.1%}; drawdown BL {row['max_drawdown']:.1%}; "
            f"{row['recomendacion']}."
        )
    lines.extend(["", "## Validacion robusta final"])
    robust_summary = robust.groupby(["modelo", "portfolio"], as_index=False).agg(
        sharpe_mean=("sharpe", "mean"),
        sharpe_std=("sharpe", "std"),
        drawdown_mean=("max_drawdown", "mean"),
    )
    for _, row in robust_summary.iterrows():
        lines.append(
            f"- {row['modelo']} / {row['portfolio']}: Sharpe medio {row['sharpe_mean']:.2f}, "
            f"desv. {row['sharpe_std']:.2f}, drawdown medio {row['drawdown_mean']:.1%}."
        )
    lines.extend(["", "## P4 posterior"])
    for _, row in p4.head(8).iterrows():
        lines.append(
            f"- {row['modelo']} / {row['scenario']} / {row['portfolio']}: riqueza USD {row['terminal_wealth_mean']:.0f}, "
            f"retiro {row['withdrawal_rate']:.1%}, utilidad empresa USD {row['company_revenue_mean']:.0f}, score {row['p4_score']:.0f}."
        )
    (OUTPUT_DIR / "historia_calibracion_bl.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    t0 = time.perf_counter()
    write_search_space()
    meta = read_metadata()
    datasets = {
        "sin_pandemia": load_returns_for_scenario(meta, "sin_pandemia"),
        "con_pandemia": load_returns_for_scenario(meta, "con_pandemia"),
    }
    meta = meta[meta["ticker"].isin(datasets["sin_pandemia"].columns)].copy()
    common = [t for t in meta["ticker"].tolist() if t in datasets["sin_pandemia"].columns and t in datasets["con_pandemia"].columns]
    datasets = {k: v[common].copy() for k, v in datasets.items()}
    meta = meta.set_index("ticker").reindex(common).reset_index()
    log(f"Universo comun: {len(common)} activos")

    log("Calculando Markowitz base comparable")
    markowitz_base, _ = evaluate_rebalanced_config(datasets, meta, None, RISK_PROFILES, "00_markowitz_base")
    markowitz_base["modelo"] = "Markowitz base"
    markowitz_base.to_csv(OUTPUT_DIR / "00_markowitz_base.csv", index=False)

    winners: Dict[str, ViewConfig] = {}
    rankings: Dict[str, pd.DataFrame] = {}

    winner1, _, ranking1 = run_stage("stage1_familia_view", BASE_VIEW_CONFIGS, datasets, meta, markowitz_base, RISK_PROFILES)
    winners["stage1_familia_view"] = winner1
    rankings["stage1_familia_view"] = ranking1

    stage2_configs = generate_stage2_configs(winner1)
    winner2, stage2_df, ranking2 = run_stage("stage2_estructura_P", stage2_configs, datasets, meta, markowitz_base, CALIBRATION_PROFILES)
    winners["stage2_estructura_P"] = winner2
    rankings["stage2_estructura_P"] = ranking2

    q_configs = [replace(winner2, config_id=f"stage3_q_scale_{q:.1f}", q_scale=q) for q in [0.5, 1.0, 1.5]]
    winner3, _, ranking3 = run_stage("stage3_intensidad_Q", q_configs, datasets, meta, markowitz_base, CALIBRATION_PROFILES)
    winners["stage3_intensidad_Q"] = winner3
    rankings["stage3_intensidad_Q"] = ranking3

    confidence_grid = [0.20, 0.35, 0.50] if winner3.family == "unemployment" else [0.35, 0.50, 0.65, 0.80]
    conf_configs = [replace(winner3, config_id=f"stage4_conf_{c:.2f}", confidence=c) for c in confidence_grid]
    winner4, _, ranking4 = run_stage("stage4_confianza_Omega", conf_configs, datasets, meta, markowitz_base, CALIBRATION_PROFILES)
    winners["stage4_confianza_Omega"] = winner4
    rankings["stage4_confianza_Omega"] = ranking4

    tau_configs = [replace(winner4, config_id=f"stage5_tau_{tau:.3f}", tau=tau) for tau in [0.01, 0.025, 0.05, 0.10, 0.20]]
    winner5, _, ranking5 = run_stage("stage5_tau", tau_configs, datasets, meta, markowitz_base, CALIBRATION_PROFILES)
    winners["stage5_tau"] = winner5
    rankings["stage5_tau"] = ranking5

    log("Recalculando configuracion final para todos los perfiles")
    final_bl, final_views = evaluate_rebalanced_config(datasets, meta, winner5, RISK_PROFILES, "final_bl_calibrado")
    final_bl["modelo"] = "BL calibrado"
    final_bl.to_csv(OUTPUT_DIR / "08_final_bl_calibrado.csv", index=False)
    final_views.to_csv(OUTPUT_DIR / "08_final_bl_calibrado_views.csv", index=False)

    recommendation = final_recommendation(final_bl, markowitz_base)
    recommendation.to_csv(OUTPUT_DIR / "09_recomendacion_por_perfil.csv", index=False)

    log("Validacion robusta final")
    robust_frames = []
    for horizon in [(7, 2), (6, 2), (5, 2), (4, 2)]:
        for offset in [0, 1, 2]:
            try:
                bl_r, _ = evaluate_rebalanced_config(
                    {"sin_pandemia": datasets["sin_pandemia"]}, meta, winner5, [PROFILE_BY_LABEL["Neutro"]], "robust_bl", horizon[0], horizon[1], offset
                )
                mk_r, _ = evaluate_rebalanced_config(
                    {"sin_pandemia": datasets["sin_pandemia"]}, meta, None, [PROFILE_BY_LABEL["Neutro"]], "robust_markowitz", horizon[0], horizon[1], offset
                )
                bl_r["modelo"] = "BL calibrado"
                mk_r["modelo"] = "Markowitz base"
                robust_frames.extend([bl_r, mk_r])
            except Exception as exc:
                log(f"  ventana robusta omitida h{horizon[0]}_f{horizon[1]} offset {offset}: {exc}")
    robust = pd.concat(robust_frames, ignore_index=True)
    robust.to_csv(OUTPUT_DIR / "10_validacion_robusta_final.csv", index=False)

    p4_input = pd.concat(
        [
            final_bl[["modelo", "scenario", "portfolio", "retorno_anual", "volatilidad_anual"]],
            markowitz_base.assign(modelo="Markowitz base")[["modelo", "scenario", "portfolio", "retorno_anual", "volatilidad_anual"]],
        ],
        ignore_index=True,
    )
    p4 = simulate_p4(p4_input)
    p4.to_csv(OUTPUT_DIR / "11_p4_bl_calibrado_vs_markowitz.csv", index=False)

    # Graficos simples para la historia.
    path_scores = [rankings[k].iloc[0]["score_robusto"] for k in rankings]
    draw_bar_chart(
        OUTPUT_DIR / "fig_01_camino_calibracion_score.png",
        ["Familia", "P", "Q", "Omega", "tau"],
        path_scores,
        "Camino de calibracion BL: score robusto ganador por etapa",
        "Score",
    )
    if winner2.family == "unemployment" and {"unemployment_assumed", "macro_beta", "score_robusto"}.issubset(ranking2.columns):
        draw_heatmap(
            OUTPUT_DIR / "fig_02_heatmap_estructura_P.png",
            ranking2,
            "unemployment_assumed",
            "macro_beta",
            "score_robusto",
            "Estructura macro: score por desempleo asumido y beta",
        )
    elif {"lookback_days", "market_cap_universe_size", "score_robusto"}.issubset(ranking2.columns):
        draw_heatmap(
            OUTPUT_DIR / "fig_02_heatmap_estructura_P.png",
            ranking2,
            "lookback_days",
            "market_cap_universe_size",
            "score_robusto",
            "Estructura P: score por lookback y universo market-cap",
        )
    draw_bar_chart(
        OUTPUT_DIR / "fig_03_sensibilidad_confianza.png",
        [str(x) for x in ranking4["confidence"].tolist()],
        ranking4["score_robusto"].tolist(),
        "Sensibilidad de Omega: score por confianza",
        "Score",
    )
    draw_bar_chart(
        OUTPUT_DIR / "fig_04_sensibilidad_tau.png",
        [str(x) for x in ranking5["tau"].tolist()],
        ranking5["score_robusto"].tolist(),
        "Sensibilidad final: score por tau",
        "Score",
    )
    rec_plot = recommendation.copy()
    rec_plot["label"] = rec_plot["scenario"] + " " + rec_plot["portfolio"]
    draw_bar_chart(
        OUTPUT_DIR / "fig_05_mejora_sharpe_por_perfil.png",
        rec_plot["label"].tolist(),
        rec_plot["mejora_pct_sharpe_vs_markowitz"].fillna(0.0).tolist(),
        "Mejora porcentual de Sharpe BL calibrado vs Markowitz",
        "Mejora",
    )

    write_markdown_summary(winners, rankings, recommendation, robust, p4)
    checks = {
        "activos": len(common),
        "stage1_configs": len(BASE_VIEW_CONFIGS),
        "stage2_configs": len(stage2_configs),
        "final_rows": len(final_bl),
        "robust_rows": len(robust),
        "p4_rows": len(p4),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    pd.DataFrame([checks]).to_csv(OUTPUT_DIR / "99_checks_calibracion.csv", index=False)
    log(f"Listo en {checks['elapsed_seconds']}s. Outputs en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
