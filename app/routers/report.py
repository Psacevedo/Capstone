"""
report.py - Metadatos, archivos y vistas previas del informe academico FinPUC.
"""
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response

try:
    import fitz
except Exception:  # pragma: no cover - fallback defensivo
    fitz = None

router = APIRouter(prefix="/api/report", tags=["report"])

_ROOT = Path(__file__).resolve().parents[2]
_REPORT_DIR = _ROOT / "Informe"
_PDF_PATH = _REPORT_DIR / "Informe 1 - G13.pdf"
_TEXT_PATH = _REPORT_DIR / "informe_texto.txt"
_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}


def _page_image_url(page_number: int, dpi: int = 140) -> str:
    return f"/api/report/page/{page_number}?dpi={dpi}"


VISUAL_ASSETS = [
    {
        "id": "tabla_0_1",
        "label": "Tabla 0.1",
        "kind": "Tabla",
        "page_number": 5,
        "summary": "Distribucion sectorial del universo completo con datos validos.",
        "caption": "Establece el sesgo sectorial del universo crudo previo al filtrado F5.",
        "image_url": _page_image_url(5),
        "reference": "Anexo 1 / Tabla 0.1",
    },
    {
        "id": "figura_2_1",
        "label": "Figura 2.1",
        "kind": "Figura",
        "page_number": 33,
        "summary": "Flujo del ciclo semanal del sistema recomendador FinPUC.",
        "caption": "Resume el ciclo operacional semanal citado en la seccion 2.2.1.",
        "image_url": _page_image_url(33),
        "reference": "Seccion 2.2.1",
    },
    {
        "id": "tabla_2_1",
        "label": "Tabla 2.1",
        "kind": "Tabla",
        "page_number": 34,
        "summary": "Perfiles de riesgo y tolerancia de perdida de FinPUC.",
        "caption": "Relaciona perfiles con el parametro alpha_p del sistema.",
        "image_url": _page_image_url(34),
        "reference": "Seccion 2.2.2",
    },
    {
        "id": "tabla_0_10",
        "label": "Tabla 0.10",
        "kind": "Tabla",
        "page_number": 14,
        "summary": "Sub-universos recomendados por perfil de riesgo.",
        "caption": "Sustenta la separacion entre candidate_pool_size y target_holdings.",
        "image_url": _page_image_url(14),
        "reference": "Tabla 0.10",
    },
    {
        "id": "tabla_2_4",
        "label": "Tabla 2.4",
        "kind": "Tabla",
        "page_number": 38,
        "summary": "Cascada de filtros aplicada al universo de acciones.",
        "caption": "Resume el proceso F0-F5 que define el universo operativo.",
        "image_url": _page_image_url(38),
        "reference": "Seccion 2.5",
    },
    {
        "id": "tabla_2_3",
        "label": "Tabla 2.3",
        "kind": "Tabla",
        "page_number": 37,
        "summary": "Distribucion sectorial del universo crudo con datos validos (1.165 tickers).",
        "caption": "Replica la distribucion por sector previa al proceso F0-F5.",
        "image_url": _page_image_url(37),
        "reference": "Seccion 2.4.2 / Tabla 2.3",
    },
    {
        "id": "tabla_0_3",
        "label": "Tabla 0.3",
        "kind": "Tabla",
        "page_number": 10,
        "summary": "Estadisticas por sector del universo final F5.",
        "caption": "Soporta filtros sectoriales y lectura del universo operativo.",
        "image_url": _page_image_url(10),
        "reference": "Anexo 1 / Tabla 0.3",
    },
]


