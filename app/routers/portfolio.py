"""
portfolio.py — Endpoints de gestión de portafolios.

POST /api/portfolio/optimize
    Genera un portafolio optimizado según el perfil de riesgo del cliente.
    Épica 1 & 2 & 3.

GET /api/portfolio/benchmark
    Retorna el benchmark simple: top-N acciones por CAGR histórico.
    Épica 3.

POST /api/portfolio/simulate
    Simulación Monte Carlo del comportamiento del cliente.
    Épica 2 & 3.
"""
import sqlite3
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import get_db
from ..services.benchmark import get_top_cagr_benchmark
from ..services.markowitz import compute_markowitz_portfolio, minimum_variance_portfolio
from ..services.scenarios import project_scenarios, project_scenarios_timeseries
from ..services.simulation import simulate_client_behavior

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_CACHE_5M = "public, max-age=300"

COMMISSION_RATE = 0.01      # 1% anual sobre el capital total
RISK_FREE_RATE  = 0.05      # tasa libre de riesgo (referencia EE.UU.)

# Épica 3: separación calibración / validación.
# 8 años de calibración permiten capturar varios ciclos de mercado (2008, 2020, etc.)
# y 2 años de validación ofrecen suficiente data out-of-sample para evaluar el modelo.
CALIBRATION_YEARS = 8
VALIDATION_YEARS  = 2


# ============================================================
# Request schemas
# ============================================================

class OptimizeRequest(BaseModel):
    initial_capital: float = Field(gt=0, description="Capital inicial en USD")
    max_loss_pct: float = Field(
        ge=0.01, le=1.0,
        description="Tolerancia máxima de pérdida (0.01–1.0)",
    )
    n_stocks: int = Field(default=10, ge=3, le=30)
    method: str = Field(
        default="markowitz",
        description="'markowitz' para optimización formal, 'benchmark' para top-CAGR",
    )
    sector: Optional[str] = Field(default=None)


class SimulateRequest(BaseModel):
    initial_capital: float = Field(gt=0)
    max_loss_pct: float = Field(ge=0.01, le=1.0)
    expected_return: float = Field(description="Retorno anual esperado (decimal)")
    volatility: float = Field(ge=0, description="Volatilidad anual (decimal)")
    years: int = Field(default=3, ge=1, le=10)
    n_simulations: int = Field(default=500, ge=100, le=2000)


# ============================================================
# Helpers
# ============================================================

def _risk_level(max_loss_pct: float) -> str:
    """Clasifica el perfil de riesgo según la tolerancia máxima de pérdida."""
    if max_loss_pct <= 0.15:
        return "conservador"
    elif max_loss_pct <= 0.35:
        return "moderado"
    return "agresivo"


def _get_split_dates() -> Dict[str, str]:
    """Fechas del split calibración / validación."""
    today = date.today()
    val_end   = today
    val_start = today.replace(year=today.year - VALIDATION_YEARS)
    cal_end   = val_start - timedelta(days=1)
    cal_start = cal_end.replace(year=cal_end.year - CALIBRATION_YEARS)
    return {
        "calibration_start": cal_start.isoformat(),
        "calibration_end":   cal_end.isoformat(),
        "validation_start":  val_start.isoformat(),
        "validation_end":    val_end.isoformat(),
    }


def _fetch_prices(
    db: sqlite3.Connection,
    tickers: List[str],
    start: str,
    end: str,
) -> Dict[str, List[float]]:
    """Devuelve {ticker: [close, ...]} para el rango de fechas dado."""
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    rows = db.execute(
        f"""
        SELECT ticker, close
        FROM prices
        WHERE ticker IN ({placeholders})
          AND date >= ? AND date <= ?
          AND close IS NOT NULL
        ORDER BY ticker, date ASC
        """,
        tickers + [start, end],
    ).fetchall()

    data: Dict[str, List[float]] = {}
    for row in rows:
        data.setdefault(row["ticker"], []).append(row["close"])
    return data


def _daily_returns(prices: List[float]) -> np.ndarray:
    arr = np.array(prices, dtype=float)
    return np.diff(arr) / arr[:-1]


def _is_scipy_available() -> bool:
    try:
        import scipy  # noqa: F401
        return True
    except ImportError:
        return False


