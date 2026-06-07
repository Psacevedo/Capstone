"""
payloads.py — Construcción de payloads complejos para respuestas API
"""
import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from fastapi import HTTPException

from ..services.markowitz import compute_cvar
from ..services.scenarios import project_scenarios, project_scenarios_timeseries
from ..services.simulation import simulate_client_behavior
from .helpers import closes_from_series, daily_returns, portfolio_metrics, normalize_numeric


def portfolio_rows(
    tickers: Sequence[str],
    weights: Sequence[float],
    metadata: Dict[str, Dict],
) -> List[Dict]:
    """Formatea filas de portafolio para response."""
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


def validation_summary(
    db: sqlite3.Connection,
    tickers: Sequence[str],
    weights: np.ndarray,
    splits: Dict[str, str],
    fetch_price_series_func,
) -> Optional[Dict]:
    """Resumen de validación histórica del portafolio."""
    price_map = closes_from_series(fetch_price_series_func(db, tickers, splits["validation_start"], splits["validation_end"]))
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


def scenarios_payload(
    initial_capital: float,
    expected_return_pct: float,
    volatility_pct: float,
    years: int,
    commission_rate: float,
) -> Dict:
    """Proyecciones de escenarios favorables/neutros/desfavorables."""
    return project_scenarios(
        initial_capital=initial_capital,
        expected_return=expected_return_pct / 100.0,
        volatility=volatility_pct / 100.0,
        years=years,
        commission_rate=commission_rate,
    )


def scenarios_timeseries_payload(
    initial_capital: float,
    expected_return_pct: float,
    volatility_pct: float,
    years: int,
    commission_rate: float,
) -> Dict:
    """Series temporales de proyecciones de escenarios."""
    return project_scenarios_timeseries(
        initial_capital=initial_capital,
        expected_return=expected_return_pct / 100.0,
        volatility=volatility_pct / 100.0,
        years=years,
        commission_rate=commission_rate,
    )


def simulation_payload(
    initial_capital: float,
    expected_return_pct: float,
    volatility_pct: float,
    max_loss_pct: float,
    years: int,
    commission_rate: float,
    accept_prob: float = 0.70,
    n_simulations: int = 500,
    rebalance_freq_weeks: int = 4,
    rebalance_return_boost: float = 0.0,
) -> Dict:
    """Simulación de comportamiento del cliente."""
    return simulate_client_behavior(
        initial_capital=initial_capital,
        expected_return=expected_return_pct / 100.0,
        volatility=volatility_pct / 100.0,
        max_loss_pct=max_loss_pct,
        years=years,
        commission_rate=commission_rate,
        accept_prob=accept_prob,
        n_simulations=n_simulations,
        rebalance_freq_weeks=rebalance_freq_weeks,
        rebalance_return_boost=rebalance_return_boost,
    )


def build_universe(
    profile_cfg: Dict,
    total_f5_count: int,
    candidates: List[Dict],
    candidate_pool_size: int,
    optimizer_universe_size: int,
    target_holdings: int,
    sector_filter: Optional[str],
    f5_constants: Dict,
) -> Dict:
    """Construye descripción del universo operativo."""
    return {
        "name": "Universo de acciones",
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
            "min_history_rows": f5_constants.get("F5_MIN_HISTORY_ROWS", 2500),
            "min_price_usd": f5_constants.get("F5_MIN_PRICE", 5.0),
            "min_market_cap_usd": f5_constants.get("F5_MIN_MARKET_CAP", 2e9),
            "annual_vol_range_pct": [5, 100],
            "exclude_unknown_sector": True,
            "exclude_shell_companies": True,
        },
    }


def build_weekly_cycle(parameter_values: Optional[Dict[str, object]] = None) -> Dict:
    """Construye descripcion del ciclo semanal de simulacion (Entrega 2, P4)."""
    params = parameter_values or {}
    commission_rate_pct = normalize_numeric(params.get("commission_rate_pct"), 1.0) or 1.0
    p2_acceptance_prob_pct = normalize_numeric(params.get("p2_acceptance_prob_pct"), 50.0) or 50.0
    p1_drawdown_pct = normalize_numeric(params.get("p1_withdrawal_drawdown_pct"), 20.0) or 20.0
    cash_buffer_pct = normalize_numeric(params.get("cash_buffer_pct"), 5.0)
    return {
        "cadence": "Semanal",
        "trigger": "Cierre semanal de cartera",
        "rebalancing": "El sistema evalua una recomendacion semanal y rebalancea si el cliente acepta (P2 logistica, s=20).",
        "client_acceptance": f"Aproximacion operacional de P2 con probabilidad analitica derivada del retorno ofrecido vs tolerancia.",
        "client_withdrawal": f"P1 logistica (s=20): retiro evaluado semanalmente contra perdida sobre tolerancia de {round(p1_drawdown_pct, 2)}%.",
        "commissions": f"Comision anual k = {round(commission_rate_pct, 2)}% sobre capital + {round(commission_rate_pct, 2)}% sobre 5% de rotacion en cada aceptacion.",
        "dividends": (
            "Los dividendos del dataset alimentan la logica de caja chica; "
            f"la reserva referencial reportada es {round(cash_buffer_pct, 2)}%."
            if cash_buffer_pct is not None
            else "Los dividendos del dataset alimentan la logica de caja chica."
        ),
        "rebalance_frequency": "weekly",
        "withdrawal_frequency": "weekly",
        "rebalance_freq_weeks": 1,
        "horizon_years_default": 5,
        "time_budget_seconds": 10,
    }


def build_parameter_groups(
    methodology: Dict,
    parameter_values: Dict[str, object],
    profile_key: str,
    profile_cfg: Dict,
    alpha_p: float,
    target_holdings: int,
    candidate_pool_size: int,
    sector: Optional[str],
    parameter_group_order: List[str],
) -> List[Dict]:
    """Construye grupos de parámetros para display."""
    groups = {name: [] for name in parameter_group_order}
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
                "key": "gamma",
                "label": "Gamma (aversion al riesgo)",
                "value": profile_cfg.get("gamma"),
                "value_display": str(profile_cfg.get("gamma", "—")),
                "unit": "",
                "meaning": "Coeficiente de aversion al riesgo en la utilidad cuadratica mu'w - 0.5*gamma*w'Sigma*w.",
                "report_reference": "Informe 1 / solver academico",
            },
            {
                "key": "max_weight",
                "label": "Peso maximo por activo",
                "value": profile_cfg.get("max_weight"),
                "value_display": f"{round(profile_cfg.get('max_weight', 0.0) * 100)}%",
                "unit": "%",
                "meaning": "Limite superior de peso por accion impuesto por el perfil de riesgo.",
                "report_reference": "Informe 1 / solver academico",
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
        from .helpers import format_parameter_value
        groups[definition["group"]].append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "value": raw_value,
                "value_display": format_parameter_value(raw_value, definition["unit"]),
                "unit": definition["unit"],
                "meaning": definition["meaning"],
                "report_reference": definition["report_reference"],
            }
        )

    return [
        {"group": group, "items": groups[group]}
        for group in parameter_group_order
        if groups[group]
    ]


def build_methodology_payload(
    methodology: Dict,
    methodology_id: str,
    estimation_info: Dict,
    parameters_used: List[Dict],
    solver_details: Optional[Dict],
) -> Dict:
    """Construye payload de metodología para response."""
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
