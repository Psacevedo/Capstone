"""
black_litterman_views.py
========================
Generación automática de la matriz de views P y el vector Q para el modelo
Black-Litterman, usando la señal de momentum 12-1 como fuente sistemática
de información cuantitativa.

Diseño del módulo
-----------------
El módulo expone cuatro capas de uso:

  1. Capa de cómputo (webapp y notebooks):
       generate_momentum_views(tickers, daily_returns, mu_historical, ann_cov, ...)
           → (P, Q, Omega, views_used)
       compute_bl_posterior(tickers, ann_cov, market_caps, P, Q, Omega, ...)
           → (mu_BL, pi_prior, info_dict)

  2. Capa de optimización (notebooks):
       markowitz_with_bl(mu_bl, ann_cov, tickers, gamma, max_weight)
           → (weights, tickers)

  3. Capa de carga (notebooks standalone):
       load_artifacts(outputs_dir)
           → dict con mu, sigma, daily_returns, weekly_returns, estimation_returns

  4. Pipeline completa (notebooks):
       run_full_pipeline(top_k, bottom_k, ...)
           → (mu_BL, pi_prior, views_used, info)

Importación desde la webapp
---------------------------
    from solver.black_litterman_views import generate_momentum_views, compute_bl_posterior

Importación desde notebooks
----------------------------
    from black_litterman_views import load_artifacts, run_full_pipeline
    # o bien desde la raíz del proyecto:
    import sys; sys.path.insert(0, ".")
    from solver.black_litterman_views import ...

Supuestos del modelo
--------------------
S1. VIEWS ABSOLUTAS
    Cada fila de P selecciona exactamente un activo (sub-identidad).
    No se generan views relativas ("A supera a B en X%") en este módulo.

S2. SEÑAL DE MOMENTUM 12-1
    La señal se calcula como el retorno acumulado de los últimos
    MOMENTUM_WINDOW_DAYS días de trading (≈ 12 meses), excluyendo
    los últimos SKIP_DAYS días (≈ 1 mes) para evitar el efecto reversal
    de corto plazo documentado en Jegadeesh & Titman (1993).
    Fórmula:  signal_i = ∏(1 + r_{t,i}) − 1  para t en [T-skip-window, T-skip]

S3. CALIBRACIÓN DE Q (VECTOR DE VIEWS)
    El valor esperado de cada view se escala desde mu_historical:
      - Ganadores (momentum alto):  Q_k = mu_hist_k × SCALE_WINNERS (default 1.10)
      - Perdedores (momentum bajo):  Q_k = mu_hist_k × SCALE_LOSERS  (default 0.50)
    Q se recorta al rango [Q_MIN, Q_MAX] = [-0.40, +0.80] para evitar
    views extremas que dominen la prior de equilibrio.

S4. CALIBRACIÓN DE OMEGA (HE & LITTERMAN 1999)
    Si se provee ann_cov, la incertidumbre de cada view se calibra como:
        Omega_kk = tau × P_k Σ P_k^T
    Esta calibración proporcional garantiza que Omega sea coherente con
    la escala de la covarianza del portafolio de la view.
    Si ann_cov no se provee, se usa omega_diag_fallback como valor plano.

S5. PRIOR DE EQUILIBRIO DE MERCADO (BLACK & LITTERMAN 1990)
    π = r_f + λ × Σ w_mkt
    donde w_mkt = market_caps / Σ market_caps (pesos por capitalización).
    Se asume que el mercado está en equilibrio CAPM antes de incorporar views.

S6. SIN TASA LIBRE DE RIESGO EN MARKOWITZ FINAL
    El paso de optimización (markowitz_with_bl) maximiza la utilidad
    cuadrática directamente, sin descontar r_f. Consistente con el
    solver académico del proyecto (markowitz_pipeline.py).

S7. SIN RESTRICCIONES DE SECTOR EN ESTE MÓDULO
    Las restricciones de concentración sectorial se aplican en la capa
    de sub-universos (markowitz_pipeline.py / universe_f5.py), no aquí.

Referencias
-----------
- Black, F. & Litterman, R. (1990). Asset Allocation: Combining Investor
  Views with Market Equilibrium. Goldman Sachs Fixed Income Research.
- He, G. & Litterman, R. (1999). The Intuition Behind Black-Litterman
  Model Portfolios. Goldman Sachs Investment Management Research.
- Jegadeesh, N. & Titman, S. (1993). Returns to Buying Winners and Selling
  Losers. Journal of Finance, 48(1), 65–91.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


# ---------------------------------------------------------------------------
# Constantes del módulo
# ---------------------------------------------------------------------------

MOMENTUM_WINDOW_DAYS: int = 252   # ≈ 12 meses de trading (supuesto S2)
SKIP_DAYS: int = 21               # ≈ 1 mes excluido por reversal (supuesto S2)
SCALE_WINNERS: float = 1.10       # view ganador = mu_hist × 1.10 (supuesto S3)
SCALE_LOSERS: float = 0.50        # view perdedor = mu_hist × 0.50 (supuesto S3)
Q_MIN: float = -0.40              # clip inferior de Q  (supuesto S3)
Q_MAX: float = 0.80               # clip superior de Q  (supuesto S3)
DEFAULT_TOP_K: int = 20           # ganadores con view por defecto
DEFAULT_BOTTOM_K: int = 20        # perdedores con view por defecto
TRADING_DAYS_PER_YEAR: int = 252


# ---------------------------------------------------------------------------
# Señal de momentum
# ---------------------------------------------------------------------------

def _compute_momentum_signal(
    daily_returns: np.ndarray,
    window_days: int = MOMENTUM_WINDOW_DAYS,
    skip_days: int = SKIP_DAYS,
) -> np.ndarray:
    """
    Retorno acumulado 12-1 para cada activo (supuesto S2).

    Parámetros
    ----------
    daily_returns : array (T, N) de retornos diarios.
    window_days   : longitud de la ventana de momentum en días (default 252).
    skip_days     : días a excluir al final para evitar reversal (default 21).

    Retorna
    -------
    Array (N,) con el retorno acumulado de cada activo en la ventana 12-1.
    """
    T = daily_returns.shape[0]
    end_idx = max(T - skip_days, 1)
    start_idx = max(end_idx - window_days, 0)
    window = daily_returns[start_idx:end_idx, :]
    return np.prod(1.0 + window, axis=0) - 1.0


# ---------------------------------------------------------------------------
# Generación de views
# ---------------------------------------------------------------------------

def generate_momentum_views(
    tickers: Sequence[str],
    daily_returns: np.ndarray,
    mu_historical: np.ndarray,
    ann_cov: Optional[np.ndarray] = None,
    tau: float = 0.05,
    top_k: int = DEFAULT_TOP_K,
    bottom_k: int = DEFAULT_BOTTOM_K,
    momentum_window_days: int = MOMENTUM_WINDOW_DAYS,
    skip_days: int = SKIP_DAYS,
    scale_winners: float = SCALE_WINNERS,
    scale_losers: float = SCALE_LOSERS,
    omega_diag_fallback: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Dict]]:
    """
    Genera P (K×N), Q (K,), Omega (K×K) y metadata para Black-Litterman.

    La señal de momentum 12-1 identifica los ``top_k`` activos con mayor
    retorno acumulado (ganadores) y los ``bottom_k`` con menor retorno
    (perdedores). A cada grupo se le asigna una view absoluta escalada
    desde ``mu_historical`` (supuestos S2 y S3).

    La incertidumbre de cada view se calibra como Omega_kk = tau × P_k Σ P_k^T
    si se provee ``ann_cov`` (supuesto S4), o bien con ``omega_diag_fallback``
    si no.

    Parámetros
    ----------
    tickers             : lista de N tickers, en el mismo orden que las
                          columnas de daily_returns y mu_historical.
    daily_returns       : array (T, N) de retornos diarios.
    mu_historical       : array (N,) de retornos anualizados históricos.
    ann_cov             : array (N, N) de covarianza anualizada; opcional.
                          Si se provee, se usa para calibrar Omega (S4).
    tau                 : escala de incertidumbre de la prior (default 0.05).
    top_k               : número de ganadores con view positiva (default 20).
    bottom_k            : número de perdedores con view negativa (default 20).
    momentum_window_days: ventana de momentum en días (default 252).
    skip_days           : días excluidos al final por reversal (default 21).
    scale_winners       : factor multiplicativo sobre mu_hist para ganadores.
    scale_losers        : factor multiplicativo sobre mu_hist para perdedores.
    omega_diag_fallback : valor plano de Omega cuando ann_cov no se provee.

    Retorna
    -------
    p_matrix   : array (K, N) — matriz de selección de activos.
    q_vector   : array (K,)   — retornos anualizados esperados por view.
    omega      : array (K, K) — matriz diagonal de incertidumbre.
    views_used : lista de K dicts con metadata de cada view.
    """
    tickers_list = list(tickers)
    N = len(tickers_list)

    # Limitar top_k / bottom_k a la mitad del universo para evitar overlap
    top_k = max(1, min(top_k, N // 2))
    bottom_k = max(1, min(bottom_k, N // 2))

    # 1. Señal de momentum
    momentum = _compute_momentum_signal(daily_returns, momentum_window_days, skip_days)
    momentum_series = pd.Series(momentum, index=tickers_list)

    # 2. Selección de activos
    winners = momentum_series.nlargest(top_k).index.tolist()
    losers = momentum_series.nsmallest(bottom_k).index.tolist()

    # 3. Construcción de P y Q
    p_rows: List[np.ndarray] = []
    q_vals: List[float] = []
    views_used: List[Dict] = []

    for ticker in winners:
        idx = tickers_list.index(ticker)
        row = np.zeros(N, dtype=float)
        row[idx] = 1.0
        q_raw = float(mu_historical[idx]) * scale_winners
        q_clip = float(np.clip(q_raw, Q_MIN, Q_MAX))
        p_rows.append(row)
        q_vals.append(q_clip)
        views_used.append({
            "ticker": ticker,
            "tipo": "ganador",
            "momentum_12_1_pct": round(float(momentum_series[ticker]) * 100, 2),
            "view_return_pct": round(q_clip * 100, 2),
            "mu_hist_pct": round(float(mu_historical[idx]) * 100, 2),
        })

    for ticker in losers:
        idx = tickers_list.index(ticker)
        row = np.zeros(N, dtype=float)
        row[idx] = 1.0
        q_raw = float(mu_historical[idx]) * scale_losers
        q_clip = float(np.clip(q_raw, Q_MIN, Q_MAX))
        p_rows.append(row)
        q_vals.append(q_clip)
        views_used.append({
            "ticker": ticker,
            "tipo": "perdedor",
            "momentum_12_1_pct": round(float(momentum_series[ticker]) * 100, 2),
            "view_return_pct": round(q_clip * 100, 2),
            "mu_hist_pct": round(float(mu_historical[idx]) * 100, 2),
        })

    p_matrix = np.array(p_rows, dtype=float)   # (K, N)
    q_vector = np.array(q_vals, dtype=float)    # (K,)
    K = len(q_vals)

    # 4. Calibración de Omega (He & Litterman 1999, supuesto S4)
    if ann_cov is not None:
        omega_diags = np.array([
            max(tau * float(p_matrix[k] @ ann_cov @ p_matrix[k]), 1e-8)
            for k in range(K)
        ], dtype=float)
    else:
        omega_diags = np.full(K, max(omega_diag_fallback, 1e-8), dtype=float)

    omega = np.diag(omega_diags)   # (K, K)

    return p_matrix, q_vector, omega, views_used


# ---------------------------------------------------------------------------
# Posterior Black-Litterman
# ---------------------------------------------------------------------------

def compute_bl_posterior(
    tickers: Sequence[str],
    ann_cov: np.ndarray,
    market_caps: np.ndarray,
    p_matrix: np.ndarray,
    q_vector: np.ndarray,
    omega: np.ndarray,
    risk_free: float = 0.05,
    lambda_risk: float = 2.5,
    tau: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    Aplica la fórmula bayesiana de Black-Litterman y devuelve mu_BL.

    Fórmula (He & Litterman 1999, Ecuación 4.7):
        M     = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹
        mu_BL = M [(τΣ)⁻¹ π + Pᵀ Ω⁻¹ Q]
        π     = r_f + λ Σ w_mkt   (prior de equilibrio, supuesto S5)

    Parámetros
    ----------
    tickers     : lista de N tickers.
    ann_cov     : covarianza anualizada (N×N).
    market_caps : capitalización bursátil (N,); se normaliza a pesos.
    p_matrix    : matriz de views (K×N).
    q_vector    : retornos esperados de cada view (K,).
    omega       : matriz de incertidumbre de las views (K×K diagonal).
    risk_free   : tasa libre de riesgo anualizada (default 0.05).
    lambda_risk : aversión al riesgo del mercado λ (default 2.5).
    tau         : escala de incertidumbre de la prior (default 0.05).

    Retorna
    -------
    mu_bl    : array (N,) — retornos bayesianos posteriores anualizados.
    pi_prior : array (N,) — prior de equilibrio del mercado.
    info     : dict con parámetros y diagnósticos del cálculo.
    """
    market_weights = market_caps / market_caps.sum()
    pi = risk_free + lambda_risk * (ann_cov @ market_weights)   # (N,)

    tau_sigma = tau * ann_cov
    tau_sigma_inv = np.linalg.pinv(tau_sigma)
    omega_inv = np.linalg.pinv(omega)

    M = np.linalg.pinv(
        tau_sigma_inv + p_matrix.T @ omega_inv @ p_matrix
    )
    v = tau_sigma_inv @ pi + p_matrix.T @ omega_inv @ q_vector
    mu_bl = (M @ v).astype(float)

    info = {
        "estimation_model": "Black-Litterman (momentum 12-1)",
        "risk_free": risk_free,
        "lambda_risk": lambda_risk,
        "tau": tau,
        "n_views": int(len(q_vector)),
        "pi_mean": float(np.mean(pi)),
        "mu_bl_mean": float(np.mean(mu_bl)),
        "mu_bl_vs_pi_delta": float(np.mean(mu_bl - pi)),
    }
    return mu_bl, pi, info


