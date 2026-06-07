"""
universe_f5.py - Definicion operativa del universo de acciones.

Centraliza las restricciones usadas para:
- Explorer "Universo de acciones" (sectores, busqueda, fichas).
- Seleccion de candidatos del recomendador (router portfolio).
"""

from typing import Dict, List, Tuple

F5_MIN_HISTORY_ROWS = 2520   # ~10 anos
F5_MIN_PRICE = 5.0           # USD
F5_MIN_MARKET_CAP = 2_000_000_000  # $2B
F5_VOL_MIN = 0.05            # 5% anual
F5_VOL_MAX = 1.0             # 100% anual


def f5_base_clauses() -> Tuple[List[str], List]:
    clauses = [
        "cagr IS NOT NULL",
        "ann_volatility IS NOT NULL",
        "current_price IS NOT NULL",
        "market_cap IS NOT NULL",
        "n_rows >= ?",
        "current_price >= ?",
        "market_cap >= ?",
        "ann_volatility BETWEEN ? AND ?",
        "COALESCE(sector, '') <> 'Unknown'",
        "COALESCE(industry, '') <> 'Shell Companies'",
    ]
    params: List = [
        F5_MIN_HISTORY_ROWS,
        F5_MIN_PRICE,
        F5_MIN_MARKET_CAP,
        F5_VOL_MIN,
        F5_VOL_MAX,
    ]
    return clauses, params


def f5_base_where_sql() -> Tuple[str, List]:
    clauses, params = f5_base_clauses()
    return " AND ".join(clauses), params


def get_universe_definition() -> Dict:
    """Retorna la definicion completa del universo de acciones con filtros y supuestos."""
    return {
        "name": "Universo de acciones",
        "description": (
            "Universo operativo de acciones del mercado estadounidense, "
            "filtrado secuencialmente para garantizar liquidez, estabilidad "
            "y representatividad estadistica."
        ),
        "filters": {
            "title": "Cascada de filtrado (F0 -> F5)",
            "source": "Seccion 2.5 / Anexo N2",
            "stages": [
                {
                    "id": "F0",
                    "name": "Universo crudo",
                    "criterion": "Archivos CSV encontrados en Data/Historical_Stocks/",
                    "tickers": 1406,
                    "retention_pct": 100.0,
                },
                {
                    "id": "F1",
                    "name": "Liquidez basica",
                    "criterion": "Precio >= $5 USD, historia >= 5 anos (~1250 filas), market cap >= $300M o sin dato",
                    "tickers": 827,
                    "retention_pct": 58.8,
                },
                {
                    "id": "F2",
                    "name": "Calidad de clasificacion",
                    "criterion": "Excluye Shell Companies, sector Unknown. Solo instrumentos EQUITY.",
                    "tickers": 824,
                    "retention_pct": 58.6,
                },
                {
                    "id": "F3",
                    "name": "Large/Mega cap",
                    "criterion": "Capitalizacion bursatil >= $2B USD",
                    "tickers": 659,
                    "retention_pct": 46.9,
                },
                {
                    "id": "F4",
                    "name": "Historia suficiente",
                    "criterion": "Historia >= 10 anos (~2500 filas) fuera de pandemia",
                    "tickers": 606,
                    "retention_pct": 43.1,
                },
                {
                    "id": "F5",
                    "name": "Volatilidad razonable",
                    "criterion": "Volatilidad anualizada entre 5% y 100%",
                    "tickers": 601,
                    "retention_pct": 42.7,
                },
            ],
        },
        "current_criteria": {
            "title": "Criterios operativos actuales (webapp)",
            "min_history_rows": F5_MIN_HISTORY_ROWS,
            "min_history_years": 10,
            "min_price_usd": F5_MIN_PRICE,
            "min_market_cap_usd": F5_MIN_MARKET_CAP,
            "volatility_range_pct": [int(F5_VOL_MIN * 100), int(F5_VOL_MAX * 100)],
            "exclude_unknown_sector": True,
            "exclude_shell_companies": True,
        },
        "assumptions": {
            "title": "Supuestos del universo operativo",
            "items": [
                {
                    "label": "Datos y fuente",
                    "detail": (
                        "Los precios de cierre y dividendos provienen de Yahoo Finance via yfinance. "
                        "Se asume que representan adecuadamente la informacion disponible para cada activo. "
                        "La metadata de capitalizacion de mercado es suficiente para construir el benchmark "
                        "y los pesos de equilibrio de Black-Litterman."
                    ),
                    "report_reference": "Anexo N2 / Seccion 2.5",
                },
                {
                    "label": "Sesgo de supervivencia",
                    "detail": (
                        "Exigir historia >= 10 anos y alta capitalizacion puede introducir sesgo de supervivencia. "
                        "Las empresas que quebraron o fueron adquiridas antes de 2016 no estan en el universo. "
                        "Se mitiga parcialmente usando el escenario con pandemia (2020-2022) como prueba de estres."
                    ),
                    "report_reference": "Seccion 2.5 / Anexo N2",
                },
                {
                    "label": "Sobrerrepresentacion sectorial",
                    "detail": (
                        "Financial Services representa el 37% del universo final debido a la alta presencia "
                        "de bancos regionales y gestores de activos en el mercado estadounidense. "
                        "El filtro F3 (market cap >= $2B) reduce este sesgo pero no lo elimina."
                    ),
                    "report_reference": "Anexo N2 / Tabla 0.3",
                },
                {
                    "label": "Tratamiento de pandemia (2020-2022)",
                    "detail": (
                        "Se construyen dos escenarios comparables: sin pandemia (excluye 2020-2022 del entrenamiento) "
                        "y con pandemia (conserva 2020-2022). El periodo futuro de evaluacion se mantiene fijo "
                        "(2024-01-29 a 2026-01-30). Las diferencias se interpretan como efecto de la informacion "
                        "usada para calibrar, no como cambios en el mercado futuro."
                    ),
                    "report_reference": "Seccion 2.5 / Anexo N2",
                },
                {
                    "label": "Retornos y matriz de covarianza",
                    "detail": (
                        "La matriz de retornos se construye con join='inner', asumiendo que eliminar fechas "
                        "no comunes no introduce sesgo relevante. Para estabilizar la covarianza muestral se "
                        "aplica shrinkage de 20%. La anualizacion considera 252 dias habiles. "
                        "El retorno diario total incorpora dividendos: r_t = (P_t - P_{t-1} + D_t) / P_{t-1}."
                    ),
                    "report_reference": "Seccion 3 / Supuestos",
                },
                {
                    "label": "Restricciones operativas",
                    "detail": (
                        "Carteras long-only (w_i >= 0, sum(w) = 1). Sin apalancamiento. "
                        "Peso maximo por activo segun perfil (5% a 20%). "
                        "Time budget para optimizacion: 10 segundos. "
                        "La optimizacion omite costos de transaccion, impuestos y slippage; "
                        "en Monte Carlo se aproximan con comision k = 1% sobre transacciones."
                    ),
                    "report_reference": "Seccion 2.4 / Seccion 4",
                },
            ],
        },
        "sectors": [
            "Technology", "Financial Services", "Industrials", "Healthcare",
            "Consumer Cyclical", "Consumer Defensive", "Real Estate",
            "Utilities", "Energy", "Basic Materials", "Communication Services",
        ],
    }
