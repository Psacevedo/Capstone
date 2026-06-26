"""
methodology_catalog.py - Catalogo academico de metodologias FinPUC.
"""
from copy import deepcopy
from typing import Dict, List


def _parameter(
    key: str,
    label: str,
    group: str,
    meaning: str,
    report_reference: str,
    unit: str = "",
    default=None,
    required: bool = False,
    input_type: str = "number",
    step=None,
    minimum=None,
    maximum=None,
    placeholder: str = "",
    options: List[Dict] = None,
):
    result = {
        "key": key,
        "label": label,
        "group": group,
        "meaning": meaning,
        "report_reference": report_reference,
        "unit": unit,
        "default": default,
        "required": required,
        "input_type": input_type,
        "step": step,
        "min": minimum,
        "max": maximum,
        "placeholder": placeholder,
    }
    if options:
        result["options"] = options
    return result


def _supuesto(label: str, value: str, reference: str, applies_to: str = "Todas"):
    return {"label": label, "value": value, "reference": reference, "applies_to": applies_to}

# ============================================================
# Supuestos globales (Entrega 2) — compartidos por todas las metodologias
# ============================================================
SUPUESTOS_GLOBALES = [
    _supuesto("Tasa libre de riesgo (Rf)", "2% anual", "Supuestos F1 / Seccion 4"),
    _supuesto("Dias habiles por ano", "252", "Supuestos E3 / Seccion 2.5"),
    _supuesto("Shrinkage de covarianza (lambda)", "0.20 (Ledoit-Wolf)", "Supuestos E1 / Metodologia"),
    _supuesto("Comision anual (k)", "1% (solo en Monte Carlo P4)", "Supuestos F2 / Seccion 2.4"),
    _supuesto("Sensibilidad logistica (s)", "20", "Supuestos K4 / Ecuacion 4.6"),
    _supuesto("Turnover por recomendacion aceptada", "5% de la riqueza actual", "Supuestos K7 / Seccion 2.4"),
    _supuesto("Capital inicial cliente (C0)", "$1,000 USD", "Supuestos K1 / P4"),
    _supuesto("Rebalanceo de optimizacion", "Semestral (126 dias habiles)", "Supuestos J1 / Seccion 2.2"),
    _supuesto("Rebalanceo de simulacion", "Semanal (cada 1 semana)", "Supuestos K3 / P4"),
    _supuesto("Horizonte de simulacion", "5 anos (260 semanas)", "Supuestos K2 / P4"),
    _supuesto("Simulaciones Monte Carlo", "5,000 trayectorias", "Supuestos K8 / P4"),
    _supuesto("Escenarios proyectados", "+/- 0.5 * sigma (fav/neutro/desfav)", "Supuestos L1-L4 / P4"),
    _supuesto("Medicion de perdida (P1)", "Respecto a C0, no al maximo historico", "Supuestos K6 / P4"),
    _supuesto("Solo largo (long-only)", "w_i >= 0 para todo i", "Supuestos C1 / Seccion 2.4"),
    _supuesto("Presupuesto completo", "sum(w_i) = 1 (100% invertido)", "Supuestos C2 / Seccion 2.4"),
    _supuesto("Solver de optimizacion", "SLSQP (scipy.optimize.minimize)", "Supuestos G1 / Implementacion"),
    _supuesto("Time budget", "< 10 segundos por optimizacion", "Supuestos G5 / Seccion 2.4"),
]

