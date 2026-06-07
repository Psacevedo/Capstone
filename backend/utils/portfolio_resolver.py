"""
portfolio_resolver.py — Resolución y validación de parámetros de portafolio
"""
from typing import Dict, Optional, Tuple

from fastapi import HTTPException

from ..utils.helpers import normalize_numeric


TARGET_HOLDINGS_DEFAULT = 10
TARGET_HOLDINGS_MAX = 30
MIN_OPTIMIZER_UNIVERSE = 20
MAX_OPTIMIZER_UNIVERSE = 40
DEFAULT_RISK_FREE_RATE = 0.02  # 2% anual (Entrega 2)
DEFAULT_COMMISSION_RATE = 0.01


RISK_PROFILES = {
    "muy_conservador": {
        "alpha_p": 0.00,
        "label": "Muy conservador",
        "description": "No admite perdidas sobre el capital invertido.",
        "candidate_pool_default": 40,
        "candidate_pool_range": "30-50",
        "candidate_pool_max": 50,
        "max_vol": 0.08,
        "sectors": ["Utilities", "Consumer Defensive"],
        "cvar_level": 0.99,
        "dividend_bias": True,
        "gamma": 80.0,
        "max_weight": 0.05,
        "n_assets": 40,
        "max_sector_fraction": 0.30,
    },
    "conservador": {
        "alpha_p": 0.05,
        "label": "Conservador",
        "description": "Tolera perdidas minimas y privilegia estabilidad.",
        "candidate_pool_default": 65,
        "candidate_pool_range": "50-80",
        "candidate_pool_max": 80,
        "max_vol": 0.12,
        "sectors": None,
        "cvar_level": 0.95,
        "dividend_bias": True,
        "gamma": 45.0,
        "max_weight": 0.07,
        "n_assets": 60,
        "max_sector_fraction": 0.30,
    },
    "neutro": {
        "alpha_p": 0.15,
        "label": "Neutro",
        "description": "Equilibra retorno esperado y riesgo.",
        "candidate_pool_default": 100,
        "candidate_pool_range": "80-120",
        "candidate_pool_max": 120,
        "max_vol": 0.18,
        "sectors": None,
        "cvar_level": 0.90,
        "dividend_bias": False,
        "gamma": 20.0,
        "max_weight": 0.10,
        "n_assets": 80,
        "max_sector_fraction": 0.25,
    },
    "arriesgado": {
        "alpha_p": 0.30,
        "label": "Arriesgado",
        "description": "Acepta mas volatilidad para capturar crecimiento.",
        "candidate_pool_default": 125,
        "candidate_pool_range": "100-150",
        "candidate_pool_max": 150,
        "max_vol": 0.28,
        "sectors": None,
        "cvar_level": 0.85,
        "dividend_bias": False,
        "gamma": 8.0,
        "max_weight": 0.15,
        "n_assets": 100,
        "max_sector_fraction": 0.30,
    },
    "muy_arriesgado": {
        "alpha_p": 0.40,
        "label": "Muy arriesgado",
        "description": "Opera sobre el universo de acciones completo.",
        "candidate_pool_default": None,
        "candidate_pool_range": "Universo de acciones completo",
        "candidate_pool_max": None,
        "max_vol": 0.40,
        "sectors": None,
        "cvar_level": 0.80,
        "dividend_bias": False,
        "gamma": 3.0,
        "max_weight": 0.20,
        "n_assets": 120,
        "max_sector_fraction": 0.35,
    },
}

LEGACY_METHOD_MAP = {
    "markowitz": "markowitz_media_varianza",
    "simple": "maximo_retorno",
    "propio": "minima_varianza_global",
    "benchmark": "benchmark",
    "equiponderado": "equiponderado",
    "finpuc_hibrido": "markowitz_media_varianza",
    "capm_markowitz": "markowitz_media_varianza",
    "fama_french_markowitz": "markowitz_media_varianza",
}


