"""
Pipeline de entrega final Markowitz vs portafolio equiponderado.

Este modulo centraliza la logica usada por los notebooks de Modelo_finanzas:
- carga del dataset real Data/Historical_Stocks,
- reconstruccion del universo F5,
- construccion de sub-universos por perfil de riesgo,
- optimizacion Markowitz sin tasa libre de riesgo,
- benchmark equiponderado top 20 por market cap,
- exportacion de tablas finales.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


TRADING_DAYS_PER_YEAR = 252
WEEKS_PER_YEAR = 52
ESTIMATION_YEARS = 8
ESTIMATION_WEEKS = ESTIMATION_YEARS * WEEKS_PER_YEAR
MIN_VALID_WEEKS = 350
PROJECTION_START = pd.Timestamp("2026-05-03")
EXCLUDE_START = pd.Timestamp("2020-01-01")
EXCLUDE_END = pd.Timestamp("2022-12-31")
SHRINKAGE_COVARIANCE = 0.10
EPS_COV = 1e-8
DEFAULT_MAX_WEIGHT = 0.40
DEFAULT_TOP_TICKERS = 10

PROFILE_ORDER = [
    "Muy conservador",
    "Conservador",
    "Neutro",
    "Arriesgado",
    "Muy arriesgado",
]

DEFENSIVE_SECTORS = {"Utilities", "Consumer Defensive"}
GROWTH_SECTORS = {"Technology", "Consumer Cyclical", "Communication Services"}


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    loss_tolerance: float
    gamma: float
    max_weight: float
    n_assets: int
    max_sector_fraction: float


PROFILE_CONFIGS: Dict[str, ProfileConfig] = {
    "Muy conservador": ProfileConfig("Muy conservador", 0.00, 60.0, 0.05, 40, 0.30),
    "Conservador": ProfileConfig("Conservador", 0.05, 35.0, 0.07, 60, 0.30),
    "Neutro": ProfileConfig("Neutro", 0.15, 18.0, 0.10, 80, 0.25),
    "Arriesgado": ProfileConfig("Arriesgado", 0.30, 8.0, 0.15, 100, 0.30),
    "Muy arriesgado": ProfileConfig("Muy arriesgado", 0.40, 4.0, 0.20, 120, 0.35),
}


@dataclass(frozen=True)
class Paths:
    root: Path
    model_dir: Path
    data_dir: Path
    outputs_dir: Path


def resolve_paths(model_dir: Optional[Path] = None) -> Paths:
    """Resuelve rutas esperadas desde notebooks o ejecucion directa."""
    if model_dir is None:
        model_dir = Path(__file__).resolve().parent
    model_dir = Path(model_dir).resolve()
    root = model_dir.parent
    data_dir = root / "Data" / "Historical_Stocks"
    outputs_dir = model_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return Paths(root=root, model_dir=model_dir, data_dir=data_dir, outputs_dir=outputs_dir)


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def parse_stocks_info(info_file: Path) -> pd.DataFrame:
    """Parsea stocks_info.txt en un DataFrame de metadata util para F5."""
    records = []
    with open(info_file, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or ";" not in line:
                continue
            ticker, raw = line.split(";", 1)
            ticker = ticker.strip().upper()
            try:
                data = ast.literal_eval(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            records.append(
                {
                    "ticker": ticker,
                    "short_name": data.get("shortName"),
                    "long_name": data.get("longName"),
                    "sector": data.get("sector") or data.get("sectorDisp"),
                    "industry": data.get("industry") or data.get("industryDisp"),
                    "market_cap": _safe_float(data.get("marketCap")),
                    "current_price_meta": _safe_float(
                        data.get("currentPrice") or data.get("regularMarketPrice")
                    ),
                    "quote_type": data.get("quoteType"),
                    "dividend_yield": _safe_float(data.get("dividendYield")),
                }
            )
    return pd.DataFrame(records)


def load_stock_history(csv_path: Path) -> Optional[pd.DataFrame]:
    """Carga un CSV historico Yahoo Finance y normaliza columnas clave."""
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return None
    required = {"Date", "Close", "Dividends"}
    if df.empty or not required.issubset(df.columns):
        return None
    dates = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert(None)
    out = pd.DataFrame(
        {
            "date": dates.dt.normalize(),
            "close": pd.to_numeric(df["Close"], errors="coerce"),
            "dividends": pd.to_numeric(df["Dividends"], errors="coerce").fillna(0.0),
        }
    )
    out = out.dropna(subset=["date", "close"])
    out = out[out["close"] > 0]
    out = out.sort_values("date").drop_duplicates("date", keep="last")
    return out.reset_index(drop=True) if not out.empty else None


def compute_history_stats(df: pd.DataFrame) -> Dict[str, object]:
    """Calcula estadisticas historicas usadas por filtros y seleccion."""
    closes = df["close"].to_numpy(dtype=float)
    n_rows = int(len(closes))
    current_price = float(closes[-1])
    start_date = pd.Timestamp(df["date"].iloc[0]).date().isoformat()
    end_date = pd.Timestamp(df["date"].iloc[-1]).date().isoformat()
    dividends_total = float(df["dividends"].sum())
    has_dividends = bool(dividends_total > 0)
    if n_rows < 10:
        cagr = np.nan
        ann_volatility = np.nan
    else:
        log_returns = np.diff(np.log(closes))
        cagr = float((closes[-1] / closes[0]) ** (TRADING_DAYS_PER_YEAR / n_rows) - 1)
        ann_volatility = float(np.nanstd(log_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    return {
        "n_rows": n_rows,
        "start_date": start_date,
        "end_date": end_date,
        "current_price": current_price,
        "cagr": cagr,
        "ann_volatility": ann_volatility,
        "has_dividends": has_dividends,
        "dividends_total": dividends_total,
    }


def build_dataset(paths: Optional[Paths] = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carga metadata e historicos, aplica filtros F5 y retorna:
    universe_f5, daily_returns, weekly_total_returns.
    """
    paths = paths or resolve_paths()
    metadata = parse_stocks_info(paths.data_dir / "stocks_info.txt")

    stats_records: List[Dict[str, object]] = []
    close_series: Dict[str, pd.Series] = {}
    dividend_series: Dict[str, pd.Series] = {}

    for csv_path in sorted(paths.data_dir.glob("stock_return_*.csv")):
        ticker = csv_path.stem.replace("stock_return_", "").upper()
        df = load_stock_history(csv_path)
        if df is None:
            continue
        stats = compute_history_stats(df)
        stats["ticker"] = ticker
        stats_records.append(stats)
        close_series[ticker] = pd.Series(df["close"].to_numpy(dtype=float), index=df["date"])
        dividend_series[ticker] = pd.Series(df["dividends"].to_numpy(dtype=float), index=df["date"])

    stats_df = pd.DataFrame(stats_records)
    universe = stats_df.merge(metadata, on="ticker", how="left")
    universe["market_cap"] = pd.to_numeric(universe["market_cap"], errors="coerce")
    universe["sector"] = universe["sector"].fillna("Unknown")
    universe["industry"] = universe["industry"].fillna("Unknown")

    f5 = universe[
        universe["cagr"].notna()
        & universe["ann_volatility"].notna()
        & universe["current_price"].notna()
        & universe["market_cap"].notna()
        & (universe["n_rows"] >= 2520)
        & (universe["current_price"] >= 5.0)
        & (universe["market_cap"] >= 2_000_000_000)
        & (universe["ann_volatility"].between(0.05, 1.0))
        & (universe["sector"] != "Unknown")
        & (universe["industry"] != "Shell Companies")
    ].copy()
    f5 = f5.sort_values(["sector", "market_cap"], ascending=[True, False]).reset_index(drop=True)

    prices = pd.DataFrame({ticker: close_series[ticker] for ticker in f5["ticker"]})
    prices = prices.sort_index()
    daily_returns = np.log(prices / prices.shift(1)).replace([np.inf, -np.inf], np.nan)
    weekly_prices = prices.resample("W-FRI").last()
    dividends = pd.DataFrame({ticker: dividend_series[ticker] for ticker in f5["ticker"]})
    dividends = dividends.reindex(prices.index).fillna(0.0).sort_index()
    weekly_dividends = dividends.resample("W-FRI").sum().reindex(weekly_prices.index).fillna(0.0)
    weekly_returns = (
        (weekly_prices - weekly_prices.shift(1) + weekly_dividends)
        / weekly_prices.shift(1)
    ).replace([np.inf, -np.inf], np.nan)
    weekly_returns = weekly_returns.where((weekly_returns >= -0.95) & (weekly_returns <= 3.0))

    return f5, daily_returns, weekly_returns