# ---------------------------------------------------------------------------
# Markowitz con mu_BL (para notebooks)
# ---------------------------------------------------------------------------

def markowitz_with_bl(
    mu_bl: np.ndarray,
    ann_cov: np.ndarray,
    tickers: Sequence[str],
    gamma: float = 18.0,
    max_weight: float = 0.10,
    top_n: Optional[int] = None,
) -> Tuple[np.ndarray, List[str]]:
    """
    Optimización media-varianza usando mu_BL como estimador de retornos.

    Formulación idéntica a markowitz_pipeline.py (supuesto S6):
        max  wᵀ mu_BL − ½ γ wᵀ Σ w
        s.t. Σ wᵢ = 1,   0 ≤ wᵢ ≤ max_weight

    Parámetros
    ----------
    mu_bl      : retornos BL anualizados (N,).
    ann_cov    : covarianza anualizada (N×N).
    tickers    : lista de N tickers.
    gamma      : coeficiente de aversión al riesgo (default 18 = Neutro).
    max_weight : peso máximo por activo (default 0.10 = 10%).
    top_n      : si se especifica, restringe la optimización a los top_n
                 activos por mu_BL antes de optimizar.

    Retorna
    -------
    weights : array (N,) de pesos óptimos.
    tickers : lista de N tickers en el orden de weights.
    """
    tickers_list = list(tickers)
    mu_arr = mu_bl.copy()
    cov_arr = ann_cov.copy()

    if top_n is not None and top_n < len(tickers_list):
        order = np.argsort(mu_arr)[::-1][:top_n]
        tickers_list = [tickers_list[i] for i in order]
        mu_arr = mu_arr[order]
        cov_arr = cov_arr[np.ix_(order, order)]

    N = len(tickers_list)
    w0 = np.full(N, 1.0 / N)

    def neg_utility(w: np.ndarray) -> float:
        return -(w @ mu_arr) + 0.5 * gamma * float(w @ cov_arr @ w)

    result = minimize(
        neg_utility,
        w0,
        method="SLSQP",
        bounds=[(0.0, max_weight)] * N,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
        options={"ftol": 1e-10, "maxiter": 1000, "disp": False},
    )
    return result.x, tickers_list


