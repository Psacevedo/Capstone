"""
portfolio.py - Endpoints academicos del sistema recomendador FinPUC.
"""
import json
import logging
import sqlite3
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from solver.fallback import ScipyPortfolioSolver
from solver.validators import PortfolioValidator

from ..db import get_db
from ..services.markowitz import (
    compute_cvar,
    compute_efficient_frontier,
    compute_markowitz_portfolio,
    maximum_return_portfolio,
    minimum_variance_portfolio,
)
from ..services.methodology_catalog import (
    get_base_parameters,
    get_catalog,
    get_methodology,
)
from ..services.universe_f5 import (
    F5_MIN_HISTORY_ROWS,
    F5_MIN_MARKET_CAP,
    F5_MIN_PRICE,
    f5_base_clauses,
    f5_base_where_sql,
)
from ..services.scenarios import project_scenarios, project_scenarios_timeseries
from ..services.simulation import simulate_client_behavior

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_CACHE_5M = "public, max-age=300"
TARGET_HOLDINGS_DEFAULT = 10
TARGET_HOLDINGS_MAX = 30
MIN_OPTIMIZER_UNIVERSE = 20
MAX_OPTIMIZER_UNIVERSE = 40
DEFAULT_RISK_FREE_RATE = 0.05
DEFAULT_COMMISSION_RATE = 0.01
# Decisión de grupo (profesor): rebalanceo mensual por defecto, ajustable en UI.
DEFAULT_REBALANCE_FREQ_WEEKS = 4
PARAMETER_GROUP_ORDER = [
    "Perfil y universo",
    "Estimacion",
    "Riesgo y escenarios",
    "Cliente y negocio",
]
BL_Z_10_90 = 1.2815515655446004


def _fit_distributions_pct(values_pct: np.ndarray) -> Dict:
    """
    Ajusta distribuciones candidatas sobre retornos en %.
    Se usa para *describir* colas/asimetria, no para afirmar iid/estacionariedad.
    """
    values_pct = np.array(values_pct, dtype=float)
    values_pct = values_pct[np.isfinite(values_pct)]
    n_obs = int(values_pct.size)
    if n_obs < 50:
        return {"best_by_bic": None, "candidates": [], "notes": "No hay suficientes datos para ajustar distribuciones (n<50)."}

    try:
        from scipy import stats  # type: ignore
    except Exception:  # pragma: no cover
        return {"best_by_bic": None, "candidates": [], "notes": "SciPy no disponible para ajuste de distribuciones."}

    def _aic_bic(loglik: float, k_params: int) -> Tuple[float, float]:
        aic = 2 * k_params - 2 * loglik
        bic = k_params * float(np.log(n_obs)) - 2 * loglik
        return float(aic), float(bic)

    candidates: List[Dict] = []

    mu = float(values_pct.mean())
    sigma = float(values_pct.std(ddof=1)) if n_obs > 1 else 0.0
    if sigma > 0:
        ll = float(np.sum(stats.norm.logpdf(values_pct, loc=mu, scale=sigma)))
        aic, bic = _aic_bic(ll, 2)
        candidates.append(
            {
                "name": "normal",
                "params": {"mu_pct": round(mu, 6), "sigma_pct": round(sigma, 6)},
                "loglik": round(ll, 3),
                "aic": round(aic, 3),
                "bic": round(bic, 3),
            }
        )

    try:
        df, loc, scale = stats.t.fit(values_pct)
        if float(scale) > 0 and float(df) > 0:
            ll = float(np.sum(stats.t.logpdf(values_pct, df, loc=loc, scale=scale)))
            aic, bic = _aic_bic(ll, 3)
            candidates.append(
                {
                    "name": "student_t",
                    "params": {"df": round(float(df), 6), "loc_pct": round(float(loc), 6), "scale_pct": round(float(scale), 6)},
                    "loglik": round(ll, 3),
                    "aic": round(aic, 3),
                    "bic": round(bic, 3),
                }
            )
    except Exception:
        pass

    try:
        a, b, loc, scale = stats.johnsonsu.fit(values_pct)
        if float(scale) > 0:
            ll = float(np.sum(stats.johnsonsu.logpdf(values_pct, a, b, loc=loc, scale=scale)))
            aic, bic = _aic_bic(ll, 4)
            candidates.append(
                {
                    "name": "johnsonsu",
                    "params": {
                        "a": round(float(a), 6),
                        "b": round(float(b), 6),
                        "loc_pct": round(float(loc), 6),
                        "scale_pct": round(float(scale), 6),
                    },
                    "loglik": round(ll, 3),
                    "aic": round(aic, 3),
                    "bic": round(bic, 3),
                }
            )
    except Exception:
        pass

    candidates.sort(key=lambda item: item.get("bic", float("inf")))
    best = candidates[0]["name"] if candidates else None

    implied_df = None
    try:
        k_excess = float(stats.kurtosis(values_pct, fisher=True))
        if k_excess > 0:
            implied_df = 4.0 + 6.0 / k_excess
    except Exception:
        implied_df = None

    notes = (
        "Guia rapida: kurtosis_excess alta => colas pesadas (Student-t). "
        "Skew != 0 => asimetria (Johnson SU / skew-t)."
    )
    if implied_df is not None and np.isfinite(implied_df):
        notes += f" df(t) aproximado por kurtosis: {round(float(implied_df), 3)}."

    return {"best_by_bic": best, "candidates": candidates, "notes": notes}


RISK_PROFILES = {
    "muy_conservador": {
        "alpha_p": 0.00,
        "label": "Muy conservador",
        "description": "No admite perdidas sobre el capital invertido.",
        "candidate_pool_default": 40,
        "candidate_pool_range": "30-50",
        "candidate_pool_max": 50,
        "max_vol": 0.30,
        "sectors": ["Utilities", "Consumer Defensive"],
        "cvar_level": 0.99,
        "dividend_bias": True,
    },
    "conservador": {
        "alpha_p": 0.05,
        "label": "Conservador",
        "description": "Tolera perdidas minimas y privilegia estabilidad.",
        "candidate_pool_default": 65,
        "candidate_pool_range": "50-80",
        "candidate_pool_max": 80,
        "max_vol": 0.35,
        "sectors": None,
        "cvar_level": 0.95,
        "dividend_bias": True,
    },
    "neutro": {
        "alpha_p": 0.15,
        "label": "Neutro",
        "description": "Equilibra retorno esperado y riesgo.",
        "candidate_pool_default": 100,
        "candidate_pool_range": "80-120",
        "candidate_pool_max": 120,
        "max_vol": None,
        "sectors": None,
        "cvar_level": 0.90,
        "dividend_bias": False,
    },
    "arriesgado": {
        "alpha_p": 0.30,
        "label": "Arriesgado",
        "description": "Acepta mas volatilidad para capturar crecimiento.",
        "candidate_pool_default": 125,
        "candidate_pool_range": "100-150",
        "candidate_pool_max": 150,
        "max_vol": None,
        "sectors": None,
        "cvar_level": 0.85,
        "dividend_bias": False,
    },
    "muy_arriesgado": {
        "alpha_p": 0.40,
        "label": "Muy arriesgado",
        "description": "Opera sobre el universo F5 completo.",
        "candidate_pool_default": None,
        "candidate_pool_range": "Universo F5 completo",
        "candidate_pool_max": None,
        "max_vol": None,
        "sectors": None,
        "cvar_level": 0.80,
        "dividend_bias": False,
    },
}


LEGACY_METHOD_MAP = {
    "markowitz": "markowitz_media_varianza",
    "simple": "maximo_retorno",
    "propio": "minima_varianza_global",
    "benchmark": "benchmark",
    # Backward compat: IDs eliminados en entrega 2 caen a Markowitz
    "finpuc_hibrido": "markowitz_media_varianza",
    "capm_markowitz": "markowitz_media_varianza",
    "fama_french_markowitz": "markowitz_media_varianza",
}


class OptimizeRequest(BaseModel):
    initial_capital: float = Field(gt=0, description="Capital inicial en USD")
    methodology_id: str = Field(
        default="markowitz_media_varianza",
        description="Identificador de la metodologia academica seleccionada.",
    )
    profile: Optional[str] = Field(
        default=None,
        description="muy_conservador|conservador|neutro|arriesgado|muy_arriesgado",
    )
    max_loss_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    target_holdings: Optional[int] = Field(default=None, ge=3, le=TARGET_HOLDINGS_MAX)
    candidate_pool_size: Optional[int] = Field(default=None, ge=10, le=636)
    sector: Optional[str] = Field(default=None)
    parameter_values: Dict[str, object] = Field(default_factory=dict)

    # Compatibilidad con la version previa
    strategy: Optional[str] = Field(default=None)
    n_stocks: Optional[int] = Field(default=None, ge=3, le=TARGET_HOLDINGS_MAX)
    method: Optional[str] = Field(default=None)


