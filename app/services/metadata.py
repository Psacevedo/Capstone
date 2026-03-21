"""
metadata.py — Parseo de stocks_info.txt.

Formato de cada línea:
    TICKER;{python_dict_con_metadatos}

Uso:
    from app.services.metadata import load_all_metadata
    meta = load_all_metadata()   # dict {ticker: {sector, industry, marketCap, ...}}
"""
import ast
import logging
from pathlib import Path
from typing import Dict, Any

log = logging.getLogger(__name__)

# Campos que nos interesan extraer del dict crudo de Yahoo Finance
_FIELDS = [
    ("short_name",          ["shortName"]),
    ("long_name",           ["longName"]),
    ("sector",              ["sector", "sectorDisp"]),
    ("industry",            ["industry", "industryDisp"]),
    ("market_cap",          ["marketCap"]),
    ("beta",                ["beta"]),
    ("trailing_pe",         ["trailingPE"]),
    ("dividend_yield",      ["dividendYield"]),
    ("week52_low",          ["fiftyTwoWeekLow"]),
    ("week52_high",         ["fiftyTwoWeekHigh"]),
    ("current_price",       ["currentPrice", "regularMarketPrice"]),
    ("full_time_employees", ["fullTimeEmployees"]),
    ("summary",             ["longBusinessSummary"]),
    ("quote_type",          ["quoteType"]),
]


def _extract(raw: dict, keys: list):
    for k in keys:
        v = raw.get(k)
        if v is not None:
            return v
    return None


def parse_stocks_info(info_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    Lee stocks_info.txt y retorna un dict {ticker: {campo: valor}}.
    Líneas mal formadas se omiten con un warning.
    """
    result: Dict[str, Dict[str, Any]] = {}

    with open(info_file, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue

            sep = line.find(";")
            if sep == -1:
                log.warning("Línea %d sin separador ';': omitida", lineno)
                continue

            ticker = line[:sep].strip().upper()
            raw_str = line[sep + 1:].strip()

            try:
                raw = ast.literal_eval(raw_str)
            except Exception:
                log.warning("Línea %d [%s]: dict inválido, omitida", lineno, ticker)
                continue

            if not isinstance(raw, dict):
                continue

            record: Dict[str, Any] = {"ticker": ticker}
            for dest_key, src_keys in _FIELDS:
                record[dest_key] = _extract(raw, src_keys)

            result[ticker] = record

    log.info("metadata: %d tickers cargados desde %s", len(result), info_file)
    return result


def load_all_metadata(info_file: Path) -> Dict[str, Dict[str, Any]]:
    return parse_stocks_info(info_file)