def risk_level(max_loss_pct: float) -> str:
    """Mapea máxima pérdida a perfil de riesgo."""
    if max_loss_pct <= 0.00:
        return "muy_conservador"
    if max_loss_pct <= 0.05:
        return "conservador"
    if max_loss_pct <= 0.15:
        return "neutro"
    if max_loss_pct <= 0.30:
        return "arriesgado"
    return "muy_arriesgado"


def resolve_methodology_id(method: Optional[str], strategy: Optional[str], methodology_id: Optional[str]) -> str:
    """Resuelve el ID de metodología desde parámetros legados o actuales."""
    if strategy == "benchmark" or method == "benchmark":
        return "benchmark"
    if method in LEGACY_METHOD_MAP:
        return LEGACY_METHOD_MAP[method]
    return methodology_id or "markowitz_media_varianza"


def resolve_target_holdings(target_holdings: Optional[int], n_stocks: Optional[int]) -> int:
    """Resuelve número de holdings finales."""
    value = target_holdings or n_stocks or TARGET_HOLDINGS_DEFAULT
    return max(3, min(int(value), TARGET_HOLDINGS_MAX))


def resolve_profile(profile: Optional[str], max_loss_pct: Optional[float]) -> Tuple[str, Dict, float]:
    """Resuelve perfil de riesgo desde nombre o máxima pérdida."""
    if profile and profile in RISK_PROFILES:
        profile_cfg = RISK_PROFILES[profile]
        return profile, profile_cfg, profile_cfg["alpha_p"]

    max_loss = max_loss_pct if max_loss_pct is not None else 0.15
    profile_key = risk_level(max_loss)
    profile_cfg = RISK_PROFILES[profile_key]
    return profile_key, profile_cfg, profile_cfg["alpha_p"]


def resolve_candidate_pool_size(
    profile_cfg: Dict,
    requested: Optional[int],
    f5_total_size: int,
) -> int:
    """Resuelve el tamaño del sub-universo de candidatos."""
    if requested is not None:
        if profile_cfg["candidate_pool_max"] is not None:
            return max(10, min(int(requested), profile_cfg["candidate_pool_max"]))
        return max(10, min(int(requested), f5_total_size))

    if profile_cfg["candidate_pool_default"] is not None:
        return min(profile_cfg["candidate_pool_default"], f5_total_size)
    return f5_total_size


def optimizer_universe_size(candidate_pool_size: int, target_holdings: int) -> int:
    """Calcula el tamaño del universo para optimización."""
    return min(
        candidate_pool_size,
        max(MIN_OPTIMIZER_UNIVERSE, target_holdings * 4),
        MAX_OPTIMIZER_UNIVERSE,
    )


def normalize_parameter_values(methodology: Dict, incoming: Dict[str, object]) -> Dict[str, object]:
    """Normaliza valores de parámetros según tipo de entrada."""
    normalized: Dict[str, object] = {}
    for definition in methodology["parameters"]:
        key = definition["key"]
        raw_value = incoming.get(key, definition.get("default"))
        if definition["input_type"] in {"text", "textarea"}:
            normalized[key] = raw_value if raw_value is not None else definition.get("default")
        else:
            normalized[key] = normalize_numeric(raw_value, definition.get("default"))
    return normalized


def ensure_required_inputs(methodology: Dict, parameter_values: Dict[str, object]) -> None:
    """Valida que todos los parámetros requeridos estén presentes."""
    missing = []
    for definition in methodology["parameters"]:
        if not definition["required"]:
            continue
        value = parameter_values.get(definition["key"])
        if definition["input_type"] in {"text", "textarea"}:
            if value is None or str(value).strip() == "":
                missing.append(definition["label"])
        elif value is None:
            missing.append(definition["label"])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan parametros requeridos para la metodologia: {', '.join(missing)}.",
        )


def coerce_query_default(value):
    """Extrae valor por defecto de Pydantic Field."""
    return value.default if hasattr(value, "default") else value