# ============================================================
# Endpoints
# ============================================================

@router.post("/optimize")
def optimize_portfolio(
    req: OptimizeRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Genera un portafolio optimizado según el perfil de riesgo del cliente.

    Épica 1: recibe tolerancia máxima de pérdida → devuelve portafolio +
    escenarios de retorno (favorable / neutro / desfavorable).
    Épica 3: split calibración/validación, Markowitz vs. benchmark.
    """
    splits = _get_split_dates()
    risk_level = _risk_level(req.max_loss_pct)

    # ----------------------------------------------------------
    # 1. Selección de candidatos
    # ----------------------------------------------------------
    sector_clause = "AND sector = ?" if req.sector else ""
    sector_params = [req.sector] if req.sector else []

    candidate_n = min(req.n_stocks * 4, 60)
    rows = db.execute(
        f"""
        SELECT ticker, short_name, sector, cagr, ann_volatility
        FROM stocks
        WHERE cagr IS NOT NULL
          AND ann_volatility IS NOT NULL
          AND n_rows >= 252
          {sector_clause}
        ORDER BY cagr DESC
        LIMIT ?
        """,
        sector_params + [candidate_n],
    ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron acciones con datos suficientes.",
        )

    candidates = [dict(r) for r in rows]
    ticker_meta = {c["ticker"]: c for c in candidates}

    # ----------------------------------------------------------
    # 2. Optimización
    # ----------------------------------------------------------
    use_markowitz = req.method == "markowitz" and _is_scipy_available()

    if use_markowitz:
        # Cargar retornos del período de calibración
        cand_tickers = [c["ticker"] for c in candidates]
        price_map = _fetch_prices(
            db, cand_tickers,
            splits["calibration_start"],
            splits["calibration_end"],
        )

        # Filtrar tickers con al menos 252 observaciones en calibración
        valid = [t for t in cand_tickers if len(price_map.get(t, [])) >= 252]

        if len(valid) >= 3:
            valid = valid[: req.n_stocks]
            min_len = min(len(price_map[t]) for t in valid)
            returns_matrix = np.column_stack(
                [_daily_returns(price_map[t][-min_len:]) for t in valid]
            )

            if risk_level == "conservador":
                opt = minimum_variance_portfolio(valid, returns_matrix, RISK_FREE_RATE)
            else:
                opt = compute_markowitz_portfolio(valid, returns_matrix, RISK_FREE_RATE)

            tickers = valid
            weights = opt["weights"]
            metrics = {
                "expected_return_pct": round(opt["expected_return"] * 100, 2),
                "volatility_pct":      round(opt["volatility"] * 100, 2),
                "sharpe_ratio":        round(opt["sharpe_ratio"], 3),
                "method":              "markowitz",
            }
        else:
            use_markowitz = False  # fallback

    if not use_markowitz:
        bench = get_top_cagr_benchmark(db, n=req.n_stocks, sector=req.sector)
        tickers = [s["ticker"] for s in bench]
        weights = [s["weight"] for s in bench]
        exp_r = sum(s["cagr"] * s["weight"] for s in bench if s.get("cagr")) or 0.0
        exp_v = sum((s["ann_volatility"] or 0) * s["weight"] for s in bench)
        sharpe = (exp_r - RISK_FREE_RATE) / exp_v if exp_v > 1e-10 else 0.0
        metrics = {
            "expected_return_pct": round(exp_r * 100, 2),
            "volatility_pct":      round(exp_v * 100, 2),
            "sharpe_ratio":        round(sharpe, 3),
            "method":              "benchmark",
        }

    # ----------------------------------------------------------
    # 3. Armar lista de posiciones del portafolio
    # ----------------------------------------------------------
    portfolio_items = []
    for t, w in zip(tickers, weights):
        m = ticker_meta.get(t, {})
        portfolio_items.append({
            "ticker":        t,
            "short_name":    m.get("short_name", t),
            "sector":        m.get("sector"),
            "weight":        round(float(w), 4),
            "cagr_pct":      round(m["cagr"] * 100, 2) if m.get("cagr") else None,
            "volatility_pct": round(m["ann_volatility"] * 100, 2) if m.get("ann_volatility") else None,
        })

    # ----------------------------------------------------------
    # 4. Escenarios de retorno (Épica 1)
    # ----------------------------------------------------------
    exp_ret = metrics["expected_return_pct"] / 100
    exp_vol = metrics["volatility_pct"] / 100

    scenarios = project_scenarios(
        initial_capital=req.initial_capital,
        expected_return=exp_ret,
        volatility=exp_vol,
        years=5,
        commission_rate=COMMISSION_RATE,
    )
    scenario_ts = project_scenarios_timeseries(
        initial_capital=req.initial_capital,
        expected_return=exp_ret,
        volatility=exp_vol,
        years=5,
        commission_rate=COMMISSION_RATE,
    )

    # ----------------------------------------------------------
    # 5. Validación en período de holdout (Épica 3)
    # ----------------------------------------------------------
    validation_result = None
    val_price_map = _fetch_prices(
        db, tickers,
        splits["validation_start"],
        splits["validation_end"],
    )
    val_contributions = []
    for t, w in zip(tickers, weights):
        closes = val_price_map.get(t, [])
        if len(closes) >= 5:
            ret = (closes[-1] / closes[0]) - 1
            val_contributions.append(float(w) * ret)

    if val_contributions:
        total_val_ret = sum(val_contributions)
        validation_result = {
            "period":            f"{splits['validation_start']} → {splits['validation_end']}",
            "total_return_pct":  round(total_val_ret * 100, 2),
            "annualized_return_pct": round(
                ((1 + total_val_ret) ** (1 / VALIDATION_YEARS) - 1) * 100, 2
            ),
        }

    return JSONResponse(content={
        "risk_level":        risk_level,
        "max_loss_pct":      req.max_loss_pct,
        "portfolio":         portfolio_items,
        "metrics":           metrics,
        "scenarios":         scenarios,
        "scenario_timeseries": scenario_ts,
        "data_split":        splits,
        "validation":        validation_result,
        "commission_rate_pct": COMMISSION_RATE * 100,
    })


@router.get("/benchmark")
def get_benchmark(
    n: int = Query(default=10, ge=3, le=30),
    sector: Optional[str] = Query(default=None),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Benchmark simple: top-N acciones por CAGR histórico con pesos iguales.
    Épica 3: caso base para comparar contra Markowitz.
    """
    stocks = get_top_cagr_benchmark(db, n=n, sector=sector)
    if not stocks:
        raise HTTPException(status_code=404, detail="No se encontraron acciones.")

    exp_r = sum(s["cagr"] * s["weight"] for s in stocks if s.get("cagr")) or 0.0
    exp_v = sum((s["ann_volatility"] or 0) * s["weight"] for s in stocks)

    return JSONResponse(
        content={
            "method": "benchmark_top_cagr",
            "n_stocks": n,
            "sector_filter": sector,
            "portfolio": [
                {
                    "ticker":         s["ticker"],
                    "short_name":     s.get("short_name"),
                    "sector":         s.get("sector"),
                    "weight":         round(s["weight"], 4),
                    "cagr_pct":       round(s["cagr"] * 100, 2) if s.get("cagr") else None,
                    "volatility_pct": round(s["ann_volatility"] * 100, 2) if s.get("ann_volatility") else None,
                }
                for s in stocks
            ],
            "metrics": {
                "expected_return_pct": round(exp_r * 100, 2),
                "volatility_pct":      round(exp_v * 100, 2),
            },
        },
        headers={"Cache-Control": _CACHE_5M},
    )


@router.post("/simulate")
def simulate_portfolio(req: SimulateRequest):
    """
    Simulación Monte Carlo del comportamiento del cliente.

    Épica 2: recomendaciones periódicas con probabilidad de aceptación,
    retiro si las pérdidas superan la tolerancia, comisión del 1% anual.
    Épica 3: distribución de capital final y tasa de retiro.
    """
    result = simulate_client_behavior(
        initial_capital=req.initial_capital,
        expected_return=req.expected_return,
        volatility=req.volatility,
        max_loss_pct=req.max_loss_pct,
        years=req.years,
        commission_rate=COMMISSION_RATE,
        n_simulations=req.n_simulations,
    )
    return JSONResponse(content=result)