class SimulateRequest(BaseModel):
    initial_capital: float = Field(gt=0)
    max_loss_pct: float = Field(ge=0.01, le=1.0)
    expected_return: float = Field(description="Retorno anual esperado en decimal")
    volatility: float = Field(ge=0, description="Volatilidad anual en decimal")
    years: int = Field(default=3, ge=3, le=5)
    n_simulations: int = Field(default=500, ge=100, le=2000)
    commission_rate_pct: float = Field(default=1.0, ge=0, le=10)
    p2_acceptance_prob_pct: float = Field(default=70.0, ge=0, le=100)
    rebalance_freq_weeks: int = Field(default=DEFAULT_REBALANCE_FREQ_WEEKS, ge=1, le=52)
    rebalance_return_boost_pct: float = Field(default=0.1, ge=0, le=5)


def _risk_level(max_loss_pct: float) -> str:
    if max_loss_pct <= 0.00:
        return "muy_conservador"
    if max_loss_pct <= 0.05:
        return "conservador"
    if max_loss_pct <= 0.15:
        return "neutro"
    if max_loss_pct <= 0.30:
        return "arriesgado"
    return "muy_arriesgado"


def _resolve_methodology_id(req: OptimizeRequest) -> str:
    if req.strategy == "benchmark" or req.method == "benchmark":
        return "benchmark"
    if req.method in LEGACY_METHOD_MAP:
        return LEGACY_METHOD_MAP[req.method]
    return req.methodology_id or "markowitz_media_varianza"


def _resolve_target_holdings(req: OptimizeRequest) -> int:
    value = req.target_holdings or req.n_stocks or TARGET_HOLDINGS_DEFAULT
    return max(3, min(int(value), TARGET_HOLDINGS_MAX))


def _resolve_profile(req: OptimizeRequest) -> Tuple[str, Dict, float]:
    if req.profile and req.profile in RISK_PROFILES:
        profile_key = req.profile
        profile_cfg = RISK_PROFILES[profile_key]
        return profile_key, profile_cfg, profile_cfg["alpha_p"]

    max_loss_pct = req.max_loss_pct if req.max_loss_pct is not None else 0.15
    profile_key = _risk_level(max_loss_pct)
    profile_cfg = RISK_PROFILES[profile_key]
    return profile_key, profile_cfg, profile_cfg["alpha_p"]


def _resolve_candidate_pool_size(profile_cfg: Dict, requested: Optional[int], f5_total_size: int) -> int:
    if requested is not None:
        if profile_cfg["candidate_pool_max"] is not None:
            return max(10, min(int(requested), profile_cfg["candidate_pool_max"]))
        return max(10, min(int(requested), f5_total_size))

    if profile_cfg["candidate_pool_default"] is not None:
        return min(profile_cfg["candidate_pool_default"], f5_total_size)
    return f5_total_size


def _optimizer_universe_size(candidate_pool_size: int, target_holdings: int) -> int:
    return min(
        candidate_pool_size,
        max(MIN_OPTIMIZER_UNIVERSE, target_holdings * 4),
        MAX_OPTIMIZER_UNIVERSE,
    )


def _get_split_dates() -> Dict[str, str]:
    today = date.today()
    validation_end = today
    validation_start = today.replace(year=today.year - 2)
    calibration_end = validation_start - timedelta(days=1)
    calibration_start = calibration_end.replace(year=calibration_end.year - 8)
    return {
        "calibration_start": calibration_start.isoformat(),
        "calibration_end": calibration_end.isoformat(),
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
    }


def _fetch_price_series(
    db: sqlite3.Connection,
    tickers: Sequence[str],
    start: str,
    end: str,
) -> Dict[str, List[Tuple[str, float]]]:
    if not tickers:
        return {}

    placeholders = ",".join("?" * len(tickers))
    rows = db.execute(
        f"""
        SELECT ticker, date, close
        FROM prices
        WHERE ticker IN ({placeholders})
          AND date >= ? AND date <= ?
          AND close IS NOT NULL
        ORDER BY ticker, date ASC
        """,
        list(tickers) + [start, end],
    ).fetchall()

    series: Dict[str, List[Tuple[str, float]]] = {}
    for row in rows:
        series.setdefault(row["ticker"], []).append((row["date"], float(row["close"])))
    return series


def _closes_from_series(series_map: Dict[str, List[Tuple[str, float]]]) -> Dict[str, List[float]]:
    return {ticker: [close for _, close in rows] for ticker, rows in series_map.items()}


def _daily_returns(closes: List[float]) -> np.ndarray:
    prices = np.array(closes, dtype=float)
    return np.diff(prices) / prices[:-1]


def _align_return_matrix(
    series_map: Dict[str, List[Tuple[str, float]]],
    tickers: Sequence[str],
) -> Tuple[List[str], np.ndarray]:
    valid_tickers = [ticker for ticker in tickers if len(series_map.get(ticker, [])) >= 252]
    if len(valid_tickers) < 3:
        raise HTTPException(status_code=400, detail="No hay suficientes tickers con historia util en calibracion.")

    min_len = min(len(series_map[ticker]) for ticker in valid_tickers)
    matrix = np.column_stack(
        [
            _daily_returns([close for _, close in series_map[ticker][-min_len:]])
            for ticker in valid_tickers
        ]
    )
    return valid_tickers, matrix