BL_SUPUESTOS = [
    _supuesto("Tau (incertidumbre de la prior)", "0.05", "Supuestos H1 / Seccion 4", "Black-Litterman"),
    _supuesto("Lambda (aversion al riesgo de mercado)", "2.5 (fallback si delta no es finito)", "Supuestos H2 / Ecuacion 4.7", "Black-Litterman"),
    _supuesto("Omega (incertidumbre de views)", "P * (tau * Sigma) * P^T / confidence", "Supuestos H4 / Seccion 4", "Black-Litterman"),
    _supuesto("Covarianza posterior", "Sigma_BL = nearest_psd(Sigma + posterior_covariance)", "Supuestos E6 / Metodologia", "Black-Litterman"),
    _supuesto("Confianza view: momentum", "0.50 (todas las variantes de momentum)", "Supuestos I1-I3 / Metodologia", "Black-Litterman"),
    _supuesto("Confianza view: momentum general", "0.50 (calibracion Entrega 3)", "Supuestos I5 / Metodologia", "Black-Litterman"),
    _supuesto("Confianza view: desempleo", "0.35", "Supuestos I4 / Metodologia", "Black-Litterman"),
    _supuesto("Lookback momentum general", "252 dias habiles (1 ano)", "Supuestos I1 / Metodologia", "Black-Litterman"),
    _supuesto("Lookback momentum top20 6M", "126 dias habiles (6 meses)", "Supuestos I2 / Metodologia", "Black-Litterman"),
    _supuesto("Lookback momentum top40 1Y", "252 dias habiles (1 ano)", "Supuestos I3 / Metodologia", "Black-Litterman"),
    _supuesto("Desempleo asumido", "4% (bajo el neutro 5%)", "Supuestos I4a-I4b / Metodologia", "Black-Litterman"),
    _supuesto("Beta macro desempleo", "1.0", "Supuestos I4c / Metodologia", "Black-Litterman"),
    _supuesto("Puntos frontera eficiente BL", "12 (vs 30 en Markowitz)", "Supuestos H5 / Seccion 4", "Black-Litterman"),
]

MARKOWITZ_SUPUESTOS = [
    _supuesto("Gamma por perfil", "muy_cons=80, cons=45, neutro=20, arriesgado=8, muy_arr=3", "Supuestos D1-D5 / Informe 1", "Markowitz"),
    _supuesto("Peso maximo por perfil", "5% / 7% / 10% / 15% / 20%", "Supuestos C5 / Seccion 2.4", "Markowitz"),
    _supuesto("Cota volatilidad por perfil", "8% / 12% / 18% / 28% / 40% anual", "Supuestos D1-D5 / Seccion 2.3", "Markowitz"),
    _supuesto("Relajacion automatica", "Si la cota de volatilidad es infactible, se relaja", "Supuestos G4 / Seccion 3", "Markowitz"),
    _supuesto("Puntos frontera eficiente", "30 puntos equiespaciados", "Supuestos G2 / Seccion 3", "Markowitz"),
]


BASE_PARAMETERS: List[Dict] = [
    _parameter(
        "profile",
        "Perfil de riesgo",
        "Perfil y universo",
        "Selecciona el umbral alpha_p de perdida maxima tolerada por el cliente.",
        "Tabla 2.1 / Seccion 2.2.2",
        default="neutro",
        required=True,
        input_type="text",
    ),
    _parameter(
        "candidate_pool_size",
        "Tamano del sub-universo",
        "Perfil y universo",
        "Cantidad de acciones candidatas que pasan al conjunto operativo antes de optimizar.",
        "Tabla 0.10 / Tabla 2.4",
        unit="acciones",
        default=100,
        required=False,
        step=1,
        minimum=10,
        maximum=636,
    ),
    _parameter(
        "target_holdings",
        "Holdings finales",
        "Perfil y universo",
        "Numero final de posiciones visibles en el portafolio recomendado.",
        "Decision principal 2.3.1",
        unit="acciones",
        default=10,
        required=True,
        step=1,
        minimum=3,
        maximum=30,
    ),
    _parameter(
        "sector",
        "Filtro sectorial opcional",
        "Perfil y universo",
        "Permite restringir la busqueda a un sector del universo de acciones cuando el analisis lo requiere.",
        "Anexo 1 / Tabla 0.3",
        default="",
        required=False,
        input_type="text",
        placeholder="Technology, Utilities, Consumer Defensive...",
    ),
]


