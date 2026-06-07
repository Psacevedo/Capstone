"""
bl_views.py - Construccion de views Black-Litterman predefinidas (Entrega 2).

Implementa los 4 tipos de views del notebook black_litterman.ipynb:
- momentum: long top-20 / short bottom-20 por retorno historico 1Y
- desempleo: macro view asumida (cyclical vs defensive)
- momentum_top20_6m: top-20 market cap, long 10 / short 10 por momentum 6M
- momentum_top20_bottom20_1y: top-40 market cap, long 20 / short 20 por momentum 1Y
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

TRADING_DAYS_PER_YEAR = 252

# Sectores ciclicos y defensivos para la view de desempleo
CYCLICAL_SECTORS = [
    "Technology", "Consumer Cyclical", "Industrials",
    "Financial Services", "Basic Materials", "Real Estate", "Energy",
]
DEFENSIVE_SECTORS = [
    "Healthcare", "Consumer Defensive", "Utilities", "Communication Services",
]

# Parametros por tipo de view (misma nomenclatura que los notebooks)
VIEW_CONFIGS = {
    "momentum": {
        "label": "Momentum (1Y, 20 long / 20 short)",
        "description": "Top-20 y bottom-20 por retorno acumulado en 252 dias. Opera sobre el universo completo.",
        "confidence": 0.50,
        "lookback": 252,
        "top_bottom": 20,
    },
    "desempleo": {
        "label": "Desempleo (macro asumida)",
        "description": (
            "View macro: asume tasa de desempleo 4% bajo el neutro 5%, "
            "favorece sectores ciclicos sobre defensivos."
        ),
        "confidence": 0.35,
        "unemployment_rate": 0.04,
        "unemployment_neutral": 0.05,
        "macro_beta": 1.0,
    },
    "momentum_top20_6m": {
        "label": "Momentum Top20 6M (10 long / 10 short)",
        "description": "Top-20 por market cap, long 10 / short 10 por momentum semestral (126d).",
        "confidence": 0.50,
        "lookback": 126,
        "top_bottom": 10,
        "market_cap_size": 20,
    },
    "momentum_top20_bottom20_1y": {
        "label": "Momentum Top40 1Y (20 long / 20 short)",
        "description": "Top-40 por market cap, long 20 / short 20 por momentum anual (252d).",
        "confidence": 0.50,
        "lookback": 252,
        "top_bottom": 20,
        "market_cap_size": 40,
    },
}


def _momentum_scores(
    tickers: List[str],
    returns_matrix: np.ndarray,
    lookback: int,
) -> np.ndarray:
    """Retorna el retorno acumulado en los ultimos 'lookback' dias para cada ticker."""
    recent = returns_matrix[-lookback:, :] if returns_matrix.shape[0] >= lookback else returns_matrix
    return recent.mean(axis=0) * lookback  # retorno acumulado aproximado


def build_momentum_view(
    tickers: List[str],
    returns_matrix: np.ndarray,
    config: Dict,
) -> Tuple[np.ndarray, np.ndarray, float, Dict]:
    """Construye view de momentum: long top-N / short bottom-N."""
    n_top = config["top_bottom"]
    lookback = config["lookback"]
    confidence = config["confidence"]
    scores = _momentum_scores(tickers, returns_matrix, lookback)
    n = len(tickers)
    ranked = np.argsort(scores)
    bottom_idx = ranked[:n_top]
    top_idx = ranked[-n_top:]

    p_row = np.zeros(n, dtype=float)
    p_row[top_idx] = 1.0 / n_top
    p_row[bottom_idx] = -1.0 / n_top
    q_value = float(np.mean(scores[top_idx]) - np.mean(scores[bottom_idx]))

    return p_row.reshape(1, -1), np.array([q_value]), confidence, {
        "view_type": "momentum",
        "lookback": lookback,
        "n_long": int(len(top_idx)),
        "n_short": int(len(bottom_idx)),
        "q_value": round(q_value, 6),
        "confidence": confidence,
    }


def build_desempleo_view(
    tickers: List[str],
    metadata: Dict[str, Dict],
    config: Dict,
) -> Tuple[np.ndarray, np.ndarray, float, Dict]:
    """Construye view de desempleo: long cyclical / short defensive."""
    confidence = config["confidence"]
    signal = config["unemployment_neutral"] - config["unemployment_rate"]
    q_value = abs(signal) * config["macro_beta"] / TRADING_DAYS_PER_YEAR

    cyclical_idx = []
    defensive_idx = []
    for idx, ticker in enumerate(tickers):
        sector = metadata.get(ticker, {}).get("sector", "")
        if sector in CYCLICAL_SECTORS:
            cyclical_idx.append(idx)
        elif sector in DEFENSIVE_SECTORS:
            defensive_idx.append(idx)

    if not cyclical_idx or not defensive_idx:
        vols = [_momentum_scores(tickers, returns_matrix=None, lookback=252)]  # fallback
        raise ValueError(
            "No se encontraron tickers ciclicos o defensivos para la view de desempleo. "
            "Verifica los sectores en el universo."
        )

    n = len(tickers)
    p_row = np.zeros(n, dtype=float)
    p_row[cyclical_idx] = 1.0 / len(cyclical_idx)
    p_row[defensive_idx] = -1.0 / len(defensive_idx)

    return p_row.reshape(1, -1), np.array([q_value]), confidence, {
        "view_type": "desempleo",
        "signal": round(signal, 6),
        "q_value": round(q_value, 6),
        "confidence": confidence,
        "n_cyclical": len(cyclical_idx),
        "n_defensive": len(defensive_idx),
    }


def build_marketcap_momentum_view(
    tickers: List[str],
    returns_matrix: np.ndarray,
    metadata: Dict[str, Dict],
    config: Dict,
) -> Tuple[np.ndarray, np.ndarray, float, Dict]:
    """Construye view de momentum restringida por market cap."""
    n_top = config["top_bottom"]
    lookback = config["lookback"]
    confidence = config["confidence"]
    cap_size = config["market_cap_size"]

    market_caps = np.array([
        float(metadata.get(t, {}).get("market_cap") or 0.0) for t in tickers
    ])
    top_cap_idx = np.argsort(market_caps)[-cap_size:]
    if len(top_cap_idx) < n_top * 2:
        top_cap_idx = np.argsort(market_caps)[-(n_top * 2):]

    selected_tickers = [tickers[i] for i in top_cap_idx]
    sub_returns = returns_matrix[:, top_cap_idx]
    scores = _momentum_scores(selected_tickers, sub_returns, lookback)
    ranked = np.argsort(scores)
    bottom_local = ranked[:n_top]
    top_local = ranked[-n_top:]

    n = len(tickers)
    p_row = np.zeros(n, dtype=float)
    p_row[top_cap_idx[top_local]] = 1.0 / n_top
    p_row[top_cap_idx[bottom_local]] = -1.0 / n_top
    q_value = float(np.mean(scores[top_local]) - np.mean(scores[bottom_local]))

    return p_row.reshape(1, -1), np.array([q_value]), confidence, {
        "view_type": config.get("view_type", "marketcap_momentum"),
        "lookback": lookback,
        "market_cap_size": cap_size,
        "n_long": n_top,
        "n_short": n_top,
        "q_value": round(q_value, 6),
        "confidence": confidence,
    }


def build_bl_view(
    view_type: str,
    tickers: List[str],
    returns_matrix: np.ndarray,
    metadata: Dict[str, Dict],
) -> Tuple[np.ndarray, np.ndarray, float, Dict]:
    """Construye P, Q, confidence y metadata para una view predefinida.

    Returns:
        P: matriz (1, n) con pesos long/short
        Q: array (1,) con el valor esperado de la view
        confidence: escalar en (0,1]
        info: dict con metadata de la view construida
    """
    config = VIEW_CONFIGS.get(view_type)
    if config is None:
        raise ValueError(
            f"View type '{view_type}' no reconocido. "
            f"Opciones: {list(VIEW_CONFIGS.keys())}"
        )

    if view_type == "momentum":
        return build_momentum_view(tickers, returns_matrix, config)
    elif view_type == "desempleo":
        return build_desempleo_view(tickers, metadata, config)
    elif view_type == "momentum_top20_6m":
        return build_marketcap_momentum_view(tickers, returns_matrix, metadata, {
            **config, "view_type": view_type,
        })
    elif view_type == "momentum_top20_bottom20_1y":
        return build_marketcap_momentum_view(tickers, returns_matrix, metadata, {
            **config, "view_type": view_type,
        })
    else:
        raise ValueError(f"View type no implementado: {view_type}")
