"""
history.py — Lectura de CSVs históricos de precios.

Cada CSV tiene columnas: Date, Open, High, Low, Close, Volume, Dividends, Stock Splits
La columna Date tiene timezone: "1980-12-12 00:00:00-05:00"
"""
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def load_stock_csv(ticker: str, data_dir: Path) -> Optional[pd.DataFrame]:
    """
    Lee el CSV de un ticker y retorna un DataFrame normalizado con columnas:
        date (str YYYY-MM-DD), close (float), volume (int), dividends (float)

    Retorna None si el archivo no existe o está vacío.
    """
    csv_path = data_dir / f"stock_return_{ticker}.csv"
    if not csv_path.exists():
        log.debug("CSV no encontrado: %s", csv_path)
        return None

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        log.warning("Error leyendo %s: %s", csv_path, e)
        return None

    if df.empty or "Close" not in df.columns:
        return None

    # Normalizar fechas: "2023-01-03 00:00:00-05:00" → "2023-01-03"
    try:
        df["date"] = pd.to_datetime(df["Date"], utc=True).dt.date.astype(str)
    except Exception as e:
        log.warning("Error parseando fechas en %s: %s", ticker, e)
        return None

    # Seleccionar y limpiar columnas relevantes
    out = pd.DataFrame({
        "date":      df["date"],
        "close":     pd.to_numeric(df["Close"],     errors="coerce"),
        "volume":    pd.to_numeric(df["Volume"],    errors="coerce").fillna(0).astype(int),
        "dividends": pd.to_numeric(df["Dividends"], errors="coerce").fillna(0.0),
    })

    # Eliminar filas sin precio de cierre
    out = out.dropna(subset=["close"])
    out = out.sort_values("date").reset_index(drop=True)

    return out if not out.empty else None


def compute_stats(df: pd.DataFrame) -> dict:
    """
    Calcula CAGR y volatilidad anualizada sobre el DataFrame de precios.
    Retorna {"cagr": float|None, "ann_volatility": float|None}.
    """
    if df is None or len(df) < 10:
        return {"cagr": None, "ann_volatility": None}

    closes = df["close"].values
    n = len(closes)

    # CAGR
    try:
        cagr = float((closes[-1] / closes[0]) ** (252.0 / n) - 1)
    except Exception:
        cagr = None

    # Volatilidad anualizada (log-returns)
    try:
        import numpy as np
        log_rets = np.log(closes[1:] / closes[:-1])
        ann_vol = float(log_rets.std() * (252 ** 0.5))
    except Exception:
        ann_vol = None

    return {"cagr": cagr, "ann_volatility": ann_vol}