# ---------------------------------------------------------------------------
# Carga de artefactos pre-computados (solo para notebooks)
# ---------------------------------------------------------------------------

def load_artifacts(outputs_dir: Optional[Path] = None) -> Dict:
    """
    Carga los artefactos pre-computados del solver desde outputs/*.pkl.

    Uso exclusivo en notebooks o ejecución standalone. La webapp computa
    estos parámetros en tiempo de ejecución desde SQLite.

    Parámetros
    ----------
    outputs_dir : ruta al directorio outputs/. Si es None, se resuelve
                  automáticamente relativo a este archivo.

    Retorna
    -------
    dict con claves: mu, sigma, estimation_returns, weekly_returns, daily_returns
    """
    if outputs_dir is None:
        outputs_dir = Path(__file__).parent / "outputs"

    def _load(name: str):
        path = outputs_dir / name
        if not path.exists():
            raise FileNotFoundError(
                f"Artefacto no encontrado: {path}. "
                "Ejecuta primero 01_Preparar_Datos.ipynb y 02_Modelo_Markowitz.ipynb."
            )
        with open(path, "rb") as f:
            return pickle.load(f)

    return {
        "mu": _load("mu.pkl"),
        "sigma": _load("sigma.pkl"),
        "estimation_returns": _load("estimation_returns.pkl"),
        "weekly_returns": _load("weekly_returns.pkl"),
        "daily_returns": _load("daily_returns.pkl"),
    }


