"""
config.py — Configuración centralizada de la webapp P4.
"""
import os
from pathlib import Path

DATA_DIR  = Path(os.getenv("DATA_DIR",  "/data/Historical_Stocks"))
DB_PATH   = Path(os.getenv("DB_PATH",   "/data/webapp_cache.db"))
INFO_FILE = DATA_DIR / "stocks_info.txt"

SECTORS = [
    "Technology",
    "Financial Services",
    "Industrials",
    "Healthcare",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Real Estate",
    "Utilities",
    "Energy",
    "Basic Materials",
    "Communication Services",
]
