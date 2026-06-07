"""
db.py — Construcción y acceso a la base de datos SQLite para la webapp P4.

Schema:
    stocks  — metadata + stats pre-computados por ticker
    prices  — precios diarios (date, close, volume, dividends)

El build se ejecuta una sola vez (primer arranque). Usos posteriores
leen directamente desde la DB ya construida.
"""
import sqlite3
import logging
import os
from pathlib import Path
from typing import Generator, Optional

from .config import DATA_DIR, DB_PATH, INFO_FILE
from .services.metadata import load_all_metadata
from .services.history import load_stock_csv, compute_stats

log = logging.getLogger(__name__)

# Estado global del build (leído por /api/status)
_build_state = {"ready": False, "message": "Iniciando..."}


# ============================================================
# Schema
# ============================================================

_DDL = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker              TEXT PRIMARY KEY,
    short_name          TEXT,
    sector              TEXT,
    industry            TEXT,
    market_cap          REAL,
    beta                REAL,
    trailing_pe         REAL,
    dividend_yield      REAL,
    week52_low          REAL,
    week52_high         REAL,
    current_price       REAL,
    full_time_employees INTEGER,
    summary             TEXT,
    cagr                REAL,
    ann_volatility      REAL,
    n_rows              INTEGER
);

CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    close       REAL,
    volume      INTEGER,
    dividends   REAL,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices (ticker, date);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks (sector);
"""


# ============================================================
# Build de la DB
# ============================================================

def _db_needs_build() -> bool:
    """Retorna True si la DB no existe o está vacía."""
    if not DB_PATH.exists():
        return True
    try:
        con = sqlite3.connect(DB_PATH)
        n = con.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        con.close()
        return n == 0
    except Exception:
        return True


def build_db() -> None:
    """
    Construye la DB SQLite desde cero.
    Lee stocks_info.txt y todos los CSVs de precios.
    Lleva ~3-5 minutos en el primer arranque.
    """
    global _build_state

    log.info("=== Iniciando build de la DB SQLite ===")
    _build_state = {"ready": False, "message": "Cargando metadatos..."}

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Eliminar DB vieja si existe
    if DB_PATH.exists():
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    con.executescript(_DDL)
    con.commit()

    # 1. Cargar metadatos
    if not INFO_FILE.exists():
        _build_state = {"ready": False, "message": f"ERROR: no se encontró {INFO_FILE}"}
        log.error("INFO_FILE no encontrado: %s", INFO_FILE)
        con.close()
        return

    meta = load_all_metadata(INFO_FILE)
    _build_state = {"ready": False, "message": f"Metadatos cargados ({len(meta)} tickers). Procesando CSVs..."}
    log.info("Metadatos: %d tickers", len(meta))

    # 2. Descubrir CSVs disponibles
    csv_files = list(DATA_DIR.glob("stock_return_*.csv"))
    total = len(csv_files)
    log.info("CSVs encontrados: %d", total)

    # 3. Procesar cada CSV
    stocks_rows = []
    prices_batch = []
    BATCH_SIZE = 50_000

    for idx, csv_path in enumerate(csv_files, 1):
        ticker = csv_path.stem.replace("stock_return_", "").upper()

        if idx % 100 == 0 or idx == total:
            pct = int(idx / total * 100)
            _build_state = {
                "ready": False,
                "message": f"Procesando CSVs: {idx}/{total} ({pct}%)..."
            }
            log.info("Progreso: %d/%d tickers", idx, total)

        df = load_stock_csv(ticker, DATA_DIR)
        stats = compute_stats(df)
        m = meta.get(ticker, {})

        stocks_rows.append((
            ticker,
            m.get("short_name"),
            m.get("sector"),
            m.get("industry"),
            m.get("market_cap"),
            m.get("beta"),
            m.get("trailing_pe"),
            m.get("dividend_yield"),
            m.get("week52_low"),
            m.get("week52_high"),
            m.get("current_price"),
            m.get("full_time_employees"),
            m.get("summary"),
            stats["cagr"],
            stats["ann_volatility"],
            len(df) if df is not None else 0,
        ))

        if df is not None:
            for row in df.itertuples(index=False):
                prices_batch.append((ticker, row.date, row.close, row.volume, row.dividends))

            # Insertar en lotes para no usar demasiada RAM
            if len(prices_batch) >= BATCH_SIZE:
                con.executemany(
                    "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?)",
                    prices_batch
                )
                con.commit()
                prices_batch.clear()

    # Insertar stocks
    con.executemany(
        """INSERT OR REPLACE INTO stocks VALUES
           (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        stocks_rows
    )

    # Insertar precios restantes
    if prices_batch:
        con.executemany(
            "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?)",
            prices_batch
        )

    con.commit()
    con.close()

    n_stocks = len(stocks_rows)
    log.info("=== Build completado: %d stocks ===", n_stocks)
    _build_state = {
        "ready": True,
        "message": f"Listo. {n_stocks} acciones indexadas."
    }


def build_db_if_needed() -> None:
    """Entry point para el startup de FastAPI."""
    global _build_state
    if _db_needs_build():
        build_db()
    else:
        _build_state = {"ready": True, "message": "DB ya construida."}
        log.info("DB ya existe, saltando build.")


def get_build_state() -> dict:
    return _build_state


# ============================================================
# Conexión / dependencia FastAPI
# ============================================================

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependencia FastAPI: una conexión SQLite por request."""
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA cache_size = -32768")   # 32 MB read cache
    con.execute("PRAGMA synchronous = NORMAL")
    try:
        yield con
    finally:
        con.close()