# ---------------------------------------------------------------------------
# Pipeline completa (para notebooks)
# ---------------------------------------------------------------------------

def run_full_pipeline(
    top_k: int = DEFAULT_TOP_K,
    bottom_k: int = DEFAULT_BOTTOM_K,
    risk_free: float = 0.05,
    lambda_risk: float = 2.5,
    tau: float = 0.05,
    outputs_dir: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, List[Dict], Dict]:
    """
    Pipeline completa: carga artefactos → genera views → calcula posterior BL.

    Uso en notebooks para ejecutar el modelo completo en una sola llamada.

    Retorna
    -------
    mu_bl      : array (N,) de retornos BL anualizados.
    pi_prior   : array (N,) de prior de equilibrio.
    views_used : lista de dicts con metadata de las views generadas.
    info       : dict con parámetros del cómputo.
    """
    arts = load_artifacts(outputs_dir)
    mu: pd.Series = arts["mu"]
    sigma: pd.DataFrame = arts["sigma"]
    daily_df: pd.DataFrame = arts["daily_returns"]

    tickers = mu.index.tolist()
    mu_arr = mu.values.astype(float)
    sigma_arr = sigma.loc[tickers, tickers].values.astype(float)
    daily_arr = daily_df[tickers].values.astype(float)

    # Sin market caps reales en los pkl → pesos equiponderados para la prior
    market_caps = np.ones(len(tickers), dtype=float)

    p_matrix, q_vector, omega, views_used = generate_momentum_views(
        tickers=tickers,
        daily_returns=daily_arr,
        mu_historical=mu_arr,
        ann_cov=sigma_arr,
        tau=tau,
        top_k=top_k,
        bottom_k=bottom_k,
    )

    mu_bl, pi_prior, info = compute_bl_posterior(
        tickers=tickers,
        ann_cov=sigma_arr,
        market_caps=market_caps,
        p_matrix=p_matrix,
        q_vector=q_vector,
        omega=omega,
        risk_free=risk_free,
        lambda_risk=lambda_risk,
        tau=tau,
    )
    info["views_used"] = views_used
    return mu_bl, pi_prior, views_used, info