def prepare_estimation_window(weekly_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Prepara ventana efectiva de estimacion semanal.

    Se excluye 2020-2022 para hacer comparable la metodologia con el notebook
    de referencia y luego se toman las ultimas 416 semanas validas antes de 2026.
    """
    returns = weekly_returns.copy()
    returns.index = pd.to_datetime(returns.index)
    returns = returns[returns.index < PROJECTION_START]
    returns = returns[(returns.index < EXCLUDE_START) | (returns.index > EXCLUDE_END)]
    returns = returns.dropna(how="all")
    returns = returns.tail(ESTIMATION_WEEKS)
    valid_counts = returns.notna().sum()
    valid_tickers = valid_counts[valid_counts >= MIN_VALID_WEEKS].index.tolist()
    returns = returns[valid_tickers]
    if returns.empty:
        raise ValueError("No quedaron activos con suficientes semanas validas.")
    return returns.apply(lambda col: col.fillna(col.median()), axis=0)


def estimate_weekly_parameters(returns: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    """Estima media semanal y covarianza semanal con shrinkage diagonal."""
    mu = returns.mean()
    cov = returns.cov()
    diag = np.diag(np.diag(cov.to_numpy(dtype=float)))
    shrunk = (1.0 - SHRINKAGE_COVARIANCE) * cov.to_numpy(dtype=float) + SHRINKAGE_COVARIANCE * diag
    shrunk = (shrunk + shrunk.T) / 2.0
    values, vectors = np.linalg.eigh(shrunk)
    values = np.clip(values, EPS_COV, None)
    cov_psd = vectors @ np.diag(values) @ vectors.T
    return mu, pd.DataFrame(cov_psd, index=cov.index, columns=cov.columns)


def build_asset_stats(universe_f5: pd.DataFrame, estimation_returns: pd.DataFrame) -> pd.DataFrame:
    """Agrega metricas semanales anualizadas usadas para seleccionar subuniversos."""
    stats = pd.DataFrame(
        {
            "ticker": estimation_returns.columns,
            "return_annual_hist": estimation_returns.mean().to_numpy(dtype=float) * WEEKS_PER_YEAR,
            "volatility_annual_hist": estimation_returns.std().to_numpy(dtype=float) * np.sqrt(WEEKS_PER_YEAR),
        }
    )
    stats["sharpe_hist"] = stats["return_annual_hist"] / stats["volatility_annual_hist"].replace(0, np.nan)
    return stats.merge(universe_f5, on="ticker", how="left")


def save_prepared_outputs(
    universe_f5: pd.DataFrame,
    daily_returns: pd.DataFrame,
    weekly_returns: pd.DataFrame,
    paths: Optional[Paths] = None,
) -> Dict[str, Path]:
    """Guarda artefactos base de datos y parametros anualizados."""
    paths = paths or resolve_paths()
    estimation_returns = prepare_estimation_window(weekly_returns)
    mu_weekly, sigma_weekly = estimate_weekly_parameters(estimation_returns)
    mu = mu_weekly * WEEKS_PER_YEAR
    sigma = sigma_weekly * WEEKS_PER_YEAR
    sector_summary = (
        universe_f5.groupby("sector")
        .agg(
            n=("ticker", "count"),
            avg_ann_volatility=("ann_volatility", "mean"),
            avg_cagr=("cagr", "mean"),
            pct_with_dividends=("has_dividends", "mean"),
            total_market_cap=("market_cap", "sum"),
        )
        .sort_values("n", ascending=False)
        .reset_index()
    )

    outputs = {
        "universe_f5": paths.outputs_dir / "universe_f5.csv",
        "daily_returns": paths.outputs_dir / "daily_returns.pkl",
        "weekly_returns": paths.outputs_dir / "weekly_returns.pkl",
        "estimation_returns": paths.outputs_dir / "estimation_returns.pkl",
        "mu": paths.outputs_dir / "mu.pkl",
        "sigma": paths.outputs_dir / "sigma.pkl",
        "sector_summary": paths.outputs_dir / "sector_summary.csv",
    }
    universe_f5.to_csv(outputs["universe_f5"], index=False)
    daily_returns.to_pickle(outputs["daily_returns"])
    weekly_returns.to_pickle(outputs["weekly_returns"])
    estimation_returns.to_pickle(outputs["estimation_returns"])
    mu.to_pickle(outputs["mu"])
    sigma.to_pickle(outputs["sigma"])
    sector_summary.to_csv(outputs["sector_summary"], index=False)
    return outputs


def load_prepared_outputs(paths: Optional[Paths] = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    """Carga artefactos generados por 01_Preparar_Datos."""
    paths = paths or resolve_paths()
    universe_f5 = pd.read_csv(paths.outputs_dir / "universe_f5.csv")
    daily_returns = pd.read_pickle(paths.outputs_dir / "daily_returns.pkl")
    weekly_returns = pd.read_pickle(paths.outputs_dir / "weekly_returns.pkl")
    mu = pd.read_pickle(paths.outputs_dir / "mu.pkl")
    sigma = pd.read_pickle(paths.outputs_dir / "sigma.pkl")
    return universe_f5, daily_returns, weekly_returns, mu, sigma


def _rank_pct_asc(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, ascending=True).fillna(0.0)


def _rank_pct_desc(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, ascending=False).fillna(0.0)


def _select_with_sector_limit(df: pd.DataFrame, n: int, max_sector_fraction: float) -> pd.DataFrame:
    """Selecciona por score respetando un limite aproximado por sector."""
    max_per_sector = max(1, int(np.ceil(n * max_sector_fraction)))
    selected_rows = []
    sector_counts: Dict[str, int] = {}

    for _, row in df.sort_values("score", ascending=False).iterrows():
        sector = row.get("sector", "Unknown")
        if sector_counts.get(sector, 0) < max_per_sector:
            selected_rows.append(row)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if len(selected_rows) >= n:
            break

    selected = pd.DataFrame(selected_rows)
    if len(selected) < n:
        missing = n - len(selected)
        already = set(selected["ticker"]) if not selected.empty else set()
        extra = df[~df["ticker"].isin(already)].sort_values("score", ascending=False).head(missing)
        selected = pd.concat([selected, extra], ignore_index=True)
    return selected.head(n)


def build_profile_subuniverses(universe_f5: pd.DataFrame, estimation_returns: pd.DataFrame) -> pd.DataFrame:
    """Construye sub-universos por perfil usando scores comparables al notebook externo."""
    stats = build_asset_stats(universe_f5, estimation_returns)
    stats = stats.dropna(subset=["return_annual_hist", "volatility_annual_hist", "sharpe_hist"])
    stats["r_cap"] = _rank_pct_asc(stats["market_cap"].fillna(0.0))
    stats["r_low_vol"] = _rank_pct_desc(stats["volatility_annual_hist"])
    stats["r_return"] = _rank_pct_asc(stats["return_annual_hist"])
    stats["r_sharpe"] = _rank_pct_asc(stats["sharpe_hist"])
    stats["bonus_div"] = stats["has_dividends"].astype(float)
    stats["bonus_defensive"] = stats["sector"].isin(["Utilities", "Consumer Defensive", "Healthcare"]).astype(float)

    pieces: List[pd.DataFrame] = []
    for profile in PROFILE_ORDER:
        cfg = PROFILE_CONFIGS[profile]
        df = stats.copy()
        if profile == "Muy conservador":
            df = df[df["volatility_annual_hist"] <= df["volatility_annual_hist"].quantile(0.55)]
            df["score"] = (
                0.30 * df["r_cap"]
                + 0.35 * df["r_low_vol"]
                + 0.20 * df["bonus_div"]
                + 0.15 * df["bonus_defensive"]
            )
        elif profile == "Conservador":
            df = df[df["volatility_annual_hist"] <= df["volatility_annual_hist"].quantile(0.70)]
            df["score"] = (
                0.35 * df["r_cap"]
                + 0.35 * df["r_low_vol"]
                + 0.20 * df["r_sharpe"]
                + 0.10 * df["bonus_div"]
            )
        elif profile == "Neutro":
            df["score"] = (
                0.35 * df["r_cap"]
                + 0.35 * df["r_sharpe"]
                + 0.15 * df["r_return"]
                + 0.15 * df["r_low_vol"]
            )
        elif profile == "Arriesgado":
            df["score"] = (
                0.30 * df["r_cap"]
                + 0.35 * df["r_return"]
                + 0.25 * df["r_sharpe"]
                + 0.10 * df["r_low_vol"]
            )
        else:
            df["score"] = (
                0.25 * df["r_cap"]
                + 0.45 * df["r_return"]
                + 0.25 * df["r_sharpe"]
                + 0.05 * df["r_low_vol"]
            )
        pieces.append(_tag_profile(_select_with_sector_limit(df, cfg.n_assets, cfg.max_sector_fraction), profile))

    sub = pd.concat(pieces, ignore_index=True)
    return sub[
        [
            "profile",
            "ticker",
            "sector",
            "industry",
            "market_cap",
            "current_price",
            "cagr",
            "ann_volatility",
            "return_annual_hist",
            "volatility_annual_hist",
            "sharpe_hist",
            "has_dividends",
            "short_name",
        ]
    ]


def _tag_profile(df: pd.DataFrame, profile: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "profile", profile)
    return out


def _select_sector_representative(universe: pd.DataFrame, target_size: int) -> pd.DataFrame:
    """Seleccion sectorial proporcional con prioridad por market cap."""
    sector_counts = universe["sector"].value_counts()
    quotas = (sector_counts / sector_counts.sum() * target_size).round().astype(int).clip(lower=1)
    selected = []
    for sector, quota in quotas.items():
        selected.append(
            universe[universe["sector"] == sector]
            .sort_values("market_cap", ascending=False)
            .head(int(quota))
        )
    out = pd.concat(selected).drop_duplicates("ticker")
    if len(out) < target_size:
        extra = universe[~universe["ticker"].isin(out["ticker"])].sort_values("market_cap", ascending=False)
        out = pd.concat([out, extra.head(target_size - len(out))])
    return out.head(target_size)


def _clean_returns_for_tickers(returns: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    cols = [t for t in tickers if t in returns.columns]
    data = returns[cols].dropna(axis=0, how="any")
    if len(data) < 252:
        data = returns[cols].dropna(axis=1, thresh=252).dropna(axis=0, how="any")
    return data


def portfolio_metrics(weights: np.ndarray, returns: pd.DataFrame) -> Dict[str, float]:
    """Calcula retorno anual, volatilidad anual y Sharpe sin tasa libre."""
    mu_weekly, cov_weekly = estimate_weekly_parameters(returns)
    expected_return = float(weights @ mu_weekly.to_numpy(dtype=float) * WEEKS_PER_YEAR)
    variance_weekly = float(weights @ cov_weekly.to_numpy(dtype=float) @ weights)
    volatility = float(np.sqrt(max(variance_weekly, 0.0)) * np.sqrt(WEEKS_PER_YEAR))
    sharpe = expected_return / volatility if volatility > 1e-12 else np.nan
    return {
        "annual_return": expected_return,
        "annual_volatility": volatility,
        "sharpe": float(sharpe),
    }


def optimize_markowitz(
    returns: pd.DataFrame,
    profile_config: ProfileConfig,
) -> Tuple[pd.Series, Dict[str, float]]:
    """Optimiza media-varianza: max mu'w - 0.5 * gamma * w'Sigma w."""
    returns = returns.dropna(axis=0, how="any")
    n_assets = len(returns.columns)
    if n_assets == 0:
        raise ValueError("No hay activos con retornos suficientes para optimizar.")

    mu_weekly, cov_weekly = estimate_weekly_parameters(returns)
    mu_vec = mu_weekly.to_numpy(dtype=float)
    cov_mat = cov_weekly.to_numpy(dtype=float)

    def objective(w: np.ndarray) -> float:
        return -float(w @ mu_vec - 0.5 * profile_config.gamma * (w @ cov_mat @ w))

    w0 = np.ones(n_assets) / n_assets
    upper = min(profile_config.max_weight, 1.0)
    bounds = [(0.0, upper)] * n_assets
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    result = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 1000, "disp": False},
    )

    weights = result.x if result.success else w0
    weights = np.clip(weights, 0.0, upper)
    weights = weights / weights.sum()
    metrics = portfolio_metrics(weights, returns)
    metrics["optimizer_success"] = bool(result.success)
    metrics["optimizer_message"] = str(result.message)
    return pd.Series(weights, index=returns.columns, name="weight"), metrics


def equal_weight_metrics(returns: pd.DataFrame) -> Tuple[pd.Series, Dict[str, float]]:
    n_assets = len(returns.columns)
    weights = pd.Series(np.ones(n_assets) / n_assets, index=returns.columns, name="weight")
    return weights, portfolio_metrics(weights.to_numpy(dtype=float), returns)


def benchmark_top20_equal_weight(
    universe_f5: pd.DataFrame,
    returns_data: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Benchmark equiponderado con top 20 market cap del F5."""
    tickers = universe_f5.sort_values("market_cap", ascending=False).head(20)["ticker"].tolist()
    returns = _clean_returns_for_tickers(returns_data, tickers)
    tickers = list(returns.columns)
    weights, metrics = equal_weight_metrics(returns)
    bench = pd.DataFrame({"ticker": tickers, "benchmark_weight": weights.values})
    bench = bench.merge(
        universe_f5[["ticker", "sector", "market_cap", "short_name"]],
        on="ticker",
        how="left",
    )
    metrics["n_assets"] = len(tickers)
    return bench, metrics


def run_profiles(
    universe_f5: pd.DataFrame,
    estimation_returns: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Optimiza Markowitz por perfil y compara contra benchmark top 20 equiponderado."""
    sub = build_profile_subuniverses(universe_f5, estimation_returns)
    _, benchmark_metrics = benchmark_top20_equal_weight(universe_f5, estimation_returns)
    summary_records = []
    weights_records = []

    for profile in PROFILE_ORDER:
        cfg = PROFILE_CONFIGS[profile]
        profile_assets = sub[sub["profile"] == profile].copy()
        returns = _clean_returns_for_tickers(estimation_returns, profile_assets["ticker"].tolist())
        profile_assets = profile_assets[profile_assets["ticker"].isin(returns.columns)]
        weights, metrics = optimize_markowitz(returns, profile_config=cfg)
        eq_weights, _ = equal_weight_metrics(returns)

        weights_df = pd.DataFrame({"ticker": weights.index, "weight": weights.values})
        weights_df = weights_df.merge(
            profile_assets[["ticker", "sector", "market_cap", "short_name"]],
            on="ticker",
            how="left",
        )
        weights_df.insert(0, "profile", profile)
        weights_df["equal_weight"] = weights_df["ticker"].map(eq_weights)
        weights_records.append(weights_df)

        sector_conc = (
            weights_df.groupby("sector")["weight"]
            .sum()
            .sort_values(ascending=False)
            .round(6)
            .to_dict()
        )
        top_tickers = (
            weights_df.sort_values("weight", ascending=False)
            .head(DEFAULT_TOP_TICKERS)
            .assign(weight=lambda x: x["weight"].round(6))
            [["ticker", "weight"]]
            .to_dict("records")
        )
        sorted_weights = weights_df["weight"].sort_values(ascending=False).to_numpy()
        summary_records.append(
            {
                "profile": profile,
                "subuniverse_size": int(len(profile_assets)),
                "gamma": cfg.gamma,
                "max_weight": cfg.max_weight,
                "loss_tolerance": cfg.loss_tolerance,
                "annual_return_markowitz": metrics["annual_return"],
                "annual_volatility_markowitz": metrics["annual_volatility"],
                "sharpe_markowitz": metrics["sharpe"],
                "annual_return_equal_weight": benchmark_metrics["annual_return"],
                "annual_volatility_equal_weight": benchmark_metrics["annual_volatility"],
                "sharpe_equal_weight": benchmark_metrics["sharpe"],
                "delta_sharpe": metrics["sharpe"] - benchmark_metrics["sharpe"],
                "benchmark_n_assets": benchmark_metrics["n_assets"],
                "top5_weight": float(sorted_weights[:5].sum()),
                "top10_weight": float(sorted_weights[:10].sum()),
                "hhi": float(np.square(weights_df["weight"]).sum()),
                "sector_concentration": sector_conc,
                "top_tickers": top_tickers,
                "optimizer_success": metrics["optimizer_success"],
                "optimizer_message": metrics["optimizer_message"],
            }
        )

    summary = pd.DataFrame(summary_records)
    weights_all = pd.concat(weights_records, ignore_index=True)
    return sub, summary, weights_all


def save_final_outputs(
    subuniverses: pd.DataFrame,
    summary: pd.DataFrame,
    weights: pd.DataFrame,
    benchmark: pd.DataFrame,
    paths: Optional[Paths] = None,
) -> Dict[str, Path]:
    paths = paths or resolve_paths()
    outputs = {
        "subuniverses": paths.outputs_dir / "subuniverses_by_profile.csv",
        "summary": paths.outputs_dir / "markowitz_profiles_summary.csv",
        "weights": paths.outputs_dir / "markowitz_profile_weights.csv",
        "benchmark": paths.outputs_dir / "benchmark_top20_equal_weight.csv",
    }
    subuniverses.to_csv(outputs["subuniverses"], index=False)
    summary.to_csv(outputs["summary"], index=False)
    weights.to_csv(outputs["weights"], index=False)
    benchmark.to_csv(outputs["benchmark"], index=False)

    final_table = summary[
        [
            "profile",
            "subuniverse_size",
            "gamma",
            "max_weight",
            "annual_return_markowitz",
            "annual_volatility_markowitz",
            "sharpe_markowitz",
            "annual_return_equal_weight",
            "annual_volatility_equal_weight",
            "sharpe_equal_weight",
            "delta_sharpe",
            "top5_weight",
            "top10_weight",
            "hhi",
        ]
    ].copy()
    final_table.to_csv(paths.outputs_dir / "tabla_final_markowitz_vs_equiponderado.csv", index=False)

    sector_concentration = (
        weights.groupby(["profile", "sector"], as_index=False)["weight"]
        .sum()
        .sort_values(["profile", "weight"], ascending=[True, False])
    )
    sector_concentration.to_csv(paths.outputs_dir / "concentracion_sectorial_por_perfil.csv", index=False)

    top_tickers = (
        weights.sort_values(["profile", "weight"], ascending=[True, False])
        .groupby("profile")
        .head(DEFAULT_TOP_TICKERS)
    )
    top_tickers.to_csv(paths.outputs_dir / "top_tickers_por_perfil.csv", index=False)
    return outputs


def run_all(paths: Optional[Paths] = None) -> Dict[str, object]:
    """Ejecuta el pipeline completo y guarda todas las salidas."""
    paths = paths or resolve_paths()
    universe_f5, daily_returns, weekly_returns = build_dataset(paths)
    base_outputs = save_prepared_outputs(universe_f5, daily_returns, weekly_returns, paths)
    estimation_returns = prepare_estimation_window(weekly_returns)
    sub, summary, weights = run_profiles(universe_f5, estimation_returns)
    benchmark, benchmark_metrics = benchmark_top20_equal_weight(universe_f5, estimation_returns)
    final_outputs = save_final_outputs(sub, summary, weights, benchmark, paths)
    return {
        "universe_f5": universe_f5,
        "daily_returns": daily_returns,
        "weekly_returns": weekly_returns,
        "estimation_returns": estimation_returns,
        "subuniverses": sub,
        "summary": summary,
        "weights": weights,
        "benchmark": benchmark,
        "benchmark_metrics": benchmark_metrics,
        "outputs": {**base_outputs, **final_outputs},
    }


if __name__ == "__main__":
    result = run_all()
    print("Universo F5:", len(result["universe_f5"]))
    print(result["summary"][["profile", "subuniverse_size", "sharpe_markowitz", "sharpe_equal_weight", "delta_sharpe"]])
