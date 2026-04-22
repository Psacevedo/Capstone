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
):
    return {
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
        "Permite restringir la busqueda a un sector del universo F5 cuando el analisis lo requiere.",
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
            "id": "markowitz_media_varianza",
            "label": "Markowitz media-varianza",
            "family": "Optimizacion clasica",
            "recommended": False,
            "description": "Usa retornos historicos anualizados y la matriz de covarianza para maximizar el ratio de Sharpe.",
            "formula_summary": "max_w (w^T mu - r_f) / sqrt(w^T Sigma w)",
            "formula_latex": r"\max_{\mathbf{w}} \frac{\mathbf{w}^{\top}\mu - r_f}{\sqrt{\mathbf{w}^{\top}\Sigma\mathbf{w}}}",
            "report_references": ["Seccion 3", "Seccion 4", "Ecuacion 4.7"],
            "implementation_status": "Operativa",
            "formula_legend": [
                {
                    "symbol": "w",
                    "name": "Pesos del portafolio",
                    "description": "Vector de decision del optimizador. Cada w_i in [0, 0.4] y sum(w_i) = 1. Resuelto por SLSQP (scipy.optimize).",
                    "source": "Variable calculada — no proviene de datos externos",
                },
                {
                    "symbol": "mu",
                    "name": "Retornos esperados anualizados",
                    "description": "Media de retornos diarios * 252 para cada accion del sub-universo. Usa 8 anios de precios ajustados.",
                    "source": "Historical_Stocks/ — precios diarios ajustados por dividendos y splits",
                },
                {
                    "symbol": "r_f",
                    "name": "Tasa libre de riesgo",
                    "description": "Retorno garantizado anual de referencia. Mide el exceso de retorno del portafolio sobre un activo sin riesgo.",
                    "source": "Parametro de entrada del usuario (default 5% anual)",
                },
                {
                    "symbol": "Sigma",
                    "name": "Matriz de covarianza",
                    "description": "Covarianza anualizada N*N de retornos diarios: np.cov(retornos.T) * 252. Incluye regularizacion Tikhonov 1e-8 para garantizar definicion positiva.",
                    "source": "Historical_Stocks/ — calculada sobre el mismo periodo que mu",
                },
            ],
            "notes": [
                "Usa el CAGR historico y retornos diarios del universo F5 como insumos base.",
                "La restriccion de riesgo por perfil se reporta mediante CVaR historico.",
            ],
            "parameters": [
                _parameter(
                    "risk_free_rate_pct",
                    "Tasa libre de riesgo",
                    "Estimacion",
                    "Se usa para medir el exceso de retorno del portafolio respecto de un activo libre de riesgo.",
                    "Revision bibliografica / Sharpe (1964)",
                    unit="% anual",
                    default=5.0,
                    required=True,
                    step=0.1,
                    minimum=0,
                    maximum=25,
                ),
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
        },
        {
            "id": "minima_varianza_global",
            "label": "Minima varianza global",
            "family": "Optimizacion clasica",
            "recommended": False,
            "description": "Selecciona el portafolio de menor varianza del universo operativo, priorizando estabilidad.",
            "formula_summary": "min_w w^T Sigma w",
            "formula_latex": r"\min_{\mathbf{w}} \mathbf{w}^{\top}\Sigma\mathbf{w}",
            "report_references": ["Seccion 3", "Seccion 4", "Tabla 0.10"],
            "implementation_status": "Operativa",
            "formula_legend": [
                {
                    "symbol": "w",
                    "name": "Pesos del portafolio",
                    "description": "Vector de decision. Restricciones identicas a Markowitz: w_i in [0, 0.4], sum = 1. El optimizador ignora mu y solo minimiza riesgo.",
                    "source": "Variable calculada — no proviene de datos externos",
                },
                {
                    "symbol": "Sigma",
                    "name": "Matriz de covarianza",
                    "description": "Misma covarianza anualizada N*N que Markowitz. El modelo privilegia acciones con baja volatilidad propia y baja correlacion entre si.",
                    "source": "Historical_Stocks/ — np.cov(retornos_diarios.T) * 252",
                },
            ],
            "notes": [
                "Se alinea con perfiles conservadores y muy conservadores del informe.",
            ],
            "parameters": [
                _parameter(
                    "cvar_beta_pct",
                    "Nivel beta para CVaR",
                    "Riesgo y escenarios",
                    "Nivel de confianza de la medida de cola usada para verificar la compatibilidad con alpha_p.",
                    "Ecuacion 4.4",
                    unit="%",
                    default=95.0,
                    required=True,
                    step=1,
                    minimum=50,
                    maximum=99,
                ),
            ],
        },
        {
            "id": "maximo_retorno",
            "label": "Maximo retorno",
            "family": "Optimizacion clasica",
            "recommended": False,
            "description": "Asigna pesos maximizando el retorno esperado anualizado sin ventas cortas.",
            "formula_summary": "max_w w^T mu",
            "formula_latex": r"\max_{\mathbf{w}} \mathbf{w}^{\top}\mu",
            "report_references": ["Seccion 2.3.2", "Seccion 3"],
            "implementation_status": "Operativa",
            "formula_legend": [
                {
                    "symbol": "w",
                    "name": "Pesos del portafolio",
                    "description": "Vector de decision. El optimizador concentra peso (hasta 40%) en las acciones de mayor mu_i. Ignora completamente la covarianza.",
                    "source": "Variable calculada — no proviene de datos externos",
                },
                {
                    "symbol": "mu",
                    "name": "Retornos esperados anualizados",
                    "description": "Media de retornos diarios * 252. Al ignorar riesgo, el modelo favorece acciones de alto CAGR historico, tipicamente de alta volatilidad.",
                    "source": "Historical_Stocks/ — mismo calculo que Markowitz media-varianza",
                },
            ],
            "notes": [
                "Favorece perfiles muy arriesgados del universo F5.",
            ],
            "parameters": [
                _parameter(
                    "cvar_beta_pct",
                    "Nivel beta para CVaR",
                    "Riesgo y escenarios",
                    "Nivel de confianza del reporte de perdidas extremas del portafolio.",
                    "Ecuacion 4.4",
                    unit="%",
                    default=80.0,
                    required=True,
                    step=1,
                    minimum=50,
                    maximum=99,
                ),
            ],
        },
        {
            "id": "black_litterman_markowitz",
            "label": "Black-Litterman + Markowitz",
            "family": "Estimacion bayesiana — avance inicial",
            "recommended": False,
            "wip": True,
            "description": (
                "Construye retornos esperados mu_BL combinando la prior de equilibrio del mercado "
                "con vistas subjetivas del analista mediante actualizacion bayesiana. "
                "Es el modelo mas complejo del informe: requiere la matriz de views P, "
                "el vector Q, y los parametros de incertidumbre tau y Omega."
            ),
            "formula_summary": "mu_BL = ((tau Sigma)^-1 + P^T Omega^-1 P)^-1 ((tau Sigma)^-1 pi + P^T Omega^-1 Q)",
            "formula_latex": r"\mu_{BL}=\left[(\tau\Sigma)^{-1}+P^{\top}\Omega^{-1}P\right]^{-1}\left[(\tau\Sigma)^{-1}\pi + P^{\top}\Omega^{-1}Q\right]",
            "report_references": ["Seccion 4", "Ecuacion 4.7", "Black-Litterman (1990)"],
            "implementation_status": "Avance inicial — en desarrollo en paralelo",
            "formula_legend": [
                {
                    "symbol": "mu_BL",
                    "name": "Retornos esperados bayesianos",
                    "description": "Vector N de retornos ajustados que combina la prior historica con las views del analista. Reemplaza a mu en el paso de Markowitz.",
                    "source": "Calculado por el modelo — combina datos historicos y views del usuario",
                },
                {
                    "symbol": "tau",
                    "name": "Escala de incertidumbre de la prior",
                    "description": "Controla cuanto peso tiene la prior de mercado vs. las views. tau pequeno -> prior domina; tau grande -> views dominan. Tipicamente tau = 0.01 a 0.10.",
                    "source": "Parametro de entrada del usuario (default 0.05)",
                },
                {
                    "symbol": "Sigma",
                    "name": "Matriz de covarianza historica",
                    "description": "Covarianza anualizada N*N identica a los otros modelos. Se usa tanto para construir la prior pi como en el paso final de asignacion Markowitz.",
                    "source": "Historical_Stocks/ — np.cov(retornos_diarios.T) * 252",
                },
                {
                    "symbol": "P",
                    "name": "Matriz de views (K x N)",
                    "description": "Matriz binaria construida automaticamente desde views_json. Cada fila k indica que accion tiene view activa (P_ki = 1) y cuales no (P_ki = 0).",
                    "source": "Construida internamente desde las views_json ingresadas por el usuario",
                },
                {
                    "symbol": "Omega",
                    "name": "Incertidumbre de las views",
                    "description": "Matriz diagonal K*K donde cada elemento = omega_diag. Omega mayor -> views con menos influencia. Permite calibrar la confianza en cada view individualmente.",
                    "source": "Parametro de entrada del usuario (default 0.05 por view)",
                },
                {
                    "symbol": "pi",
                    "name": "Prior de equilibrio del mercado",
                    "description": "Retornos implicitos del mercado: pi = lambda * Sigma * w_mkt. w_mkt son los pesos por market cap del universo F5. Representa lo que el mercado ya tiene 'descontado'.",
                    "source": "Calculado desde market cap del universo F5 (columna market_cap de la BD local)",
                },
                {
                    "symbol": "Q",
                    "name": "Vector de views del analista",
                    "description": "Vector K con los retornos anualizados que el analista espera para cada accion con view. Ingresado como view_return_pct en views_json.",
                    "source": "Parametro de entrada del usuario via views_json (view_return_pct por ticker)",
                },
                {
                    "symbol": "lambda",
                    "name": "Aversion al riesgo del mercado",
                    "description": "Escala global de aversion al riesgo usada para derivar pi = lambda * Sigma * w_mkt. Tipicamente estimada en 2.0 a 3.0 para mercados desarrollados.",
                    "source": "Parametro de entrada del usuario (default 2.5)",
                },
            ],
            "notes": [
                "Prior de equilibrio pi derivada de los pesos de mercado del universo F5.",
                "tau controla cuanto peso tiene la prior vs. las views del analista.",
                "Omega (diagonal) fija la incertidumbre de cada view; Omega mayor implica views con menos peso.",
                "Las views Q se ingresan por ticker como retornos anualizados esperados.",
                "Fase siguiente: integracion con solver LP para restriccion CVaR <= alpha_p.",
            ],
            "parameters": [
                _parameter(
                    "risk_free_rate_pct",
                    "Tasa libre de riesgo",
                    "Estimacion",
                    "Componente base del retorno en exceso usado para construir la prior de equilibrio del mercado.",
                    "Seccion 4 / Black-Litterman",
                    unit="% anual",
                    default=5.0,
                    required=True,
                    step=0.1,
                    minimum=0,
                    maximum=25,
                ),
                _parameter(
                    "lambda_risk_aversion",
                    "Lambda — aversion al riesgo",
                    "Estimacion",
                    "Escala de aversion al riesgo usada para derivar la prior de equilibrio pi = lambda * Sigma * w_mkt.",
                    "Ecuacion 4.7",
                    default=2.5,
                    required=True,
                    step=0.1,
                    minimum=0.1,
                    maximum=10,
                ),
                _parameter(
                    "tau",
                    "Tau — incertidumbre de la prior",
                    "Estimacion",
                    "Escala de incertidumbre sobre la covarianza base. Tau pequeno da mas peso a la prior; tau grande a las views.",
                    "Discusion metodologica / Seccion 4",
                    default=0.05,
                    required=True,
                    step=0.01,
                    minimum=0.001,
                    maximum=1,
                ),
                _parameter(
                    "omega_diag",
                    "Omega diagonal — confianza en views",
                    "Estimacion",
                    "Incertidumbre de las vistas del analista. Omega mayor implica views con menos influencia sobre mu_BL.",
                    "Discusion metodologica / Seccion 4",
                    default=0.05,
                    required=True,
                    step=0.01,
                    minimum=0.001,
                    maximum=1,
                ),
                _parameter(
                    "views_json",
                    "Views del analista (matriz Q)",
                    "Estimacion",
                    "Vistas absolutas por ticker: retorno anualizado esperado segun el analista. Alimentan el vector Q del modelo.",
                    "Black-Litterman / Seccion 4",
                    default='[\n  {"ticker": "MSFT", "view_return_pct": 14.0},\n  {"ticker": "JNJ", "view_return_pct": 9.0}\n]',
                    required=True,
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
        },
    ],
}


def get_catalog() -> Dict:
    return deepcopy(CATALOG)


def get_methodology(methodology_id: str) -> Dict:
    for methodology in CATALOG["methodologies"]:
        if methodology["id"] == methodology_id:
            return deepcopy(methodology)
    raise KeyError(methodology_id)


def get_base_parameters() -> List[Dict]:
    return deepcopy(BASE_PARAMETERS)
