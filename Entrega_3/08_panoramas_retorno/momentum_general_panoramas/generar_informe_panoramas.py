"""
Generador de informe y visualizaciones para panoramas proyectados de retorno.

Lee los resultados producidos por validacion_momentum_general_panoramas.py y
construye un informe LaTeX autocontenido, junto con figuras comparativas por
modelo, escenario historico, perfil de riesgo y panorama proyectado.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs"
TEST_DIR = OUTPUT_DIR / "test_p4"
BEHAVIOR_DIR = OUTPUT_DIR / "behavior"
REPORT_DIR = WORK_DIR / "informe resultados"
FIG_DIR = REPORT_DIR / "figuras"
REPORT_TEX = REPORT_DIR / "informe_resultados_panoramas_retorno.tex"

for directory in [REPORT_DIR, FIG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

PANORAMA_ORDER = ["desfavorable", "neutro", "favorable"]
PANORAMA_LABELS = {
    "desfavorable": "Desfavorable",
    "neutro": "Neutro",
    "favorable": "Favorable",
}
PANORAMA_COLORS = {
    "desfavorable": (185, 72, 50),
    "neutro": (146, 109, 43),
    "favorable": (56, 132, 84),
}
MODEL_ORDER = ["Markowitz", "BL calibrado"]
SCENARIO_ORDER = ["sin_pandemia", "con_pandemia"]
PROFILE_ORDER = [
    "Muy conservador",
    "Conservador",
    "Neutro",
    "Arriesgado",
    "Muy arriesgado",
]
SCENARIO_LABELS = {
    "sin_pandemia": "sin pandemia",
    "con_pandemia": "con pandemia",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT_TITLE = font(26, True)
FONT_SUBTITLE = font(16)
FONT_AXIS = font(13)
FONT_SMALL = font(12)
FONT_LEGEND = font(13)


def slug(value: str) -> str:
    value = value.lower()
    value = value.replace(" ", "_").replace("/", "_")
    value = re.sub(r"[^a-z0-9_]+", "", value)
    return value.strip("_")


def tex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def fmt_num(value: float, decimals: int = 3) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(value: float) -> str:
    if pd.isna(value):
        return "---"
    return f"{int(round(float(value))):,}".replace(",", ".")


def fmt_pct(value: float, decimals: int = 1) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value) * 100:.{decimals}f}\\%"


def display_model(model: str) -> str:
    return "Black-Litterman calibrado" if model == "BL calibrado" else model


def ordered_unique(values: Iterable[str], preferred: Sequence[str]) -> List[str]:
    present = list(dict.fromkeys(values))
    ordered = [value for value in preferred if value in present]
    ordered.extend([value for value in present if value not in ordered])
    return ordered


def get_range(values: Sequence[float]) -> Tuple[float, float]:
    clean = [float(v) for v in values if pd.notna(v) and math.isfinite(float(v))]
    if not clean:
        return 0.0, 1.0
    vmin = min(clean)
    vmax = max(clean)
    if abs(vmax - vmin) < 1e-12:
        pad = max(abs(vmax) * 0.10, 1.0)
        return vmin - pad, vmax + pad
    pad = (vmax - vmin) * 0.08
    lower = min(0.0, vmin - pad) if vmin >= 0 else vmin - pad
    return lower, vmax + pad


def scale_x(value: float, xmin: float, xmax: float, left: int, right: int) -> int:
    if xmax == xmin:
        return left
    return int(left + (value - xmin) / (xmax - xmin) * (right - left))


def scale_y(value: float, ymin: float, ymax: float, top: int, bottom: int) -> int:
    if ymax == ymin:
        return bottom
    return int(bottom - (value - ymin) / (ymax - ymin) * (bottom - top))


def draw_axes(draw: ImageDraw.ImageDraw, left: int, top: int, right: int, bottom: int) -> None:
    axis_color = (80, 80, 80)
    grid_color = (226, 230, 234)
    for i in range(5):
        y = top + int((bottom - top) * i / 4)
        draw.line([(left, y), (right, y)], fill=grid_color, width=1)
    draw.line([(left, bottom), (right, bottom)], fill=axis_color, width=2)
    draw.line([(left, top), (left, bottom)], fill=axis_color, width=2)


def draw_legend(draw: ImageDraw.ImageDraw, x: int, y: int, items: Sequence[Tuple[str, Tuple[int, int, int]]]) -> None:
    cursor_x = x
    for label, color in items:
        draw.rectangle([cursor_x, y + 2, cursor_x + 16, y + 14], fill=color)
        draw.text((cursor_x + 22, y), label, fill=(50, 50, 50), font=FONT_LEGEND)
        cursor_x += 130


def draw_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    subtitle: str,
    x_label: str,
    y_label: str,
    out_path: Path,
    pct: bool = False,
) -> None:
    width, height = 1320, 760
    left, right, top, bottom = 100, width - 70, 105, height - 115
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    draw.text((left, 24), title, fill=(28, 33, 40), font=FONT_TITLE)
    draw.text((left, 62), subtitle, fill=(85, 91, 100), font=FONT_SUBTITLE)
    draw_axes(draw, left, top, right, bottom)

    all_x = df[x_col].dropna().astype(float).tolist()
    all_y = df[y_col].dropna().astype(float).tolist()
    xmin, xmax = (min(all_x), max(all_x)) if all_x else (0.0, 1.0)
    ymin, ymax = get_range(all_y)

    for i in range(5):
        value = ymin + (ymax - ymin) * i / 4
        y = scale_y(value, ymin, ymax, top, bottom)
        label = f"{value * 100:.1f}%" if pct else fmt_num(value, 2)
        draw.text((12, y - 8), label, fill=(90, 90, 90), font=FONT_SMALL)

    for i in range(6):
        value = xmin + (xmax - xmin) * i / 5
        x = scale_x(value, xmin, xmax, left, right)
        draw.line([(x, bottom), (x, bottom + 6)], fill=(80, 80, 80), width=1)
        draw.text((x - 12, bottom + 12), str(int(round(value))), fill=(90, 90, 90), font=FONT_SMALL)

    for panorama in PANORAMA_ORDER:
        sub = df[df["panorama_retorno"] == panorama].sort_values(x_col)
        if sub.empty:
            continue
        points = [
            (
                scale_x(float(row[x_col]), xmin, xmax, left, right),
                scale_y(float(row[y_col]), ymin, ymax, top, bottom),
            )
            for _, row in sub.iterrows()
            if pd.notna(row[y_col])
        ]
        if len(points) >= 2:
            draw.line(points, fill=PANORAMA_COLORS[panorama], width=3)
        for point in points[:: max(1, len(points) // 12)]:
            x, y = point
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=PANORAMA_COLORS[panorama])

    draw.text(((left + right) // 2 - 35, height - 48), x_label, fill=(55, 55, 55), font=FONT_AXIS)
    draw.text((left, top - 24), y_label, fill=(55, 55, 55), font=FONT_AXIS)
    draw_legend(
        draw,
        left,
        height - 84,
        [(PANORAMA_LABELS[p], PANORAMA_COLORS[p]) for p in PANORAMA_ORDER],
    )
    image.save(out_path)


def draw_grouped_bar_chart(
    df: pd.DataFrame,
    metric: str,
    title: str,
    subtitle: str,
    y_label: str,
    out_path: Path,
    pct: bool = False,
) -> None:
    width, height = 1320, 760
    left, right, top, bottom = 100, width - 70, 105, height - 145
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    draw.text((left, 24), title, fill=(28, 33, 40), font=FONT_TITLE)
    draw.text((left, 62), subtitle, fill=(85, 91, 100), font=FONT_SUBTITLE)
    draw_axes(draw, left, top, right, bottom)

    profiles = ordered_unique(df["portfolio"].tolist(), PROFILE_ORDER)
    values = [float(v) for v in df[metric].dropna().tolist()]
    ymin, ymax = get_range(values)
    if ymin < 0:
        ymin = min(ymin, 0.0)
    else:
        ymin = 0.0

    for i in range(5):
        value = ymin + (ymax - ymin) * i / 4
        y = scale_y(value, ymin, ymax, top, bottom)
        label = f"{value * 100:.1f}%" if pct else fmt_num(value, 2)
        draw.text((12, y - 8), label, fill=(90, 90, 90), font=FONT_SMALL)

    group_width = (right - left) / max(1, len(profiles))
    bar_width = min(44, int(group_width / 5))
    zero_y = scale_y(0.0, ymin, ymax, top, bottom)

    for i, profile in enumerate(profiles):
        center = left + int(group_width * (i + 0.5))
        for j, panorama in enumerate(PANORAMA_ORDER):
            sub = df[(df["portfolio"] == profile) & (df["panorama_retorno"] == panorama)]
            if sub.empty or pd.isna(sub.iloc[0][metric]):
                continue
            value = float(sub.iloc[0][metric])
            x0 = center + (j - 1) * (bar_width + 6) - bar_width // 2
            x1 = x0 + bar_width
            y = scale_y(value, ymin, ymax, top, bottom)
            draw.rectangle([x0, min(y, zero_y), x1, max(y, zero_y)], fill=PANORAMA_COLORS[panorama])
        label = profile.replace("Muy ", "Muy\n")
        draw.multiline_text((center - 50, bottom + 12), label, fill=(65, 65, 65), font=FONT_SMALL, align="center")

    draw.text((left, top - 24), y_label, fill=(55, 55, 55), font=FONT_AXIS)
    draw_legend(
        draw,
        left,
        height - 84,
        [(PANORAMA_LABELS[p], PANORAMA_COLORS[p]) for p in PANORAMA_ORDER],
    )
    image.save(out_path)


def read_inputs() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p4 = pd.read_csv(TEST_DIR / "p4_test_limpio_resumen.csv")
    weekly = pd.read_csv(BEHAVIOR_DIR / "weekly_behavior_timeseries_summary.csv")
    monthly = pd.read_csv(BEHAVIOR_DIR / "monthly_behavior_timeseries_summary.csv")
    semiannual = pd.read_csv(BEHAVIOR_DIR / "semiannual_gain_timeseries_summary.csv")
    return p4, weekly, monthly, semiannual


def generate_final_metric_figures(p4: pd.DataFrame) -> List[Tuple[str, Path, str]]:
    figures: List[Tuple[str, Path, str]] = []
    metrics = [
        ("terminal_wealth_mean", "Riqueza terminal", "Riqueza terminal promedio", False),
        ("company_revenue_mean", "Utilidad empresa", "Utilidad acumulada promedio", False),
        ("p4_score_mean", "Score P4", "Score P4 promedio", False),
        ("withdrawal_rate_mean", "Tasa de abandono", "Tasa de abandono", True),
        ("final_active_clients_mean", "Clientes finales", "Clientes activos finales", False),
    ]
    for model in ordered_unique(p4["modelo"].tolist(), MODEL_ORDER):
        for scenario in ordered_unique(p4["scenario"].tolist(), SCENARIO_ORDER):
            sub = p4[(p4["modelo"] == model) & (p4["scenario"] == scenario)]
            if sub.empty:
                continue
            for metric, title_metric, y_label, pct in metrics:
                filename = f"barras_{slug(metric)}_{slug(model)}_{slug(scenario)}.png"
                out_path = FIG_DIR / filename
                title = f"{title_metric} por panorama"
                subtitle = f"{display_model(model)} - escenario {SCENARIO_LABELS.get(scenario, scenario)}"
                draw_grouped_bar_chart(sub, metric, title, subtitle, y_label, out_path, pct=pct)
                caption = (
                    f"{title_metric} por perfil y panorama para {display_model(model)}, "
                    f"escenario {SCENARIO_LABELS.get(scenario, scenario)}."
                )
                figures.append((filename, out_path, caption))
    return figures


def generate_timeseries_figures(
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    semiannual: pd.DataFrame,
) -> Dict[str, List[Tuple[str, Path, str]]]:
    specs = {
        "riqueza": [
            (weekly, "week", "mean_active_wealth", "semanal", "Semana", "Riqueza promedio", False),
            (monthly, "month", "mean_active_wealth", "mensual", "Mes", "Riqueza promedio", False),
            (semiannual, "semester", "mean_active_wealth", "semestral", "Semestre", "Riqueza promedio", False),
        ],
        "perdida": [
            (weekly, "week", "mean_active_loss", "semanal", "Semana", "Perdida promedio", True),
            (monthly, "month", "mean_active_loss", "mensual", "Mes", "Perdida promedio", True),
            (semiannual, "semester", "mean_active_loss", "semestral", "Semestre", "Perdida promedio", True),
        ],
        "utilidad": [
            (weekly, "week", "company_revenue_cumulative_mean", "semanal", "Semana", "Utilidad acumulada", False),
            (monthly, "month", "company_revenue_cumulative_mean", "mensual", "Mes", "Utilidad acumulada", False),
            (semiannual, "semester", "company_revenue_cumulative_mean", "semestral", "Semestre", "Utilidad acumulada", False),
        ],
    }
    figures: Dict[str, List[Tuple[str, Path, str]]] = {key: [] for key in specs}
    all_models = ordered_unique(weekly["modelo"].tolist(), MODEL_ORDER)
    all_scenarios = ordered_unique(weekly["scenario"].tolist(), SCENARIO_ORDER)
    all_profiles = ordered_unique(weekly["portfolio"].tolist(), PROFILE_ORDER)

    for model in all_models:
        for scenario in all_scenarios:
            for profile in all_profiles:
                for group_name, group_specs in specs.items():
                    for frame, x_col, y_col, freq, x_label, y_label, pct in group_specs:
                        sub = frame[
                            (frame["modelo"] == model)
                            & (frame["scenario"] == scenario)
                            & (frame["portfolio"] == profile)
                        ]
                        if sub.empty:
                            continue
                        filename = (
                            f"linea_{slug(group_name)}_{freq}_{slug(model)}_"
                            f"{slug(scenario)}_{slug(profile)}.png"
                        )
                        out_path = FIG_DIR / filename
                        title_map = {
                            "riqueza": "Riqueza de clientes",
                            "perdida": "Perdida de clientes",
                            "utilidad": "Utilidad acumulada de empresa",
                        }
                        title = f"{title_map[group_name]} {freq}"
                        subtitle = (
                            f"{display_model(model)} - {profile} - "
                            f"escenario {SCENARIO_LABELS.get(scenario, scenario)}"
                        )
                        draw_line_chart(sub, x_col, y_col, title, subtitle, x_label, y_label, out_path, pct=pct)
                        caption = (
                            f"{title_map[group_name]} con frecuencia {freq} para el perfil {profile}, "
                            f"{display_model(model)}, escenario {SCENARIO_LABELS.get(scenario, scenario)}."
                        )
                        figures[group_name].append((filename, out_path, caption))
    return figures


def p4_table_tex(p4: pd.DataFrame) -> str:
    cols = [
        "Modelo",
        "Escenario",
        "Perfil",
        "Panorama",
        "Riqueza",
        "Utilidad",
        "Score P4",
        "Abandono",
        "Clientes finales",
    ]
    rows: List[str] = []
    sort_cols = ["modelo", "scenario", "portfolio", "panorama_retorno"]
    ordered = p4.copy()
    ordered["portfolio_order"] = ordered["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)}).fillna(99)
    ordered["panorama_order"] = ordered["panorama_retorno"].map({p: i for i, p in enumerate(PANORAMA_ORDER)}).fillna(99)
    ordered["model_order"] = ordered["modelo"].map({m: i for i, m in enumerate(MODEL_ORDER)}).fillna(99)
    ordered["scenario_order"] = ordered["scenario"].map({s: i for i, s in enumerate(SCENARIO_ORDER)}).fillna(99)
    ordered = ordered.sort_values(["model_order", "scenario_order", "portfolio_order", "panorama_order"] + sort_cols)
    for _, row in ordered.iterrows():
        rows.append(
            " & ".join(
                [
                    tex_escape(display_model(row["modelo"])),
                    tex_escape(SCENARIO_LABELS.get(row["scenario"], row["scenario"])),
                    tex_escape(row["portfolio"]),
                    tex_escape(PANORAMA_LABELS.get(row["panorama_retorno"], row["panorama_retorno"])),
                    fmt_num(row["terminal_wealth_mean"], 3),
                    fmt_num(row["company_revenue_mean"], 2),
                    fmt_num(row["p4_score_mean"], 3),
                    fmt_pct(row["withdrawal_rate_mean"], 1),
                    fmt_int(row["final_active_clients_mean"]),
                ]
            )
            + r" \\"
        )
    header = " & ".join(cols) + r" \\"
    return "\n".join(
        [
            r"\begin{table}[H]",
            r"\centering",
            r"\scriptsize",
            r"\resizebox{\textwidth}{!}{%",
            r"\begin{tabular}{llllrrrrr}",
            r"\toprule",
            header,
            r"\midrule",
            "\n".join(rows),
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\caption{Resumen P4 por modelo, escenario historico, perfil de riesgo y panorama proyectado de retorno.}",
            r"\label{tab:p4-panoramas-resumen}",
            r"\end{table}",
        ]
    )


def best_panorama_table_tex(p4: pd.DataFrame) -> str:
    rows: List[str] = []
    grouped = p4.sort_values("p4_score_mean", ascending=False).groupby(["modelo", "scenario", "portfolio"], as_index=False)
    best = grouped.first()
    best["portfolio_order"] = best["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)}).fillna(99)
    best["model_order"] = best["modelo"].map({m: i for i, m in enumerate(MODEL_ORDER)}).fillna(99)
    best["scenario_order"] = best["scenario"].map({s: i for i, s in enumerate(SCENARIO_ORDER)}).fillna(99)
    best = best.sort_values(["model_order", "scenario_order", "portfolio_order"])
    for _, row in best.iterrows():
        rows.append(
            " & ".join(
                [
                    tex_escape(display_model(row["modelo"])),
                    tex_escape(SCENARIO_LABELS.get(row["scenario"], row["scenario"])),
                    tex_escape(row["portfolio"]),
                    tex_escape(PANORAMA_LABELS.get(row["panorama_retorno"], row["panorama_retorno"])),
                    fmt_num(row["retorno_anual_proyectado_mean"], 3),
                    fmt_num(row["terminal_wealth_mean"], 3),
                    fmt_num(row["p4_score_mean"], 3),
                    fmt_pct(row["withdrawal_rate_mean"], 1),
                ]
            )
            + r" \\"
        )
    return "\n".join(
        [
            r"\begin{table}[H]",
            r"\centering",
            r"\scriptsize",
            r"\resizebox{\textwidth}{!}{%",
            r"\begin{tabular}{llllrrrr}",
            r"\toprule",
            r"Modelo & Escenario & Perfil & Mejor panorama & Retorno proyectado & Riqueza & Score P4 & Abandono \\",
            r"\midrule",
            "\n".join(rows),
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\caption{Panorama con mayor Score P4 dentro de cada combinacion modelo--escenario--perfil.}",
            r"\label{tab:mejor-panorama-score}",
            r"\end{table}",
        ]
    )


def figure_tex(filename: str, caption: str, label: str) -> str:
    return "\n".join(
        [
            r"\begin{figure}[H]",
            r"\centering",
            rf"\includegraphics[width=0.92\textwidth]{{figuras/{filename}}}",
            rf"\caption{{{tex_escape(caption)}}}",
            rf"\label{{fig:{label}}}",
            r"\end{figure}",
        ]
    )


def selected_figures(figures: Sequence[Tuple[str, Path, str]], max_items: int | None = None) -> List[Tuple[str, Path, str]]:
    if max_items is None:
        return list(figures)
    return list(figures[:max_items])


def write_report(
    p4: pd.DataFrame,
    final_figures: List[Tuple[str, Path, str]],
    ts_figures: Dict[str, List[Tuple[str, Path, str]]],
) -> None:
    riqueza_figs = selected_figures(ts_figures["riqueza"], None)
    perdida_figs = selected_figures(ts_figures["perdida"], None)
    utilidad_figs = selected_figures(ts_figures["utilidad"], None)

    final_blocks = [
        figure_tex(filename, caption, f"final-{slug(filename[:-4])}")
        for filename, _, caption in selected_figures(final_figures, 20)
    ]
    riqueza_blocks = [
        figure_tex(filename, caption, f"riqueza-{slug(filename[:-4])}")
        for filename, _, caption in riqueza_figs
    ]
    perdida_blocks = [
        figure_tex(filename, caption, f"perdida-{slug(filename[:-4])}")
        for filename, _, caption in perdida_figs
    ]
    utilidad_blocks = [
        figure_tex(filename, caption, f"utilidad-{slug(filename[:-4])}")
        for filename, _, caption in utilidad_figs
    ]

    tex = rf"""\documentclass[11pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[spanish]{{babel}}
\usepackage{{amsmath}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{float}}
\usepackage{{geometry}}
\usepackage{{hyperref}}
\geometry{{margin=2.3cm}}
\setlength{{\parskip}}{{0.55em}}
\setlength{{\parindent}}{{0pt}}

\title{{Informe de resultados: panoramas proyectados de retorno}}
\author{{FinPUC}}
\date{{}}

\begin{{document}}
\maketitle
\tableofcontents
\newpage

\section{{Panoramas proyectados de retorno}}
Esta iteracion mantiene congelada la calibracion ganadora de la view Momentum general y no vuelve a estimar los parametros de Black--Litterman. El objetivo es aislar el efecto de la proyeccion de retorno esperada dentro de la simulacion economica P4. Para cada combinacion de modelo, escenario historico y perfil de riesgo se construyen tres panoramas simetricos en torno al retorno anual base:
\begin{{align}}
R_{{favorable}} &= R_{{base}} + 0.5\sigma_{{base}},\\
R_{{neutro}} &= R_{{base}},\\
R_{{desfavorable}} &= R_{{base}} - 0.5\sigma_{{base}}.
\end{{align}}
La volatilidad anual se mantiene fija en $\sigma_{{base}}$, por lo que los panoramas representan cambios en la media proyectada y no nuevos escenarios historicos. En terminos computacionales, la simulacion semanal utiliza:
\begin{{align}}
\mu_{{sem}} &= (1+R_{{proyectado}})^{{1/52}}-1,\\
\sigma_{{sem}} &= \frac{{\sigma_{{base}}}}{{\sqrt{{52}}}}.
\end{{align}}
La probabilidad de aceptacion del portafolio y de sus rebalanceos tambien usa el retorno proyectado:
\begin{{equation}}
P_2 = \frac{{1}}{{1+\exp\left[-(R_{{proyectado}}-\widehat{{x}}_2)\right]}},
\end{{equation}}
donde $\widehat{{x}}_2$ corresponde a la tolerancia de perdida del perfil. La probabilidad de abandono conserva la especificacion de la version v1 plus, basada en perdida contra capital inicial, abandono semanal y restriccion de ruina. La utilidad de la empresa se calcula ex--post como una comision mensual de 0,5\% sobre el saldo administrado activo.

\section{{Analisis de resultados fuera de muestra}}
La Tabla~\ref{{tab:p4-panoramas-resumen}} resume la evaluacion P4 para los tres panoramas. El panorama neutro permite comparar conceptualmente contra la simulacion base, mientras que los panoramas favorable y desfavorable muestran la sensibilidad de riqueza, abandono, clientes activos y utilidad de empresa ante desplazamientos de media esperada.

{p4_table_tex(p4)}

La Tabla~\ref{{tab:mejor-panorama-score}} sintetiza cual panorama maximiza el Score P4 dentro de cada combinacion de modelo, escenario y perfil. Esta lectura no reemplaza la comparacion metodologica entre Markowitz y Black--Litterman; sirve para observar si la recomendacion economica es robusta cuando se tensiona el retorno esperado.

{best_panorama_table_tex(p4)}

{chr(10).join(final_blocks)}

\section{{Resultados de la dinamica de portafolio}}
Las figuras siguientes muestran la evolucion de riqueza, perdida y utilidad acumulada. La separacion por modelo, escenario historico y perfil permite evaluar si el cambio de panorama altera solo el nivel esperado de los resultados o tambien modifica la trayectoria temporal del sistema. Esta distincion es relevante porque el abandono ocurre semanalmente, mientras que el rebalanceo se propone semestralmente.

\subsection{{Riqueza semanal, mensual y semestral}}
{chr(10).join(riqueza_blocks)}

\subsection{{Perdida semanal, mensual y semestral}}
{chr(10).join(perdida_blocks)}

\subsection{{Utilidad acumulada semanal, mensual y semestral}}
{chr(10).join(utilidad_blocks)}

\section{{Evaluacion economica Monte Carlo P4 en Horizonte Limpio}}
La evaluacion economica se mantiene estrictamente en el Horizonte 3. Los panoramas no recalibran la view ni reescriben el conjunto historico; solo modifican el retorno esperado utilizado en la simulacion Monte Carlo. Por ello, la utilidad de empresa sigue siendo una medicion posterior al proceso de inversion: depende del saldo administrado de los clientes que permanecen activos, no de comisiones por aceptar recomendaciones o rebalanceos.

En el panorama desfavorable se espera una reduccion simultanea de riqueza terminal, aceptacion del riesgo y utilidad acumulada. En el panorama favorable, el aumento de retorno proyectado eleva la probabilidad de aceptacion y reduce la friccion economica asociada a abandono, especialmente en perfiles con mayor tolerancia a perdida. La comparacion contra el panorama neutro permite separar el desempeno de la metodologia de asignacion del efecto mecanico de desplazar la media esperada.

\section{{Discusion de robustez}}
La extension con panoramas proyectados agrega una prueba de sensibilidad sobre la capa P4 sin alterar la calibracion de Black--Litterman. Esto es metodologicamente importante porque evita transformar un ejercicio de estres economico en una nueva busqueda de parametros. Bajo esta arquitectura, los escenarios historicos \texttt{{sin\_pandemia}} y \texttt{{con\_pandemia}} siguen midiendo regimenes de mercado distintos, mientras que los panoramas \texttt{{desfavorable}}, \texttt{{neutro}} y \texttt{{favorable}} exploran variaciones controladas en la expectativa de retorno.

La robustez debe interpretarse como estabilidad relativa: un modelo robusto no necesariamente domina en todas las combinaciones, pero conserva trayectorias economicamente defendibles cuando se reduce el retorno proyectado y aprovecha de forma consistente el panorama favorable sin depender de supuestos de comision por rebalanceo.

\section{{Conclusiones}}
La iteracion de panoramas de retorno completa la validacion economica de Momentum general al mostrar como cambia el desempeno P4 ante un abanico simetrico de retorno esperado. La configuracion conserva la calibracion ganadora de Black--Litterman y agrega una lectura mas transparente para la defensa: los resultados no dependen de un unico retorno puntual, sino que pueden observarse bajo un caso desfavorable, uno neutro y uno favorable.

Para la recomendacion final, el panorama neutro debe mantenerse como caso central de comparacion metodologica. Los panoramas favorable y desfavorable deben presentarse como sensibilidad economica: si Black--Litterman conserva mejores niveles de riqueza ajustada por abandono y utilidad ex--post frente a Markowitz, entonces la recomendacion de Momentum general se fortalece; si algun perfil cambia de modelo recomendado, ese cambio debe leerse como una condicion de sensibilidad y no como una recalibracion de la view.

\end{{document}}
"""
    REPORT_TEX.write_text(tex, encoding="utf-8")


def main() -> None:
    p4, weekly, monthly, semiannual = read_inputs()
    final_figures = generate_final_metric_figures(p4)
    ts_figures = generate_timeseries_figures(weekly, monthly, semiannual)
    write_report(p4, final_figures, ts_figures)
    print(f"[INFORME-PANORAMAS] Figuras generadas: {len(list(FIG_DIR.glob('*.png')))}")
    print(f"[INFORME-PANORAMAS] Informe LaTeX: {REPORT_TEX}")


if __name__ == "__main__":
    main()