REPORT_OUTLINE = {
    "title": "Informe academico FinPUC",
    "summary": (
        "Documento base del proyecto que define el sistema recomendador, los perfiles "
        "de riesgo, la formulacion del problema, el universo F5 y la discusion "
        "metodologica del modelo."
    ),
    "assets": [
        {"id": "pdf", "label": "Informe PDF", "url": "/api/report/file/pdf"},
        {"id": "text", "label": "Texto del informe", "url": "/api/report/file/text"},
    ],
    "sections": [
        {
            "id": "2.2.1",
            "label": "2.2.1 Ciclo operacional semanal",
            "summary": "Describe la recomendacion semanal, la aceptacion del cliente, el cobro de comisiones y el retiro por perdida excedida.",
        },
        {
            "id": "2.2.2",
            "label": "2.2.2 Perfiles de riesgo",
            "summary": "Formaliza los cinco perfiles FinPUC y el parametro alpha_p de tolerancia a perdida.",
        },
        {
            "id": "2.3",
            "label": "2.3 Formulacion del problema",
            "summary": "Expone la decision principal, los objetivos y las restricciones del problema de portafolio.",
        },
        {
            "id": "2.5",
            "label": "2.5 Proceso de filtrado del universo",
            "summary": "Resume la cascada F0-F5 y la construccion del universo operativo de 636 acciones.",
        },
        {
            "id": "3",
            "label": "3 Revision bibliografica",
            "summary": "Recorre Markowitz, CAPM, Fama-French, Black-Litterman, CVaR y simulacion de Monte Carlo.",
        },
        {
            "id": "4",
            "label": "4 Discusion metodologica",
            "summary": "Integra las metodologias en un enfoque hibrido para FinPUC y presenta las ecuaciones 4.4 a 4.7.",
        },
    ],
    "tables": [
        {
            "id": "tabla_0_1",
            "label": "Tabla 0.1",
            "summary": "Distribucion sectorial del universo completo con datos validos.",
            "page_number": 5,
            "image_url": _page_image_url(5),
        },
        {
            "id": "tabla_2_1",
            "label": "Tabla 2.1",
            "summary": "Perfiles de riesgo y tolerancia de perdida de FinPUC.",
            "page_number": 34,
            "image_url": _page_image_url(34),
        },
        {
            "id": "tabla_0_9",
            "label": "Tabla 0.9",
            "summary": "Conexion entre parametros del modelo y fuente de datos.",
            "page_number": 13,
            "image_url": _page_image_url(13),
        },
        {
            "id": "tabla_0_10",
            "label": "Tabla 0.10",
            "summary": "Sub-universos recomendados por perfil de riesgo.",
            "page_number": 14,
            "image_url": _page_image_url(14),
        },
        {
            "id": "tabla_2_4",
            "label": "Tabla 2.4",
            "summary": "Cascada de filtros aplicada al universo de acciones.",
            "page_number": 38,
            "image_url": _page_image_url(38),
        },
        {
            "id": "tabla_2_3",
            "label": "Tabla 2.3",
            "summary": "Distribucion sectorial del universo crudo con datos validos (1.165 tickers).",
            "page_number": 37,
            "image_url": _page_image_url(37),
        },
    ],
    "formulae": [
        {
            "id": "4.4",
            "label": "Ecuacion 4.4",
            "summary": "Restriccion CVaR_beta(w) <= alpha_p.",
            "latex": r"\operatorname{CVaR}_{\beta}(\mathbf{w}) \le \alpha_p",
        },
        {
            "id": "4.5",
            "label": "Ecuacion 4.5",
            "summary": "Funcion P1(x1) de abandono del cliente.",
            "latex": r"P_1(x_1)=\frac{1}{1+e^{-\left(x_1-\bar{x}_1\right)}}",
        },
        {
            "id": "4.6",
            "label": "Ecuacion 4.6",
            "summary": "Funcion P2(x2) de aceptacion de la recomendacion.",
            "latex": r"P_2(x_2)=\frac{1}{1+e^{-\left(x_2-\bar{x}_2\right)}}",
        },
        {
            "id": "4.7",
            "label": "Ecuacion 4.7",
            "summary": "Asignacion tipo Markowitz usando retornos esperados mu_BL.",
            "latex": r"\max_{\mathbf{w}} \mathbf{w}^{\top}\mu_{BL} - \lambda\,\mathbf{w}^{\top}\Sigma\mathbf{w}",
        },
    ],
    "profiles": [
        {"id": "muy_conservador", "label": "Muy conservador", "alpha_pct": 0, "summary": "No admite perdidas sobre el capital."},
        {"id": "conservador", "label": "Conservador", "alpha_pct": 5, "summary": "Tolera perdidas minimas."},
        {"id": "neutro", "label": "Neutro", "alpha_pct": 15, "summary": "Mantiene tolerancia moderada al riesgo."},
        {"id": "arriesgado", "label": "Arriesgado", "alpha_pct": 30, "summary": "Acepta perdidas significativas por mayor retorno esperado."},
        {"id": "muy_arriesgado", "label": "Muy arriesgado", "alpha_pct": 40, "summary": "Alta tolerancia al riesgo dentro del universo F5."},
    ],
    "visual_assets": VISUAL_ASSETS,
}


def _ensure_report_exists(path: Path) -> None:
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo del informe no encontrado.")


@lru_cache(maxsize=48)
def _render_page_png(page_number: int, dpi: int) -> bytes:
    if fitz is None:
        raise RuntimeError("PyMuPDF no esta disponible en el entorno actual.")

    _ensure_report_exists(_PDF_PATH)
    with fitz.open(_PDF_PATH) as document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Numero de pagina fuera de rango.")

        page = document.load_page(page_number - 1)
        zoom = dpi / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")


@router.get("/outline")
def get_report_outline():
    return JSONResponse(content=REPORT_OUTLINE, headers=_CACHE_HEADERS)


@router.get("/page/{page_number}")
def get_report_page(page_number: int, dpi: int = Query(default=140, ge=96, le=220)):
    try:
        image_bytes = _render_page_png(page_number, dpi)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(content=image_bytes, media_type="image/png", headers=_CACHE_HEADERS)


@router.get("/file/{kind}")
def get_report_file(kind: str):
    if kind == "pdf":
        path = _PDF_PATH
        media_type = "application/pdf"
    elif kind == "text":
        path = _TEXT_PATH
        media_type = "text/plain; charset=utf-8"
    else:
        raise HTTPException(status_code=404, detail="Archivo de informe no reconocido.")

    _ensure_report_exists(path)
    return FileResponse(path, media_type=media_type, filename=path.name, headers=_CACHE_HEADERS)