def _portfolio_metrics(
    weights: np.ndarray,
    returns_matrix: np.ndarray,
    ann_returns_override: np.ndarray,
    risk_free_rate: float,
) -> Dict[str, float]:
    ann_cov = np.cov(returns_matrix.T) * 252 if returns_matrix.shape[1] > 1 else np.array([[returns_matrix.var() * 252]])
    ann_cov += np.eye(len(weights)) * 1e-8
    expected_return = float(np.dot(weights, ann_returns_override))
    volatility = float(np.sqrt(weights @ ann_cov @ weights))
    sharpe = (expected_return - risk_free_rate) / volatility if volatility > 1e-10 else 0.0
    return {
        "expected_return_pct": round(expected_return * 100, 2),
        "volatility_pct": round(volatility * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
    }


def _trim_portfolio(
    tickers: List[str],
    weights: Sequence[float],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    target_holdings: int,
    renormalize: bool = True,
) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    weights_arr = np.array(weights, dtype=float)
    ranked = np.argsort(weights_arr)[::-1]
    selected = [idx for idx in ranked if weights_arr[idx] > 0][:target_holdings]
    if not selected:
        selected = list(ranked[:target_holdings])

    trimmed_weights = weights_arr[selected]
    if renormalize and trimmed_weights.sum() > 0:
        trimmed_weights = trimmed_weights / trimmed_weights.sum()

    trimmed_tickers = [tickers[idx] for idx in selected]
    trimmed_returns = returns_matrix[:, selected]
    trimmed_ann_returns = ann_returns[selected]
    return trimmed_tickers, trimmed_weights, trimmed_returns, trimmed_ann_returns


def _candidate_query(profile_cfg: Dict, sector_filter: Optional[str]) -> Tuple[str, List, str]:
    clauses, params = f5_base_clauses()

    if profile_cfg["max_vol"] is not None:
        clauses.append("ann_volatility <= ?")
        params.append(profile_cfg["max_vol"])

    if sector_filter:
        clauses.append("sector = ?")
        params.append(sector_filter)
    elif profile_cfg["sectors"]:
        placeholders = ",".join("?" * len(profile_cfg["sectors"]))
        clauses.append(f"sector IN ({placeholders})")
        params.extend(profile_cfg["sectors"])

    if profile_cfg["dividend_bias"]:
        order_sql = "COALESCE(dividend_yield, 0) DESC, ann_volatility ASC, cagr DESC"
    else:
        order_sql = "cagr DESC, ann_volatility ASC"

    return " AND ".join(clauses), params, order_sql


def _select_candidates(
    db: sqlite3.Connection,
    profile_cfg: Dict,
    candidate_pool_size: int,
    sector_filter: Optional[str],
) -> Tuple[List[Dict], int]:
    where_sql, params, order_sql = _candidate_query(profile_cfg, sector_filter)
    total_count = db.execute(
        f"SELECT COUNT(*) AS total FROM stocks WHERE {where_sql}",
        params,
    ).fetchone()["total"]

    rows = db.execute(
        f"""
        SELECT
            ticker,
            short_name,
            sector,
            industry,
            cagr,
            ann_volatility,
            market_cap,
            current_price,
            dividend_yield,
            trailing_pe,
            beta,
            n_rows
        FROM stocks
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ?
        """,
        params + [candidate_pool_size],
    ).fetchall()
    return [dict(row) for row in rows], int(total_count)


def _build_benchmark_portfolio(candidates: List[Dict], target_holdings: int) -> Tuple[List[str], np.ndarray]:
    selected = candidates[:target_holdings]
    if not selected:
        return [], np.array([])
    weights = np.ones(len(selected), dtype=float) / len(selected)
    return [item["ticker"] for item in selected], weights


def _coerce_query_default(value):
    return value.default if hasattr(value, "default") else value


def _format_parameter_value(value, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit.startswith("%"):
            return f"{round(value, 4)} {unit}".strip()
        return str(round(value, 6))
    return str(value)


def _normalize_numeric(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _normalize_parameter_values(methodology: Dict, incoming: Dict[str, object]) -> Dict[str, object]:
    normalized: Dict[str, object] = {}
    for definition in methodology["parameters"]:
        key = definition["key"]
        raw_value = incoming.get(key, definition.get("default"))
        if definition["input_type"] in {"text", "textarea"}:
            normalized[key] = raw_value if raw_value is not None else definition.get("default")
        else:
            normalized[key] = _normalize_numeric(raw_value, definition.get("default"))
    return normalized


def _ensure_required_inputs(methodology: Dict, parameter_values: Dict[str, object]) -> None:
    missing = []
    for definition in methodology["parameters"]:
        if not definition["required"]:
            continue
        value = parameter_values.get(definition["key"])
        if definition["input_type"] in {"text", "textarea"}:
            if value is None or str(value).strip() == "":
                missing.append(definition["label"])
        elif value is None:
            missing.append(definition["label"])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan parametros requeridos para la metodologia: {', '.join(missing)}.",
        )


def _historical_ann_returns(tickers: Sequence[str], metadata: Dict[str, Dict], returns_matrix: np.ndarray) -> np.ndarray:
    annualized_mean = returns_matrix.mean(axis=0) * 252
    values = []
    for idx, ticker in enumerate(tickers):
        cagr = metadata.get(ticker, {}).get("cagr")
        values.append(float(cagr) if cagr is not None else float(annualized_mean[idx]))
    return np.array(values, dtype=float)


def _zscore(values: np.ndarray) -> np.ndarray:
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std < 1e-12:
        return np.zeros_like(values)
    return (values - mean) / std


def _size_loadings(tickers: Sequence[str], metadata: Dict[str, Dict]) -> np.ndarray:
    market_caps = np.array(
        [max(float(metadata.get(ticker, {}).get("market_cap") or 1.0), 1.0) for ticker in tickers],
        dtype=float,
    )
    return _zscore(-np.log(market_caps))


def _value_loadings(tickers: Sequence[str], metadata: Dict[str, Dict]) -> np.ndarray:
    dividend_yields = []
    earnings_yields = []
    for ticker in tickers:
        meta = metadata.get(ticker, {})
        dividend_yields.append(float(meta.get("dividend_yield") or 0.0))
        trailing_pe = float(meta.get("trailing_pe") or 0.0)
        earnings_yields.append(0.0 if trailing_pe <= 0 else 1.0 / trailing_pe)
    dividend_score = _zscore(np.array(dividend_yields, dtype=float))
    earnings_score = _zscore(np.array(earnings_yields, dtype=float))
    return (dividend_score + earnings_score) / 2.0


def _parse_views_json(raw_views: object, tickers: Sequence[str]) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
    if isinstance(raw_views, str):
        try:
            data = json.loads(raw_views)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Views JSON invalido: {exc.msg}.") from exc
    elif isinstance(raw_views, list):
        data = raw_views
    else:
        raise HTTPException(status_code=400, detail="Las views deben enviarse como JSON valido.")

    if not isinstance(data, list) or not data:
        raise HTTPException(status_code=400, detail="Debes ingresar al menos una view para Black-Litterman.")

    ticker_index = {ticker: idx for idx, ticker in enumerate(tickers)}
    p_rows = []
    q_values = []
    views_used = []
    for item in data:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Cada view debe ser un objeto JSON.")
        ticker = str(item.get("ticker", "")).upper().strip()
        if ticker not in ticker_index:
            raise HTTPException(status_code=400, detail=f"La view referencia un ticker fuera del universo operativo: {ticker}.")
        view_return_pct = _normalize_numeric(item.get("view_return_pct"))
        if view_return_pct is None:
            raise HTTPException(status_code=400, detail=f"La view para {ticker} no incluye view_return_pct.")

        row = np.zeros(len(tickers), dtype=float)
        row[ticker_index[ticker]] = 1.0
        p_rows.append(row)
        q_values.append(float(view_return_pct) / 100.0)
        views_used.append({"ticker": ticker, "view_return_pct": round(float(view_return_pct), 4)})

    return np.vstack(p_rows), np.array(q_values, dtype=float), views_used


def _capm_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    risk_free_rate = (_normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    market_return = (_normalize_numeric(parameter_values.get("market_return_pct"), 10.0) or 10.0) / 100.0
    market_premium = market_return - risk_free_rate

    returns = []
    beta_used = []
    for ticker in tickers:
        beta = metadata.get(ticker, {}).get("beta")
        beta = 1.0 if beta is None else float(beta)
        beta_used.append({"ticker": ticker, "beta": round(beta, 4)})
        returns.append(risk_free_rate + beta * market_premium)

    return np.array(returns, dtype=float), {
        "estimation_model": "CAPM",
        "risk_free_rate_pct": round(risk_free_rate * 100, 4),
        "market_return_pct": round(market_return * 100, 4),
        "market_premium_pct": round(market_premium * 100, 4),
        "beta_source": "Campo beta del dataset local.",
        "beta_sample": beta_used[:5],
    }


def _fama_french_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    risk_free_rate = (_normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    market_return = (_normalize_numeric(parameter_values.get("market_return_pct"), 10.0) or 10.0) / 100.0
    smb_premium = (_normalize_numeric(parameter_values.get("smb_premium_pct"), 2.0) or 2.0) / 100.0
    hml_premium = (_normalize_numeric(parameter_values.get("hml_premium_pct"), 1.5) or 1.5) / 100.0
    market_premium = market_return - risk_free_rate

    size_load = _size_loadings(tickers, metadata)
    value_load = _value_loadings(tickers, metadata)
    returns = []
    for idx, ticker in enumerate(tickers):
        beta = metadata.get(ticker, {}).get("beta")
        beta = 1.0 if beta is None else float(beta)
        returns.append(
            risk_free_rate
            + beta * market_premium
            + size_load[idx] * smb_premium
            + value_load[idx] * hml_premium
        )

    return np.array(returns, dtype=float), {
        "estimation_model": "Fama-French aproximado",
        "risk_free_rate_pct": round(risk_free_rate * 100, 4),
        "market_return_pct": round(market_return * 100, 4),
        "smb_premium_pct": round(smb_premium * 100, 4),
        "hml_premium_pct": round(hml_premium * 100, 4),
        "loading_note": (
            "Las cargas SMB y HML se aproximan con z-scores de capitalizacion de mercado, "
            "dividend yield y trailing PE del dataset local."
        ),
    }


def _black_litterman_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    risk_free_rate = (_normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    lambda_risk = _normalize_numeric(parameter_values.get("lambda_risk_aversion"), 2.5) or 2.5
    tau = _normalize_numeric(parameter_values.get("tau"), 0.05) or 0.05
    omega_diag = _normalize_numeric(parameter_values.get("omega_diag"), 0.05) or 0.05

    if tau <= 0 or omega_diag <= 0:
        raise HTTPException(status_code=400, detail="Tau y Omega deben ser positivos para Black-Litterman.")

    ann_cov = np.cov(returns_matrix.T) * 252 if returns_matrix.shape[1] > 1 else np.array([[returns_matrix.var() * 252]])
    ann_cov += np.eye(len(tickers)) * 1e-8

    market_caps = np.array(
        [max(float(metadata.get(ticker, {}).get("market_cap") or 1.0), 1.0) for ticker in tickers],
        dtype=float,
    )
    market_weights = market_caps / market_caps.sum()
    prior = np.full(len(tickers), risk_free_rate, dtype=float) + lambda_risk * (ann_cov @ market_weights)

    p_matrix, q_vector, views_used = _parse_views_json(parameter_values.get("views_json"), tickers)
    omega = np.eye(len(q_vector), dtype=float) * omega_diag

    tau_sigma = tau * ann_cov
    tau_sigma_inv = np.linalg.pinv(tau_sigma)
    omega_inv = np.linalg.pinv(omega)
    posterior_matrix = np.linalg.pinv(tau_sigma_inv + p_matrix.T @ omega_inv @ p_matrix)
    posterior_vector = tau_sigma_inv @ prior + p_matrix.T @ omega_inv @ q_vector
    mu_bl = posterior_matrix @ posterior_vector

    return np.array(mu_bl, dtype=float), {
        "estimation_model": "Black-Litterman",
        "risk_free_rate_pct": round(risk_free_rate * 100, 4),
        "lambda_risk_aversion": round(lambda_risk, 6),
        "tau": round(tau, 6),
        "omega_diag": round(omega_diag, 6),
        "views_used": views_used,
        "market_weighting": "Pesos de mercado aproximados con market cap del universo operativo.",
    }


def _estimate_returns(
    methodology_id: str,
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    historical = _historical_ann_returns(tickers, metadata, returns_matrix)
    if methodology_id in {"markowitz_media_varianza", "minima_varianza_global", "maximo_retorno"}:
        return historical, {
            "estimation_model": "Historico",
            "historical_source": "CAGR local con fallback a media anualizada del periodo de calibracion.",
        }
    if methodology_id == "capm_markowitz":
        return _capm_ann_returns(tickers, metadata, parameter_values)
    if methodology_id == "fama_french_markowitz":
        return _fama_french_ann_returns(tickers, metadata, parameter_values)
    if methodology_id in {"black_litterman_markowitz", "finpuc_hibrido"}:
        return _black_litterman_ann_returns(tickers, metadata, returns_matrix, parameter_values)
    raise HTTPException(status_code=400, detail="Metodologia no soportada.")


def _build_hybrid_scenarios(
    tickers: Sequence[str],
    ann_returns: np.ndarray,
    returns_matrix: np.ndarray,
) -> Dict[str, Dict[str, float]]:
    daily_vol = np.std(returns_matrix, axis=0)
    weekly_vol = daily_vol * np.sqrt(5)
    weekly_mu = np.array([((1 + value) ** (1 / 52) - 1) if value > -0.999 else value / 52 for value in ann_returns], dtype=float)
    return {
        "desf": {
            ticker: float(weekly_mu[idx] - BL_Z_10_90 * weekly_vol[idx])
            for idx, ticker in enumerate(tickers)
        },
        "neutro": {
            ticker: float(weekly_mu[idx])
            for idx, ticker in enumerate(tickers)
        },
        "fav": {
            ticker: float(weekly_mu[idx] + BL_Z_10_90 * weekly_vol[idx])
            for idx, ticker in enumerate(tickers)
        },
    }


def _hybrid_probabilities(parameter_values: Dict[str, object]) -> Dict[str, float]:
    probs = {
        "desf": (_normalize_numeric(parameter_values.get("prob_desfavorable_pct"), 25.0) or 25.0) / 100.0,
        "neutro": (_normalize_numeric(parameter_values.get("prob_neutro_pct"), 50.0) or 50.0) / 100.0,
        "fav": (_normalize_numeric(parameter_values.get("prob_favorable_pct"), 25.0) or 25.0) / 100.0,
    }
    total = sum(probs.values())
    if total <= 0:
        raise HTTPException(status_code=400, detail="Las probabilidades de escenarios deben sumar un valor positivo.")
    return {key: value / total for key, value in probs.items()}


def _run_hybrid_solver(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    parameter_values: Dict[str, object],
    profile_key: str,
    alpha_p: float,
) -> Tuple[np.ndarray, float, Dict]:
    scenarios = _build_hybrid_scenarios(tickers, ann_returns, returns_matrix)
    probabilities = _hybrid_probabilities(parameter_values)
    commission_rate_pct = _normalize_numeric(parameter_values.get("commission_rate_pct"), 1.0) or 1.0
    commission_weekly = (commission_rate_pct / 100.0) / 52.0

    returns_mean = {
        ticker: sum(probabilities[scenario] * scenarios[scenario][ticker] for scenario in probabilities)
        for ticker in tickers
    }
    solver = ScipyPortfolioSolver(
        tickers=list(tickers),
        returns_mean=returns_mean,
        returns_scen=scenarios,
        probs=probabilities,
        alpha=alpha_p,
        max_weight=0.40,
        time_limit=9.0,
        commission_k=commission_weekly,
    )
    solution, diagnostic = solver.solve_stochastic_2stage()
    if solution is None:
        raise HTTPException(
            status_code=400,
            detail=f"La metodologia hibrida no pudo resolver el problema: {diagnostic.message}",
        )

    validator = PortfolioValidator.from_scipy_solution(
        solution,
        list(tickers),
        returns_scenario=scenarios["desf"],
        profile=profile_key,
        commission_rate=commission_weekly,
        max_weight_single=0.40,
    ).validate()

    weights = np.array(solution[:-1], dtype=float)
    cash_weight = float(solution[-1])
    solver_details = {
        "solver_used": "solver.fallback.ScipyPortfolioSolver",
        "status": diagnostic.status.value,
        "message": diagnostic.message,
        "solve_time_s": diagnostic.solve_time,
        "obj_value": diagnostic.obj_value,
        "validation": validator.to_dict(),
        "scenario_probabilities": {
            "desfavorable_pct": round(probabilities["desf"] * 100, 2),
            "neutro_pct": round(probabilities["neutro"] * 100, 2),
            "favorable_pct": round(probabilities["fav"] * 100, 2),
        },
        "scenario_construction": "Escenarios por activo construidos desde mu_BL y volatilidad semanal p10/p50/p90.",
    }
    return weights, cash_weight, solver_details


def _portfolio_rows(
    tickers: Sequence[str],
    weights: Sequence[float],
    metadata: Dict[str, Dict],
) -> List[Dict]:
    rows: List[Dict] = []
    for ticker, weight in zip(tickers, weights):
        meta = metadata.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "short_name": meta.get("short_name", ticker),
                "sector": meta.get("sector"),
                "industry": meta.get("industry"),
                "weight": round(float(weight), 4),
                "cagr_pct": round(float(meta["cagr"]) * 100, 2) if meta.get("cagr") is not None else None,
                "volatility_pct": round(float(meta["ann_volatility"]) * 100, 2) if meta.get("ann_volatility") is not None else None,
                "dividend_yield_pct": round(float(meta["dividend_yield"]) * 100, 2) if meta.get("dividend_yield") is not None else None,
                "market_cap_b": round(float(meta["market_cap"]) / 1e9, 2) if meta.get("market_cap") is not None else None,
            }
        )
    return rows


def _validation_summary(
    db: sqlite3.Connection,
    tickers: Sequence[str],
    weights: np.ndarray,
    splits: Dict[str, str],
) -> Optional[Dict]:
    price_map = _closes_from_series(_fetch_price_series(db, tickers, splits["validation_start"], splits["validation_end"]))
    contributions = []
    for ticker, weight in zip(tickers, weights):
        closes = price_map.get(ticker, [])
        if len(closes) < 5:
            continue
        total_return = (closes[-1] / closes[0]) - 1
        contributions.append(float(weight) * total_return)

    if not contributions:
        return None

    portfolio_return = sum(contributions)
    return {
        "period": f"{splits['validation_start']} -> {splits['validation_end']}",
        "total_return_pct": round(portfolio_return * 100, 2),
        "annualized_return_pct": round(((1 + portfolio_return) ** 0.5 - 1) * 100, 2),
    }


def _build_universe(
    profile_cfg: Dict,
    total_f5_count: int,
    candidates: List[Dict],
    candidate_pool_size: int,
    optimizer_universe_size: int,
    target_holdings: int,
    sector_filter: Optional[str],
) -> Dict:
    return {
        "name": "Universo F5",
        "total_f5_count": total_f5_count,
        "screened_candidate_count": len(candidates),
        "candidate_pool_size": candidate_pool_size,
        "optimizer_universe_size": optimizer_universe_size,
        "target_holdings": target_holdings,
        "sector_filter": sector_filter,
        "forced_sectors": profile_cfg["sectors"],
        "max_vol_pct": round(profile_cfg["max_vol"] * 100, 2) if profile_cfg["max_vol"] is not None else None,
        "filters": {
            "min_history_years": 10,
            "min_history_rows": F5_MIN_HISTORY_ROWS,
            "min_price_usd": F5_MIN_PRICE,
            "min_market_cap_usd": F5_MIN_MARKET_CAP,
            "annual_vol_range_pct": [5, 100],
            "exclude_unknown_sector": True,
            "exclude_shell_companies": True,
        },
    }


def _build_weekly_cycle(parameter_values: Optional[Dict[str, object]] = None) -> Dict:
    params = parameter_values or {}
    commission_rate_pct = _normalize_numeric(params.get("commission_rate_pct"), 1.0) or 1.0
    p2_acceptance_prob_pct = _normalize_numeric(params.get("p2_acceptance_prob_pct"), 70.0) or 70.0
    p1_drawdown_pct = _normalize_numeric(params.get("p1_withdrawal_drawdown_pct"), 20.0) or 20.0
    cash_buffer_pct = _normalize_numeric(params.get("cash_buffer_pct"), 5.0)
    return {
        "cadence": "Semanal",
        "trigger": "Cada lunes",
        "rebalancing": "El sistema emite una recomendacion semanal y rebalancea si el cliente acepta.",
        "client_acceptance": f"Aproximacion operacional de P2 con probabilidad base {round(p2_acceptance_prob_pct, 2)}%.",
        "client_withdrawal": f"Aproximacion operacional de P1 por drawdown sobre {round(p1_drawdown_pct, 2)}%.",
        "commissions": f"Comision anual k = {round(commission_rate_pct, 2)}%.",
        "dividends": (
            "Los dividendos del dataset alimentan la logica de caja chica; "
            f"la reserva referencial reportada es {round(cash_buffer_pct, 2)}%."
            if cash_buffer_pct is not None
            else "Los dividendos del dataset alimentan la logica de caja chica."
        ),
        "time_budget_seconds": 10,
    }


def _build_parameter_groups(
    methodology: Dict,
    parameter_values: Dict[str, object],
    profile_key: str,
    profile_cfg: Dict,
    alpha_p: float,
    target_holdings: int,
    candidate_pool_size: int,
    sector: Optional[str],
) -> List[Dict]:
    groups = {name: [] for name in PARAMETER_GROUP_ORDER}
    groups["Perfil y universo"].extend(
        [
            {
                "key": "profile",
                "label": "Perfil de riesgo",
                "value": profile_key,
                "value_display": profile_cfg["label"],
                "unit": "",
                "meaning": "Perfil seleccionado para fijar el umbral alpha_p y el sub-universo.",
                "report_reference": "Tabla 2.1 / Tabla 0.10",
            },
            {
                "key": "alpha_p",
                "label": "alpha_p",
                "value": round(alpha_p * 100, 4),
                "value_display": f"{round(alpha_p * 100, 4)} %",
                "unit": "%",
                "meaning": "Tolerancia maxima de perdida del perfil de riesgo.",
                "report_reference": "Seccion 2.2.2 / Ecuacion 4.4",
            },
            {
                "key": "candidate_pool_size",
                "label": "Tamano del sub-universo",
                "value": candidate_pool_size,
                "value_display": str(candidate_pool_size),
                "unit": "acciones",
                "meaning": "Cantidad de activos candidatos antes de optimizar.",
                "report_reference": "Tabla 0.10",
            },
            {
                "key": "target_holdings",
                "label": "Holdings finales",
                "value": target_holdings,
                "value_display": str(target_holdings),
                "unit": "acciones",
                "meaning": "Numero final de posiciones del portafolio recomendado.",
                "report_reference": "Seccion 2.3.1",
            },
            {
                "key": "sector",
                "label": "Filtro sectorial",
                "value": sector or "",
                "value_display": sector or "Sin filtro manual",
                "unit": "",
                "meaning": "Restriccion opcional del universo a un sector especifico.",
                "report_reference": "Anexo 1 / Tabla 0.3",
            },
        ]
    )

    for definition in methodology["parameters"]:
        raw_value = parameter_values.get(definition["key"])
        groups[definition["group"]].append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "value": raw_value,
                "value_display": _format_parameter_value(raw_value, definition["unit"]),
                "unit": definition["unit"],
                "meaning": definition["meaning"],
                "report_reference": definition["report_reference"],
            }
        )

    return [
        {"group": group, "items": groups[group]}
        for group in PARAMETER_GROUP_ORDER
        if groups[group]
    ]


def _build_methodology_payload(
    methodology: Dict,
    methodology_id: str,
    estimation_info: Dict,
    parameters_used: List[Dict],
    solver_details: Optional[Dict],
) -> Dict:
    return {
        "id": methodology_id,
        "label": methodology["label"],
        "family": methodology["family"],
        "description": methodology["description"],
        "formula_summary": methodology["formula_summary"],
        "formula_latex": methodology.get("formula_latex"),
        "report_references": methodology["report_references"],
        "implementation_status": methodology["implementation_status"],
        "recommended": methodology["recommended"],
        "notes": methodology["notes"],
        "estimation_summary": estimation_info,
        "parameters_used": parameters_used,
        "solver_details": solver_details,
    }


def _method_label(methodology_id: str) -> str:
    if methodology_id == "benchmark":
        return "Benchmark academico top CAGR"
    if methodology_id == "base_case":
        return "Caso base top market cap"
    return get_methodology(methodology_id)["label"]


def _run_primary_optimizer(
    methodology_id: str,
    tickers: Sequence[str],
    returns_matrix: np.ndarray,
    ann_returns: np.ndarray,
    risk_free_rate: float,
) -> np.ndarray:
    if methodology_id == "minima_varianza_global":
        optimized = minimum_variance_portfolio(list(tickers), returns_matrix, risk_free_rate)
    elif methodology_id == "maximo_retorno":
        optimized = maximum_return_portfolio(
            list(tickers),
            returns_matrix,
            risk_free_rate,
            custom_ann_returns=ann_returns,
        )
    else:
        optimized = compute_markowitz_portfolio(
            list(tickers),
            returns_matrix,
            risk_free_rate,
            custom_ann_returns=ann_returns,
        )

    if not optimized or not optimized.get("weights"):
        raise HTTPException(status_code=400, detail="La optimizacion no convergio para la metodologia seleccionada.")
    return np.array(optimized["weights"], dtype=float)


def _benchmark_payload(
    db: sqlite3.Connection,
    target_holdings: int,
    candidate_pool_size: Optional[int],
    sector: Optional[str],
) -> Dict:
    profile_cfg = RISK_PROFILES["neutro"]
    candidates, total_f5_count = _select_candidates(db, profile_cfg, 636, sector)
    effective_pool = _resolve_candidate_pool_size(profile_cfg, candidate_pool_size, total_f5_count)
    candidates = candidates[:effective_pool]
    selected_tickers, selected_weights = _build_benchmark_portfolio(candidates, target_holdings)
    if not selected_tickers:
        raise HTTPException(status_code=404, detail="No se encontraron acciones para construir el benchmark.")

    metadata = {candidate["ticker"]: candidate for candidate in candidates}
    splits = _get_split_dates()
    series = _fetch_price_series(db, selected_tickers, splits["calibration_start"], splits["calibration_end"])
    close_map = _closes_from_series(series)
    min_len = min(len(close_map[ticker]) for ticker in selected_tickers)
    returns_matrix = np.column_stack([_daily_returns(close_map[ticker][-min_len:]) for ticker in selected_tickers])
    ann_returns = _historical_ann_returns(selected_tickers, metadata, returns_matrix)
    metrics = _portfolio_metrics(selected_weights, returns_matrix, ann_returns, DEFAULT_RISK_FREE_RATE)
    metrics["method"] = "benchmark"
    metrics["method_label"] = "Benchmark academico top CAGR"

    return {
        "methodology_id": "benchmark",
        "portfolio": _portfolio_rows(selected_tickers, selected_weights, metadata),
        "metrics": metrics,
        "universe": {
            "name": "Universo F5",
            "total_f5_count": total_f5_count,
            "screened_candidate_count": len(candidates),
            "candidate_pool_size": effective_pool,
            "optimizer_universe_size": len(selected_tickers),
            "target_holdings": target_holdings,
            "sector_filter": sector,
        },
    }


def _select_market_cap_candidates(
    db: sqlite3.Connection,
    limit: int,
    sector_filter: Optional[str],
) -> Tuple[List[Dict], int]:
    where_sql, params = f5_base_where_sql()
    clauses = [where_sql]
    out_params: List = list(params)
    if sector_filter:
        clauses.append("sector = ?")
        out_params.append(sector_filter)
    final_where = " AND ".join(clauses)

    total_count = db.execute(
        f"SELECT COUNT(*) AS total FROM stocks WHERE {final_where}",
        out_params,
    ).fetchone()["total"]

    rows = db.execute(
        f"""
        SELECT
            ticker,
            short_name,
            sector,
            industry,
            cagr,
            ann_volatility,
            market_cap,
            current_price,
            dividend_yield,
            trailing_pe,
            beta,
            n_rows
        FROM stocks
        WHERE {final_where}
        ORDER BY market_cap DESC NULLS LAST
        LIMIT ?
        """,
        out_params + [limit],
    ).fetchall()
    return [dict(row) for row in rows], int(total_count)


def _base_case_payload(
    db: sqlite3.Connection,
    n_holdings: int,
    sector: Optional[str],
) -> Dict:
    n_holdings = max(3, min(int(n_holdings), TARGET_HOLDINGS_MAX))
    candidates, total_f5_count = _select_market_cap_candidates(db, max(200, n_holdings), sector)
    if not candidates:
        raise HTTPException(status_code=404, detail="No se encontraron acciones para construir el caso base.")

    selected = candidates[:n_holdings]
    selected_tickers = [item["ticker"] for item in selected]
    selected_weights = np.ones(len(selected_tickers), dtype=float) / len(selected_tickers)

    metadata = {candidate["ticker"]: candidate for candidate in candidates}
    splits = _get_split_dates()
    series = _fetch_price_series(db, selected_tickers, splits["calibration_start"], splits["calibration_end"])
    close_map = _closes_from_series(series)
    min_len = min(len(close_map[ticker]) for ticker in selected_tickers)
    returns_matrix = np.column_stack([_daily_returns(close_map[ticker][-min_len:]) for ticker in selected_tickers])
    ann_returns = _historical_ann_returns(selected_tickers, metadata, returns_matrix)
    metrics = _portfolio_metrics(selected_weights, returns_matrix, ann_returns, DEFAULT_RISK_FREE_RATE)
    metrics["method"] = "base_case"
    metrics["method_label"] = "Caso base top market cap"
    metrics["rebalance_policy"] = "Rebalanceo mensual a pesos iguales."

    return {
        "methodology_id": "base_case",
        "portfolio": _portfolio_rows(selected_tickers, selected_weights, metadata),
        "metrics": metrics,
        "simulation_defaults": {
            "initial_capital": 100000,
            "expected_return_pct": metrics["expected_return_pct"],
            "volatility_pct": metrics["volatility_pct"],
            "max_loss_pct": 15.0,
            "commission_rate_pct": 1.0,
            "p2_acceptance_prob_pct": 70.0,
            "rebalance_freq_weeks": DEFAULT_REBALANCE_FREQ_WEEKS,
            "rebalance_return_boost_pct": 0.0,
            "years": 3,
        },
        "universe": {
            "name": "Universo F5",
            "total_f5_count": total_f5_count,
            "screened_candidate_count": len(candidates),
            "optimizer_universe_size": len(selected_tickers),
            "target_holdings": n_holdings,
            "sector_filter": sector,
        },
    }


@router.get("/catalog")
def get_portfolio_catalog():
    catalog = get_catalog()
    catalog["base_parameters"] = get_base_parameters()
    catalog["profiles"] = [
        {
            "id": key,
            "label": value["label"],
            "description": value["description"],
            "alpha_pct": round(value["alpha_p"] * 100, 2),
            "candidate_pool_default": value["candidate_pool_default"],
            "candidate_pool_range": value["candidate_pool_range"],
            "forced_sectors": value["sectors"],
        }
        for key, value in RISK_PROFILES.items()
    ]
    catalog["benchmark_note"] = "El benchmark se mantiene como comparacion secundaria y no forma parte del selector metodologico principal."
    return JSONResponse(content=catalog, headers={"Cache-Control": _CACHE_5M})


@router.post("/optimize")
def optimize_portfolio(
    req: OptimizeRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    methodology_id = _resolve_methodology_id(req)
    if methodology_id == "benchmark":
        payload = _benchmark_payload(
            db=db,
            target_holdings=_resolve_target_holdings(req),
            candidate_pool_size=req.candidate_pool_size,
            sector=req.sector,
        )
        return JSONResponse(content=payload)

    try:
        methodology = get_methodology(methodology_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Metodologia no encontrada en el catalogo.") from exc

    splits = _get_split_dates()
    target_holdings = _resolve_target_holdings(req)
    profile_key, profile_cfg, alpha_p = _resolve_profile(req)

    prelim_candidates, total_f5_count = _select_candidates(
        db=db,
        profile_cfg=profile_cfg,
        candidate_pool_size=636,
        sector_filter=req.sector,
    )
    candidate_pool_size = _resolve_candidate_pool_size(profile_cfg, req.candidate_pool_size, total_f5_count)
    candidates = prelim_candidates[:candidate_pool_size]
    if not candidates:
        raise HTTPException(status_code=404, detail="No se encontraron acciones que cumplan el universo F5.")

    metadata = {candidate["ticker"]: candidate for candidate in candidates}
    optimizer_universe_size = _optimizer_universe_size(len(candidates), target_holdings)
    optimizer_candidates = candidates[:optimizer_universe_size]
    optimizer_tickers = [candidate["ticker"] for candidate in optimizer_candidates]

    calibration_series = _fetch_price_series(
        db,
        optimizer_tickers,
        splits["calibration_start"],
        splits["calibration_end"],
    )
    valid_tickers, returns_matrix = _align_return_matrix(calibration_series, optimizer_tickers)

    methodology_params = _normalize_parameter_values(methodology, req.parameter_values)
    _ensure_required_inputs(methodology, methodology_params)
    ann_returns, estimation_info = _estimate_returns(
        methodology_id,
        valid_tickers,
        metadata,
        returns_matrix,
        methodology_params,
    )
    risk_free_rate_pct = _normalize_numeric(methodology_params.get("risk_free_rate_pct"), DEFAULT_RISK_FREE_RATE * 100) or DEFAULT_RISK_FREE_RATE * 100
    risk_free_rate = risk_free_rate_pct / 100.0
    cvar_beta_pct = _normalize_numeric(methodology_params.get("cvar_beta_pct"), profile_cfg["cvar_level"] * 100) or profile_cfg["cvar_level"] * 100
    cvar_level = max(0.50, min(cvar_beta_pct / 100.0, 0.99))

    solver_details = None
    if methodology_id == "finpuc_hibrido":
        optimized_weights, cash_weight, solver_details = _run_hybrid_solver(
            valid_tickers,
            metadata,
            returns_matrix,
            ann_returns,
            methodology_params,
            profile_key,
            alpha_p,
        )
        selected_tickers, selected_weights, selected_returns, selected_ann_returns = _trim_portfolio(
            valid_tickers,
            optimized_weights,
            returns_matrix,
            ann_returns,
            target_holdings,
            renormalize=False,
        )
    else:
        cash_weight = 0.0
        optimized_weights = _run_primary_optimizer(
            methodology_id,
            valid_tickers,
            returns_matrix,
            ann_returns,
            risk_free_rate,
        )
        selected_tickers, selected_weights, selected_returns, selected_ann_returns = _trim_portfolio(
            valid_tickers,
            optimized_weights,
            returns_matrix,
            ann_returns,
            target_holdings,
            renormalize=True,
        )

    if len(selected_tickers) == 0:
        raise HTTPException(status_code=400, detail="No fue posible construir el portafolio solicitado.")

    metrics = _portfolio_metrics(selected_weights, selected_returns, selected_ann_returns, risk_free_rate)
    metrics["method"] = methodology_id
    metrics["method_label"] = methodology["label"]
    metrics["cash_weight_pct"] = round(cash_weight * 100, 2)

    cvar_value = compute_cvar(selected_weights, selected_returns, confidence_level=cvar_level)
    cvar_pct = round(cvar_value * 100, 2)
    cvar_compliant = bool(cvar_value <= alpha_p) if alpha_p > 0 else True

    commission_rate_pct = _normalize_numeric(methodology_params.get("commission_rate_pct"), DEFAULT_COMMISSION_RATE * 100) or DEFAULT_COMMISSION_RATE * 100
    commission_rate = commission_rate_pct / 100.0
    scenarios = project_scenarios(
        initial_capital=req.initial_capital,
        expected_return=metrics["expected_return_pct"] / 100.0,
        volatility=metrics["volatility_pct"] / 100.0,
        years=5,
        commission_rate=commission_rate,
    )
    scenario_timeseries = project_scenarios_timeseries(
        initial_capital=req.initial_capital,
        expected_return=metrics["expected_return_pct"] / 100.0,
        volatility=metrics["volatility_pct"] / 100.0,
        years=5,
        commission_rate=commission_rate,
    )

    parameters_used = _build_parameter_groups(
        methodology,
        methodology_params,
        profile_key,
        profile_cfg,
        alpha_p,
        target_holdings,
        len(candidates),
        req.sector,
    )
    validation = _validation_summary(db, selected_tickers, selected_weights, splits)

    efficient_frontier = None
    if methodology_id != "finpuc_hibrido":
        frontier_points = compute_efficient_frontier(
            list(valid_tickers),
            returns_matrix,
            risk_free_rate,
            n_points=25,
        )
        efficient_frontier = [
            {"volatility_pct": vol, "expected_return_pct": ret}
            for vol, ret in frontier_points
        ]

    response = {
        "methodology_id": methodology_id,
        "risk_level": profile_key,
        "profile_label": profile_cfg["label"],
        "profile_description": profile_cfg["description"],
        "alpha_p": alpha_p,
        "max_loss_pct": alpha_p,
        "portfolio": _portfolio_rows(selected_tickers, selected_weights, metadata),
        "metrics": metrics,
        "cvar_pct": cvar_pct,
        "cvar_level_pct": round(cvar_level * 100, 2),
        "cvar_compliant": cvar_compliant,
        "scenarios": scenarios,
        "scenario_timeseries": scenario_timeseries,
        "data_split": splits,
        "validation": validation,
        "commission_rate_pct": round(commission_rate_pct, 2),
        "methodology": _build_methodology_payload(
            methodology,
            methodology_id,
            estimation_info,
            parameters_used,
            solver_details,
        ),
        "efficient_frontier": efficient_frontier,
        "parameter_values": methodology_params,
        "parameters_used": parameters_used,
        "universe": _build_universe(
            profile_cfg=profile_cfg,
            total_f5_count=total_f5_count,
            candidates=candidates,
            candidate_pool_size=len(candidates),
            optimizer_universe_size=len(valid_tickers),
            target_holdings=target_holdings,
            sector_filter=req.sector,
        ),
        "weekly_cycle": _build_weekly_cycle(methodology_params),
        "simulation_defaults": {
            "initial_capital": req.initial_capital,
            "expected_return_pct": metrics["expected_return_pct"],
            "volatility_pct": metrics["volatility_pct"],
            "max_loss_pct": round(alpha_p * 100, 2),
            "commission_rate_pct": round(commission_rate_pct, 2),
            "p2_acceptance_prob_pct": round(_normalize_numeric(methodology_params.get("p2_acceptance_prob_pct"), 70.0) or 70.0, 2),
            "rebalance_freq_weeks": DEFAULT_REBALANCE_FREQ_WEEKS,
            "rebalance_return_boost_pct": 0.1,
            "years": 3,
        },
    }
    return JSONResponse(content=response)


@router.get("/benchmark")
def get_benchmark(
    target_holdings: int = Query(default=10, ge=3, le=TARGET_HOLDINGS_MAX),
    candidate_pool_size: Optional[int] = Query(default=None, ge=10, le=636),
    sector: Optional[str] = Query(default=None),
    n: Optional[int] = Query(default=None, ge=3, le=TARGET_HOLDINGS_MAX),
    db: sqlite3.Connection = Depends(get_db),
):
    target_holdings = _coerce_query_default(target_holdings)
    candidate_pool_size = _coerce_query_default(candidate_pool_size)
    sector = _coerce_query_default(sector)
    n = _coerce_query_default(n)
    effective_holdings = n or target_holdings
    payload = _benchmark_payload(
        db=db,
        target_holdings=effective_holdings,
        candidate_pool_size=candidate_pool_size,
        sector=sector,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": _CACHE_5M})


@router.get("/base_case")
def get_base_case(
    n: int = Query(default=10, ge=3, le=TARGET_HOLDINGS_MAX),
    sector: Optional[str] = Query(default=None),
    db: sqlite3.Connection = Depends(get_db),
):
    n = _coerce_query_default(n)
    sector = _coerce_query_default(sector)
    payload = _base_case_payload(
        db=db,
        n_holdings=n,
        sector=sector,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": _CACHE_5M})


@router.get("/diagnostics/returns")
def get_return_diagnostics(
    n: int = Query(default=30, ge=5, le=80),
    order: str = Query(default="market_cap"),
    sector: Optional[str] = Query(default=None),
    bins: int = Query(default=30, ge=10, le=80),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Diagnostico rapido de distribuciones de retornos (normalidad) sobre el universo F5 filtrado.
    Por defecto toma los top `n` por market cap (representativo para presentacion).
    """
    n = int(_coerce_query_default(n))
    order = str(_coerce_query_default(order) or "market_cap").lower()
    sector = _coerce_query_default(sector)

    if order == "market_cap":
        candidates, total_f5_count = _select_market_cap_candidates(db, max(200, n), sector)
    else:
        profile_cfg = RISK_PROFILES["neutro"]
        candidates, total_f5_count = _select_candidates(db, profile_cfg, 636, sector)
    candidates = candidates[:n]
    tickers = [candidate["ticker"] for candidate in candidates]
    if len(tickers) < 5:
        raise HTTPException(status_code=404, detail="No hay suficientes tickers para diagnostico de distribuciones.")

    splits = _get_split_dates()
    series = _fetch_price_series(db, tickers, splits["calibration_start"], splits["calibration_end"])
    close_map = _closes_from_series(series)
    min_len = min(len(close_map[ticker]) for ticker in tickers if ticker in close_map)
    returns = {
        ticker: _daily_returns(close_map[ticker][-min_len:])
        for ticker in tickers
        if ticker in close_map and len(close_map[ticker]) >= 252
    }
    if len(returns) < 5:
        raise HTTPException(status_code=404, detail="No hay suficientes series con historia util para diagnostico.")

    try:
        from scipy import stats  # type: ignore
    except Exception:  # pragma: no cover
        stats = None

    def _fit_distributions_pct(values_pct: np.ndarray) -> Dict:
        """
        Ajusta distribuciones simples sobre retornos en % (para comparacion y explicacion).
        Importante: esto NO arregla no-iid / clustering de volatilidad; solo ayuda a describir colas/asimetria.
        """
        values_pct = np.array(values_pct, dtype=float)
        values_pct = values_pct[np.isfinite(values_pct)]
        n_obs = int(values_pct.size)
        if not stats or n_obs < 50:
            return {"best_by_bic": None, "candidates": [], "notes": "No hay suficientes datos para ajustar distribuciones."}

        def _aic_bic(loglik: float, k_params: int) -> Tuple[float, float]:
            aic = 2 * k_params - 2 * loglik
            bic = k_params * float(np.log(n_obs)) - 2 * loglik
            return float(aic), float(bic)

        candidates: List[Dict] = []

        mu = float(values_pct.mean())
        sigma = float(values_pct.std(ddof=1)) if n_obs > 1 else 0.0
        if sigma > 0:
            ll = float(np.sum(stats.norm.logpdf(values_pct, loc=mu, scale=sigma)))
            aic, bic = _aic_bic(ll, 2)
            candidates.append(
                {
                    "name": "normal",
                    "params": {"mu_pct": round(mu, 6), "sigma_pct": round(sigma, 6)},
                    "loglik": round(ll, 3),
                    "aic": round(aic, 3),
                    "bic": round(bic, 3),
                }
            )

        # Student-t: captura colas pesadas con df bajo (df -> infinito recupera Normal)
        try:
            df, loc, scale = stats.t.fit(values_pct)
            if float(scale) > 0 and float(df) > 0:
                ll = float(np.sum(stats.t.logpdf(values_pct, df, loc=loc, scale=scale)))
                aic, bic = _aic_bic(ll, 3)
                candidates.append(
                    {
                        "name": "student_t",
                        "params": {"df": round(float(df), 6), "loc_pct": round(float(loc), 6), "scale_pct": round(float(scale), 6)},
                        "loglik": round(ll, 3),
                        "aic": round(aic, 3),
                        "bic": round(bic, 3),
                    }
                )
        except Exception:
            pass

        # Johnson SU: flexible para asimetria + colas (4 parametros)
        try:
            a, b, loc, scale = stats.johnsonsu.fit(values_pct)
            if float(scale) > 0:
                ll = float(np.sum(stats.johnsonsu.logpdf(values_pct, a, b, loc=loc, scale=scale)))
                aic, bic = _aic_bic(ll, 4)
                candidates.append(
                    {
                        "name": "johnsonsu",
                        "params": {
                            "a": round(float(a), 6),
                            "b": round(float(b), 6),
                            "loc_pct": round(float(loc), 6),
                            "scale_pct": round(float(scale), 6),
                        },
                        "loglik": round(ll, 3),
                        "aic": round(aic, 3),
                        "bic": round(bic, 3),
                    }
                )
        except Exception:
            pass

        candidates.sort(key=lambda item: item.get("bic", float("inf")))
        best = candidates[0]["name"] if candidates else None

        implied_df = None
        try:
            # Para Student-t con df>4: exceso kurtosis = 6/(df-4) => df ~= 4 + 6/k
            k_excess = float(stats.kurtosis(values_pct, fisher=True))
            if k_excess > 0:
                implied_df = 4.0 + 6.0 / k_excess
        except Exception:
            implied_df = None

        notes = (
            "Regla rapida: kurtosis_excess alta sugiere colas pesadas => Student-t (df bajo). "
            "Skew significativo sugiere distribucion asimetrica (p.ej. Johnson SU o skew-t)."
        )
        if implied_df is not None and np.isfinite(implied_df):
            notes += f" df(t) aproximado por kurtosis: {round(float(implied_df), 3)}."

        return {"best_by_bic": best, "candidates": candidates, "notes": notes}

    assets: List[Dict] = []
    pooled = []
    candidate_meta = {candidate["ticker"]: candidate for candidate in candidates}
    sector_groups: Dict[str, Dict] = {}

    def _histogram_pct(values: np.ndarray) -> Dict:
        values = values[np.isfinite(values)]
        if not values.size:
            return {"bin_edges_pct": [], "counts": []}
        counts, edges = np.histogram(values * 100.0, bins=int(bins))
        return {
            "bin_edges_pct": [round(float(x), 6) for x in edges.tolist()],
            "counts": [int(x) for x in counts.tolist()],
        }

    for ticker, arr in returns.items():
        arr = np.array(arr, dtype=float)
        pooled.append(arr)
        meta = candidate_meta.get(ticker, {})
        sector_name = meta.get("sector") or "Unknown"
        industry = meta.get("industry")

        mean = float(arr.mean())
        std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
        skew = float(stats.skew(arr)) if stats else float(np.nan)
        kurt = float(stats.kurtosis(arr, fisher=True)) if stats else float(np.nan)
        jb_p = float(stats.jarque_bera(arr).pvalue) if stats else float(np.nan)
        dag_p = float(stats.normaltest(arr).pvalue) if stats and arr.size >= 20 else float(np.nan)

        asset_payload = {
            "ticker": ticker,
            "sector": sector_name,
            "industry": industry,
            "n": int(arr.size),
            "mean_daily_pct": round(mean * 100, 4),
            "std_daily_pct": round(std * 100, 4),
            "skew": round(skew, 4) if stats else None,
            "kurtosis_excess": round(kurt, 4) if stats else None,
            "jarque_bera_p": round(jb_p, 6) if stats else None,
            "normaltest_p": round(dag_p, 6) if stats and arr.size >= 20 else None,
            "market_cap_b": round(float(meta.get("market_cap") or 0.0) / 1e9, 2) if meta else None,
        }
        assets.append(asset_payload)

        group = sector_groups.get(sector_name)
        if group is None:
            group = {
                "sector": sector_name,
                "assets": [],
                "_pooled": [],
            }
            sector_groups[sector_name] = group
        group["assets"].append(asset_payload)
        group["_pooled"].append(arr)

    pooled_arr = np.concatenate(pooled) if pooled else np.array([])
    pooled_summary = {}
    if pooled_arr.size:
        pooled_mean = float(pooled_arr.mean())
        pooled_std = float(pooled_arr.std(ddof=1)) if pooled_arr.size > 1 else 0.0
        pooled_summary = {
            "n": int(pooled_arr.size),
            "mean_daily_pct": round(pooled_mean * 100, 4),
            "std_daily_pct": round(pooled_std * 100, 4),
        }
        if stats:
            pooled_summary.update(
                {
                    "skew": round(float(stats.skew(pooled_arr)), 4),
                    "kurtosis_excess": round(float(stats.kurtosis(pooled_arr, fisher=True)), 4),
                    "jarque_bera_p": round(float(stats.jarque_bera(pooled_arr).pvalue), 6),
                    "normaltest_p": round(float(stats.normaltest(pooled_arr).pvalue), 6) if pooled_arr.size >= 20 else None,
                }
            )
        pooled_summary["fit"] = _fit_distributions_pct(pooled_arr * 100.0)

    if stats and assets:
        jb_pass = [a for a in assets if a.get("jarque_bera_p") is not None and a["jarque_bera_p"] >= 0.05]
        dag_pass = [a for a in assets if a.get("normaltest_p") is not None and a["normaltest_p"] >= 0.05]
        jb_pass_rate = round(len(jb_pass) / len(assets), 4)
        dag_pass_rate = round(len(dag_pass) / len(assets), 4)
    else:
        jb_pass_rate = 0.0
        dag_pass_rate = 0.0

    sectors_payload: List[Dict] = []
    for sector_name, group in sector_groups.items():
        sector_assets = group.get("assets", [])
        pooled_sector = np.concatenate(group.get("_pooled", [])) if group.get("_pooled") else np.array([])
        sector_summary: Dict[str, object] = {"n_assets": len(sector_assets)}
        if pooled_sector.size:
            sector_summary.update(
                {
                    "n": int(pooled_sector.size),
                    "mean_daily_pct": round(float(pooled_sector.mean()) * 100, 4),
                    "std_daily_pct": round(float(pooled_sector.std(ddof=1)) * 100, 4) if pooled_sector.size > 1 else 0.0,
                    "histogram": _histogram_pct(pooled_sector),
                }
            )
            if stats:
                sector_summary.update(
                    {
                        "skew": round(float(stats.skew(pooled_sector)), 4),
                        "kurtosis_excess": round(float(stats.kurtosis(pooled_sector, fisher=True)), 4),
                        "jarque_bera_p": round(float(stats.jarque_bera(pooled_sector).pvalue), 6),
                        "normaltest_p": round(float(stats.normaltest(pooled_sector).pvalue), 6) if pooled_sector.size >= 20 else None,
                    }
                )
            sector_summary["fit"] = _fit_distributions_pct(pooled_sector * 100.0)
        sectors_payload.append(
            {
                "sector": sector_name,
                "summary": sector_summary,
                "assets": [
                    {
                        "ticker": a.get("ticker"),
                        "industry": a.get("industry"),
                        "mean_daily_pct": a.get("mean_daily_pct"),
                        "std_daily_pct": a.get("std_daily_pct"),
                        "jarque_bera_p": a.get("jarque_bera_p"),
                        "normaltest_p": a.get("normaltest_p"),
                    }
                    for a in sector_assets
                ],
            }
        )
    sectors_payload.sort(key=lambda item: (item.get("summary", {}).get("n_assets", 0)), reverse=True)

    return JSONResponse(
        content={
            "calibration_window": {
                "start": splits["calibration_start"],
                "end": splits["calibration_end"],
            },
            "universe": {
                "name": "Universo F5",
                "total_f5_count": total_f5_count,
                "sector_filter": sector,
                "order": order,
                "bins": int(bins),
            },
            "summary": {
                "n_assets": len(assets),
                "jarque_bera_pass_rate_5pct": jb_pass_rate,
                "normaltest_pass_rate_5pct": dag_pass_rate,
                "notes": (
                    "Interpretacion: p >= 0.05 no rechaza normalidad (alpha 5%). "
                    "En retornos financieros es comun observar p < 0.05 por colas pesadas/asimetria, "
                    "aun si el histograma parece 'en campana' (tests sensibles con n grande)."
                ),
            },
            "pooled": pooled_summary,
            "assets": assets,
            "sectors": sectors_payload,
        },
        headers={"Cache-Control": _CACHE_5M},
    )


@router.get("/diagnostics/returns/{ticker}")
def get_ticker_return_diagnostics(
    ticker: str,
    bins: int = Query(default=40, ge=10, le=120),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Diagnostico distribucional por accion (retornos diarios en ventana de calibracion),
    para habilitar estudio individual desde la UI.
    """
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker vacio.")

    where_sql, params = f5_base_where_sql()
    row = db.execute(
        f"""
        SELECT ticker, short_name, sector, industry, market_cap, n_rows
        FROM stocks
        WHERE {where_sql} AND ticker = ?
        """,
        list(params) + [ticker],
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticker no encontrado en el universo F5.")
    meta = dict(row)

    splits = _get_split_dates()
    series = _fetch_price_series(db, [ticker], splits["calibration_start"], splits["calibration_end"])
    close_map = _closes_from_series(series)
    closes = close_map.get(ticker, [])
    if len(closes) < 252:
        raise HTTPException(status_code=404, detail="Historia insuficiente para diagnostico de retornos.")
    returns = np.array(_daily_returns(closes), dtype=float)
    returns = returns[np.isfinite(returns)]
    if returns.size < 30:
        raise HTTPException(status_code=404, detail="No hay suficientes retornos para diagnostico.")

    from scipy import stats  # type: ignore

    mean = float(returns.mean())
    std = float(returns.std(ddof=1)) if returns.size > 1 else 0.0
    skew = float(stats.skew(returns))
    kurt = float(stats.kurtosis(returns, fisher=True))
    jb_p = float(stats.jarque_bera(returns).pvalue)
    dag_p = float(stats.normaltest(returns).pvalue) if returns.size >= 20 else float("nan")

    counts, edges = np.histogram(returns * 100.0, bins=int(bins))
    hist = {
        "bin_edges_pct": [round(float(x), 6) for x in edges.tolist()],
        "counts": [int(x) for x in counts.tolist()],
    }

    # QQ-plot data (subsample to keep payload small)
    (osm, osr), (slope, intercept, r) = stats.probplot(returns, dist="norm")
    osm = np.array(osm, dtype=float)
    osr = np.array(osr, dtype=float)
    if osm.size > 400:
        idx = np.linspace(0, osm.size - 1, 400).astype(int)
        osm = osm[idx]
        osr = osr[idx]
    qq = {
        "theoretical": [round(float(x), 6) for x in osm.tolist()],
        "sample": [round(float(x), 6) for x in osr.tolist()],
        "fit": {
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 6),
            "r": round(float(r), 6),
        },
    }

    return JSONResponse(
        content={
            "calibration_window": {
                "start": splits["calibration_start"],
                "end": splits["calibration_end"],
            },
            "asset": {
                "ticker": meta.get("ticker"),
                "short_name": meta.get("short_name"),
                "sector": meta.get("sector"),
                "industry": meta.get("industry"),
                "market_cap_b": round(float(meta.get("market_cap") or 0.0) / 1e9, 2),
                "n_rows": meta.get("n_rows"),
            },
            "summary": {
                "n": int(returns.size),
                "mean_daily_pct": round(mean * 100, 6),
                "std_daily_pct": round(std * 100, 6),
                "skew": round(skew, 6),
                "kurtosis_excess": round(kurt, 6),
                "jarque_bera_p": round(jb_p, 6),
                "normaltest_p": round(dag_p, 6) if returns.size >= 20 else None,
                "fit": _fit_distributions_pct(returns * 100.0),
            },
            "histogram": hist,
            "qq_plot": qq,
        },
        headers={"Cache-Control": _CACHE_5M},
    )


@router.post("/simulate")
def simulate_portfolio(req: SimulateRequest):
    commission_rate = req.commission_rate_pct / 100.0
    accept_prob = req.p2_acceptance_prob_pct / 100.0
    rebalance_boost = req.rebalance_return_boost_pct / 100.0
    result = simulate_client_behavior(
        initial_capital=req.initial_capital,
        expected_return=req.expected_return,
        volatility=req.volatility,
        max_loss_pct=req.max_loss_pct,
        years=req.years,
        commission_rate=commission_rate,
        accept_prob=accept_prob,
        n_simulations=req.n_simulations,
        rebalance_freq_weeks=req.rebalance_freq_weeks,
        rebalance_return_boost=rebalance_boost,
    )
    result["weekly_cycle"] = _build_weekly_cycle(
        {
            "commission_rate_pct": req.commission_rate_pct,
            "p2_acceptance_prob_pct": req.p2_acceptance_prob_pct,
            "p1_withdrawal_drawdown_pct": req.max_loss_pct * 100.0,
        }
    )
    result["assumptions"] = {
        "commission_rate_pct": round(req.commission_rate_pct, 2),
        "acceptance_model": f"Aproximacion operacional de P2 con probabilidad base {round(req.p2_acceptance_prob_pct, 2)}%.",
        "withdrawal_model": f"Aproximacion operacional mensual de P1 por drawdown sobre {round(req.max_loss_pct * 100, 2)}%.",
        "rebalance_freq_weeks": req.rebalance_freq_weeks,
        "rebalance_return_boost_pct": round(req.rebalance_return_boost_pct, 2),
    }
    return JSONResponse(content=result)
