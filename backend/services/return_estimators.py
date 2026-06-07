"""
return_estimators.py — Modelos de estimación de retornos esperados
"""
from typing import Dict, Sequence, Tuple

import numpy as np
from fastapi import HTTPException

from ..utils.helpers import normalize_numeric, zscore


def historical_ann_returns(tickers: Sequence[str], metadata: Dict[str, Dict], returns_matrix: np.ndarray) -> np.ndarray:
    """Retornos anualizados desde CAGR histórico con fallback a media."""
    annualized_mean = returns_matrix.mean(axis=0) * 252
    values = []
    for idx, ticker in enumerate(tickers):
        cagr = metadata.get(ticker, {}).get("cagr")
        values.append(float(cagr) if cagr is not None else float(annualized_mean[idx]))
    return np.array(values, dtype=float)


def capm_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    """Estima retornos usando CAPM."""
    risk_free_rate = (normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    market_return = (normalize_numeric(parameter_values.get("market_return_pct"), 10.0) or 10.0) / 100.0
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


def size_loadings(tickers: Sequence[str], metadata: Dict[str, Dict]) -> np.ndarray:
    """Loadings de tamaño aproximados con market cap."""
    market_caps = np.array(
        [max(float(metadata.get(ticker, {}).get("market_cap") or 1.0), 1.0) for ticker in tickers],
        dtype=float,
    )
    return zscore(-np.log(market_caps))


def value_loadings(tickers: Sequence[str], metadata: Dict[str, Dict]) -> np.ndarray:
    """Loadings de valor aproximados con dividend yield y trailing PE."""
    dividend_yields = []
    earnings_yields = []
    for ticker in tickers:
        meta = metadata.get(ticker, {})
        dividend_yields.append(float(meta.get("dividend_yield") or 0.0))
        trailing_pe = float(meta.get("trailing_pe") or 0.0)
        earnings_yields.append(0.0 if trailing_pe <= 0 else 1.0 / trailing_pe)
    dividend_score = zscore(np.array(dividend_yields, dtype=float))
    earnings_score = zscore(np.array(earnings_yields, dtype=float))
    return (dividend_score + earnings_score) / 2.0


def fama_french_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    """Estima retornos usando Fama-French aproximado (SMB + HML)."""
    risk_free_rate = (normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    market_return = (normalize_numeric(parameter_values.get("market_return_pct"), 10.0) or 10.0) / 100.0
    smb_premium = (normalize_numeric(parameter_values.get("smb_premium_pct"), 2.0) or 2.0) / 100.0
    hml_premium = (normalize_numeric(parameter_values.get("hml_premium_pct"), 1.5) or 1.5) / 100.0
    market_premium = market_return - risk_free_rate

    size_load = size_loadings(tickers, metadata)
    value_load = value_loadings(tickers, metadata)
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


def black_litterman_ann_returns(
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    """Estima retornos usando Black-Litterman."""
    risk_free_rate = (normalize_numeric(parameter_values.get("risk_free_rate_pct"), 5.0) or 5.0) / 100.0
    lambda_risk = normalize_numeric(parameter_values.get("lambda_risk_aversion"), 2.5) or 2.5
    tau = normalize_numeric(parameter_values.get("tau"), 0.05) or 0.05
    omega_diag = normalize_numeric(parameter_values.get("omega_diag"), 0.05) or 0.05

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

    from ..routers.portfolio import _parse_views_json
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


def estimate_returns(
    methodology_id: str,
    tickers: Sequence[str],
    metadata: Dict[str, Dict],
    returns_matrix: np.ndarray,
    parameter_values: Dict[str, object],
) -> Tuple[np.ndarray, Dict]:
    """Router para seleccionar el modelo de estimación de retornos."""
    hist = historical_ann_returns(tickers, metadata, returns_matrix)
    if methodology_id in {"markowitz_media_varianza", "minima_varianza_global", "maximo_retorno", "equiponderado"}:
        return hist, {
            "estimation_model": "Historico",
            "historical_source": "CAGR local con fallback a media anualizada del periodo de calibracion.",
        }
    if methodology_id == "capm_markowitz":
        return capm_ann_returns(tickers, metadata, parameter_values)
    if methodology_id == "fama_french_markowitz":
        return fama_french_ann_returns(tickers, metadata, parameter_values)
    if methodology_id in {"black_litterman_markowitz", "finpuc_hibrido"}:
        return black_litterman_ann_returns(tickers, metadata, returns_matrix, parameter_values)
    raise HTTPException(status_code=400, detail="Metodologia no soportada.")