CATALOG = {
    "default_methodology_id": "markowitz_media_varianza",
    "methodologies": [
        {
            "id": "equiponderado",
            "label": "Portafolio equiponderado",
            "family": "Benchmark de referencia",
            "recommended": False,
            "hidden": True,
            "description": (
                "Asigna pesos iguales w_i = 1/N a los N activos de mayor capitalizacion del universo de acciones. "
                "Es el benchmark primario del informe: permite medir si la optimizacion agrega valor real "
                "respecto de una estrategia ingenua sin supuestos sobre retornos o covarianzas."
            ),
            "formula_summary": "w_i = 1/N  para todo i en el sub-universo (top N por market cap)",
            "formula_latex": r"w_i = \frac{1}{N}, \quad \forall\, i \in \mathcal{U}_{\text{top-N}}",
            "report_references": ["Seccion 2.3.2", "Tabla 5", "Figura 2"],
            "implementation_status": "Operativo",
            "formula_legend": [
                {
                    "symbol": "w_i",
                    "name": "Peso equiponderado",
                    "description": "Fraccion identica del capital asignada a cada accion. No requiere estimacion de mu ni Sigma. Es la estrategia mas simple posible dentro del universo de acciones.",
                    "source": "Variable calculada — no proviene de datos externos",
                },
                {
                    "symbol": "N",
                    "name": "Numero de holdings",
                    "description": "Cardinalidad del portafolio final. Las N acciones se seleccionan por market cap descendente dentro del universo de acciones ya filtrado.",
                    "source": "Parametro de entrada del usuario (target_holdings)",
                },
                {
                    "symbol": "U_top-N",
                    "name": "Sub-universo operativo",
                    "description": "Conjunto de las N acciones de mayor capitalizacion del universo de acciones. Garantiza liquidez y representatividad de mercado.",
                    "source": "Historical_Stocks/ — columna market_cap de stocks_info.txt",
                },
            ],
            "notes": [
                "Sirve como baseline pasivo: si el modelo optimizado no supera al benchmark, su valor agregado es cuestionable.",
                "Calculado sobre el mismo universo de acciones del informe para garantizar comparabilidad directa.",
            ],
            "parameters": [
                _parameter(
                    "cvar_beta_pct",
                    "Nivel beta para CVaR",
                    "Riesgo y escenarios",
                    "Nivel de confianza para reportar el CVaR historico del portafolio equiponderado.",
                    "Ecuacion 4.4",
                    unit="%",
                    default=90.0,
                    required=True,
                    step=1,
                    minimum=50,
                    maximum=99,
                ),
            ],
            "supuestos": SUPUESTOS_GLOBALES + [
                _supuesto("Regla de seleccion", "Top-N por capitalizacion de mercado", "Seccion 2.3.2", "Equiponderado"),
                _supuesto("Ponderacion", "Pesos iguales w_i = 1/N", "Seccion 2.3.2", "Equiponderado"),
            ],
        },
        {
            "id": "markowitz_media_varianza",
            "label": "Markowitz media-varianza",
            "family": "Optimizacion clasica",
            "recommended": True,
            "description": "Maximiza la utilidad cuadratica mu'w - 0.5*gamma*w'Sigma*w con gamma, max_weight y max_vol por perfil de riesgo, segun Entrega 2.",
            "formula_summary": "max_w w^T mu - 0.5 * gamma * w^T Sigma w",
            "formula_latex": r"\max_{\mathbf{w}}\;\mathbf{w}^{\top}\mu - \frac{1}{2}\,\gamma\,\mathbf{w}^{\top}\Sigma\mathbf{w}",
            "report_references": ["Seccion 3", "Seccion 4", "Ecuacion 3.1"],
            "implementation_status": "Operativo",
            "formula_legend": [
                {
                    "symbol": "w",
                    "name": "Pesos del portafolio",
                    "description": "Vector de decision del optimizador. Cada w_i en [0, max_weight] y sum(w_i) = 1.",
                    "source": "Variable calculada — no proviene de datos externos",
                },
                {
                    "symbol": "mu",
                    "name": "Retornos esperados anualizados",
                    "description": "CAGR historico con fallback a media anualizada * 252.",
                    "source": "Historical_Stocks/",
                },
                {
                    "symbol": "gamma",
                    "name": "Coeficiente de aversion al riesgo",
                    "description": "Muy conservador=80, Conservador=45, Neutro=20, Arriesgado=8, Muy arriesgado=3 (Entrega 2).",
                    "source": "Calibrado segun perfil — Entrega 2",
                },
                {
                    "symbol": "Sigma",
                    "name": "Matriz de covarianza",
                    "description": "Covarianza anualizada con shrinkage lambda=0.20 y regularizacion 1e-8.",
                    "source": "Historical_Stocks/",
                },
            ],
            "notes": [
                "Covarianza con shrinkage lambda=0.20 (Ledoit-Wolf).",
                "Cota de volatilidad por perfil con relajacion automatica si es infactible.",
                "max_weight por perfil: 5% / 7% / 10% / 15% / 20%.",
            ],
            "parameters": [
                _parameter(
                    "cvar_beta_pct",
                    "Nivel beta para CVaR",
                    "Riesgo y escenarios",
                    "Nivel de confianza usado para evaluar la cola de perdidas del portafolio.",
                    "Ecuacion 4.4",
                    unit="%",
                    default=90.0,
                    required=True,
                    step=1,
                    minimum=50,
                    maximum=99,
                ),
            ],
            "supuestos": SUPUESTOS_GLOBALES + MARKOWITZ_SUPUESTOS,
        },
        {
            "id": "black_litterman_markowitz",
            "label": "Black-Litterman",
            "family": "Estimacion bayesiana",
            "recommended": True,
            "wip": False,
            "description": (
                "Construye retornos esperados mu_BL combinando la prior de equilibrio del mercado "
                "con vistas subjetivas del analista mediante actualizacion bayesiana. "
                "Soporta 4 tipos de views predefinidas (momentum, desempleo, momentum top20 6M, "
                "momentum top20-bottom20 1Y) y views manuales por ticker."
            ),
            "formula_summary": "mu_BL = pi + tau*Sigma*P' * inv(P*tau*Sigma*P' + Omega) * (Q - P*pi)",
            "formula_latex": r"\mu_{BL}= \pi + \tau\Sigma P^{\top}(P\tau\Sigma P^{\top} + \Omega)^{-1}(Q-P\pi)",
            "report_references": ["Seccion 4", "Black-Litterman (1990)", "Entrega 2"],
            "implementation_status": "Completo — 4 views predefinidas + soporte manual via JSON",
            "formula_legend": [
                {
                    "symbol": "mu_BL",
                    "name": "Retornos esperados bayesianos",
                    "description": "Vector N de retornos ajustados que combina la prior de equilibrio con las views del analista.",
                    "source": "Calculado por el modelo con shrinkage de covarianza (lambda=0.20) y Omega = P(tau*Sigma)P'/confidence.",
                },
                {
                    "symbol": "tau",
                    "name": "Escala de incertidumbre de la prior",
                    "description": "Controla cuanto peso tiene la prior de mercado vs. las views. tau=0.05 en Entrega 2.",
                    "source": "Parametro de entrada del usuario (default 0.05)",
                },
                {
                    "symbol": "P, Q",
                    "name": "Matriz de views y vector de retornos esperados",
                    "description": "Construidas automaticamente segun el tipo de view seleccionado o manualmente via JSON.",
                    "source": "bl_views.py para tipos predefinidos; views_json para manuales",
                },
                {
                    "symbol": "Omega",
                    "name": "Incertidumbre de las views",
                    "description": "Omega = P(tau*Sigma)P' / confidence. Mayor confianza -> menor Omega -> views con mas peso.",
                    "source": "Calculado automaticamente desde la confianza del tipo de view",
                },
                {
                    "symbol": "pi",
                    "name": "Prior de equilibrio del mercado",
                    "description": "pi = lambda * Sigma * w_mkt. w_mkt son los pesos por market cap.",
                    "source": "Market cap del universo de acciones",
                },
            ],
            "notes": [
                "Prior de equilibrio pi derivada de los pesos de mercado del universo de acciones.",
                "Covarianza con shrinkage lambda=0.20 (Ledoit-Wolf) antes del BL.",
                "Omega = P(tau*Sigma)P' / confidence. Mayor confianza = views mas influyentes.",
                "4 views predefinidas replican exactamente las del notebook black_litterman.ipynb.",
            ],
            "parameters": [
                _parameter(
                    "bl_view_type",
                    "Tipo de view",
                    "Estimacion",
                    "Selecciona una view predefinida (momentum, desempleo, momentum top20 6M, momentum top20-bottom20 1Y) o 'manual' para ingresar views por ticker.",
                    "Seccion 4 / Entrega 2",
                    default="momentum_top20_6m",
                    required=True,
                    input_type="select",
                    options=[
                        {"value": "momentum_top20_6m", "label": "Momentum Top20 6M (10 long / 10 short)"},
                        {"value": "momentum_top20_bottom20_1y", "label": "Momentum Top40 1Y (20 long / 20 short)"},
                        {"value": "momentum", "label": "Momentum 1Y universal (20 long / 20 short)"},
                        {"value": "momentum_general", "label": "Momentum General (E3 — 1Y, 20/20)"},
                        {"value": "desempleo", "label": "Desempleo (macro asumida)"},
                        {"value": "manual", "label": "Manual (JSON por ticker)"},
                    ],
                ),
                _parameter(
                    "risk_free_rate_pct",
                    "Tasa libre de riesgo",
                    "Estimacion",
                    "Supuesto fijo de la Entrega 2. Componente base del retorno en exceso usado para construir la prior de equilibrio del mercado.",
                    "Supuestos F1 / Seccion 4",
                    unit="% anual",
                    default=2.0,
                    required=False,
                    input_type="fixed",
                ),
                _parameter(
                    "lambda_risk_aversion",
                    "Lambda — aversion al riesgo",
                    "Estimacion",
                    "Supuesto fijo de la Entrega 2. Escala de aversion al riesgo usada para derivar la prior de equilibrio pi = lambda * Sigma * w_mkt. Fallback si delta no es finito.",
                    "Supuestos H2 / Ecuacion 4.7",
                    default=2.5,
                    required=False,
                    input_type="fixed",
                ),
                _parameter(
                    "tau",
                    "Tau — incertidumbre de la prior",
                    "Estimacion",
                    "Supuesto fijo de la Entrega 2 (tau=0.05). Controla el peso de la prior vs las views.",
                    "Supuestos H1 / Seccion 4",
                    default=0.05,
                    required=False,
                    input_type="fixed",
                ),
                _parameter(
                    "bl_confidence",
                    "Confianza (solo views manuales)",
                    "Estimacion",
                    "Nivel de confianza en las views manuales. Views predefinidas usan confianza fija (0.50 momentum, 0.35 desempleo).",
                    "Entrega 2 / Seccion 4",
                    default=0.50,
                    required=False,
                    step=0.05,
                    minimum=0.05,
                    maximum=1.0,
                ),
                _parameter(
                    "views_json",
                    "Views manuales (JSON)",
                    "Estimacion",
                    "Solo se usa si bl_view_type='manual'. Vistas absolutas por ticker: retorno anualizado esperado.",
                    "Black-Litterman / Seccion 4",
                    default='[\n  {"ticker": "MSFT", "view_return_pct": 14.0},\n  {"ticker": "JNJ", "view_return_pct": 9.0}\n]',
                    required=False,
                    input_type="textarea",
                    placeholder='[{"ticker":"MSFT","view_return_pct":14.0}]',
                ),
                _parameter(
                    "cvar_beta_pct",
                    "Nivel beta para CVaR",
                    "Riesgo y escenarios",
                    "Nivel de confianza de la cola de perdidas usada para validar el portafolio resultante.",
                    "Ecuacion 4.4",
                    unit="%",
                    default=90.0,
                    required=True,
                    step=1,
                    minimum=50,
                    maximum=99,
                ),
            ],
            "supuestos": SUPUESTOS_GLOBALES + BL_SUPUESTOS,
        },
    ],
}


def get_catalog() -> Dict:
    catalog = deepcopy(CATALOG)
    catalog["methodologies"] = [m for m in catalog["methodologies"] if not m.get("hidden")]
    return catalog


def get_methodology(methodology_id: str) -> Dict:
    for methodology in CATALOG["methodologies"]:
        if methodology["id"] == methodology_id:
            return deepcopy(methodology)
    raise KeyError(methodology_id)


def get_base_parameters() -> List[Dict]:
    return deepcopy(BASE_PARAMETERS)
