from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent

VIEWS: Dict[str, Dict[str, str]] = {
    "desempleo_macro_v1_plus": {"label": "Desempleo macro", "short": "Desempleo"},
    "momentum_general_v1_plus": {"label": "Momentum general", "short": "Momentum general"},
    "momentum_top_bottom_1y_v1_plus": {"label": "Momentum top/bottom 1Y", "short": "Top/bottom 1Y"},
    "momentum_top_marketcap_6m_v1_plus": {"label": "Momentum top market-cap 6M", "short": "Top market-cap 6M"},
}

PROFILE_ORDER = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]
PROFILE_COLORS = {
    "Muy conservador": (32, 92, 132),
    "Conservador": (59, 133, 95),
    "Neutro": (142, 109, 45),
    "Arriesgado": (180, 82, 47),
    "Muy arriesgado": (120, 76, 145),
}
SCENARIOS = ["sin_pandemia", "con_pandemia"]
MODELS = ["BL calibrado", "Markowitz base"]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def tex_escape(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
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
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def fmt_num(value: object, digits: int = 3) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value):.{digits}f}"


def fmt_pct(value: object, digits: int = 1) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value) * 100:.{digits}f}\\%"


def fmt_money(value: object) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value):,.0f}".replace(",", ".")


def fmt_int(value: object) -> str:
    if pd.isna(value):
        return "---"
    return str(int(round(float(value))))


def model_slug(model: str) -> str:
    return model.lower().replace(" ", "_").replace("-", "_")


def scenario_label(scenario: str) -> str:
    return "con pandemia" if scenario == "con_pandemia" else "sin pandemia"


def sort_profile(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["scenario_order"] = out["scenario"].map({"sin_pandemia": 0, "con_pandemia": 1})
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values(["scenario_order", "profile_order"]).drop(columns=["scenario_order", "profile_order"])


def font(size: int = 14, bold: bool = False) -> ImageFont.ImageFont:
    font_path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def draw_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    scenario: str,
    model: str,
    title: str,
    out_path: Path,
    y_is_pct: bool = False,
) -> None:
    subset = df[(df["scenario"] == scenario) & (df["modelo"] == model)].copy()
    width, height = 1200, 720
    ml, mr, mt, mb = 105, 45, 90, 115
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.text((ml, 30), title, fill=(25, 30, 35), font=font(24, True))
    draw.text((ml, 60), f"{model} - escenario {scenario_label(scenario)}", fill=(85, 90, 95), font=font(14))
    plot_w = width - ml - mr
    plot_h = height - mt - mb
    x0, y0 = ml, height - mb
    draw.line((x0, mt, x0, y0), fill=(65, 65, 65), width=2)
    draw.line((x0, y0, width - mr, y0), fill=(65, 65, 65), width=2)
    if subset.empty:
        draw.text((ml, mt + 40), "Sin datos", fill=(140, 40, 40), font=font(18, True))
        img.save(out_path)
        return

    x_values = sorted(subset[x_col].dropna().unique())
    x_min, x_max = float(min(x_values)), float(max(x_values))
    x_denom = max(x_max - x_min, 1.0)
    y_vals = subset[y_col].replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    y_min = min(0.0, float(y_vals.min()) if len(y_vals) else 0.0)
    y_max = max(0.0, float(y_vals.max()) if len(y_vals) else 1.0)
    if y_is_pct:
        y_min = 0.0
        y_max = min(max(y_max * 1.15, 0.05), 1.0)
    elif y_min < 0:
        pad = max((y_max - y_min) * 0.10, 1.0)
        y_min -= pad
        y_max += pad
    else:
        y_max = max(y_max * 1.15, 1.0)
    y_denom = max(y_max - y_min, 1e-9)

    for i in range(6):
        y = y0 - plot_h * i / 5
        val = y_min + y_denom * i / 5
        label = f"{val:.0%}" if y_is_pct else f"{val:,.0f}".replace(",", ".")
        draw.line((x0 - 5, y, width - mr, y), fill=(230, 232, 235))
        draw.text((18, y - 8), label, fill=(80, 80, 80), font=font(12))

    x_tick_step = max(1, int(round(len(x_values) / 8)))
    for x_val in x_values[::x_tick_step]:
        x = x0 + (float(x_val) - x_min) / x_denom * plot_w
        draw.line((x, y0, x, y0 + 5), fill=(80, 80, 80))
        draw.text((x - 12, y0 + 18), str(int(x_val)), fill=(60, 60, 60), font=font(11))

    for profile in PROFILE_ORDER:
        prof = subset[subset["portfolio"] == profile].sort_values(x_col)
        if prof.empty:
            continue
        points = []
        for _, row in prof.iterrows():
            x = x0 + (float(row[x_col]) - x_min) / x_denom * plot_w
            y = y0 - (float(row[y_col]) - y_min) / y_denom * plot_h
            points.append((x, y))
        color = PROFILE_COLORS[profile]
        for a, b in zip(points, points[1:]):
            draw.line((a[0], a[1], b[0], b[1]), fill=color, width=3)
        for x, y in points[:: max(1, len(points) // 18)]:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)

    lx, ly = ml, height - 82
    for i, profile in enumerate(PROFILE_ORDER):
        color = PROFILE_COLORS[profile]
        x = lx + (i % 3) * 315
        y = ly + (i // 3) * 24
        draw.rectangle((x, y + 4, x + 18, y + 16), fill=color)
        draw.text((x + 26, y), profile, fill=(45, 45, 45), font=font(13))
    draw.text((x0 + plot_w / 2 - 40, height - 42), x_col.capitalize(), fill=(45, 45, 45), font=font(14))
    img.save(out_path)


def load_view(view: str) -> Dict[str, pd.DataFrame]:
    out = ROOT / view / "outputs"
    return {
        "comparison": read_csv(out / "test_p4" / "test_limpio_comparacion_resumen.csv"),
        "turnover": read_csv(out / "portfolio_dynamics" / "turnover_summary.csv"),
        "sector": read_csv(out / "portfolio_dynamics" / "sector_return_concentration_summary.csv"),
        "p4": read_csv(out / "test_p4" / "p4_test_limpio_resumen.csv"),
        "behavior": read_csv(out / "behavior" / "behavior_probabilities_clients_summary.csv"),
        "weekly": read_csv(out / "behavior" / "weekly_behavior_timeseries_summary.csv"),
        "monthly": read_csv(out / "behavior" / "monthly_behavior_timeseries_summary.csv"),
        "semiannual_gain": read_csv(out / "behavior" / "semiannual_gain_timeseries_summary.csv"),
    }


def latex_table(df: pd.DataFrame, columns: List[Tuple[str, str, str]], caption: str, label: str) -> str:
    header = " & ".join(tex_escape(h) for _, h, _ in columns) + r" \\"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col, _, kind in columns:
            if kind == "pct":
                cells.append(fmt_pct(row[col]))
            elif kind == "num2":
                cells.append(fmt_num(row[col], 2))
            elif kind == "num3":
                cells.append(fmt_num(row[col], 3))
            elif kind == "money":
                cells.append(fmt_money(row[col]))
            elif kind == "int":
                cells.append(fmt_int(row[col]))
            else:
                cells.append(tex_escape(row[col]))
        rows.append(" & ".join(cells) + r" \\")
    spec = "l" + "r" * (len(columns) - 1)
    return "\n".join(
        [
            r"\begin{table}[H]",
            r"\centering",
            r"\resizebox{\textwidth}{!}{%",
            rf"\begin{{tabular}}{{{spec}}}",
            r"\toprule",
            header,
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
            r"}",
            rf"\caption{{{tex_escape(caption)}}}",
            rf"\label{{{label}}}",
            r"\end{table}",
            "",
        ]
    )


def make_figures(view: str, data: Dict[str, pd.DataFrame], report_dir: Path) -> List[str]:
    fig_dir = report_dir / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)
    figures: List[str] = []
    chart_specs = [
        ("weekly", "week", "active_clients_mean", "clientes_weekly", "Clientes activos semanales", False),
        ("monthly", "month", "active_clients_mean", "clientes_monthly", "Clientes activos mensuales", False),
        ("weekly", "week", "mean_weekly_abandon_probability", "abandono_weekly", "Probabilidad semanal de abandono", True),
        ("monthly", "month", "monthly_abandon_probability", "abandono_monthly", "Probabilidad mensual de abandono", True),
        ("weekly", "week", "p_accept_rebalance", "aceptacion_weekly", "Probabilidad semanal de aceptacion de rebalanceo", True),
        ("monthly", "month", "p_accept_rebalance", "aceptacion_monthly", "Probabilidad mensual de aceptacion de rebalanceo", True),
        ("weekly", "week", "mean_active_gain", "ganancia_weekly", "Ganancia semanal promedio por cliente activo", False),
        ("monthly", "month", "mean_active_gain", "ganancia_monthly", "Ganancia mensual promedio por cliente activo", False),
        ("semiannual_gain", "semester", "mean_active_gain", "ganancia_semiannual", "Ganancia semestral promedio por cliente activo", False),
    ]
    for dataset, x_col, y_col, prefix, title, pct in chart_specs:
        for scenario in SCENARIOS:
            for model in MODELS:
                filename = f"{prefix}_{scenario}_{model_slug(model)}.png"
                draw_line_chart(data[dataset], x_col, y_col, scenario, model, title, fig_dir / filename, pct)
                figures.append(filename)
    return figures


def figure_block(filename: str, caption: str, label: str) -> str:
    return "\n".join(
        [
            r"\begin{figure}[H]",
            r"\centering",
            rf"\includegraphics[width=0.92\textwidth]{{figuras/{filename}}}",
            rf"\caption{{{tex_escape(caption)}}}",
            rf"\label{{{label}}}",
            r"\end{figure}",
            "",
        ]
    )


def p4_interpretation(p4: pd.DataFrame, view_label: str) -> str:
    bl = p4[p4["modelo"] == "BL calibrado"]
    if bl.empty:
        return ""
    best = bl.sort_values("p4_score_mean", ascending=False).iloc[0]
    abandon_col = "mean_monthly_abandon_probability"
    if abandon_col not in bl.columns:
        abandon_col = "mean_semiannual_abandon_probability"
    worst_abandon = bl.sort_values(abandon_col, ascending=False).iloc[0]
    return (
        f"En la view {tex_escape(view_label)}, la lectura economica del Horizonte 3 se realiza sin retroalimentar "
        "la utilidad de empresa al optimizador. El mayor score P4 promedio dentro de Black--Litterman se observa en "
        f"el perfil {tex_escape(best['portfolio'])} bajo escenario {tex_escape(best['scenario'])}, mientras que la "
        f"mayor presion mensual de abandono aparece en {tex_escape(worst_abandon['portfolio'])} bajo "
        f"{tex_escape(worst_abandon['scenario'])}. Esta distincion es central: la recomendacion financiera se evalua "
        "por desempeno y estabilidad del portafolio, y la utilidad corporativa queda como consecuencia ex-post del "
        "saldo administrado que permanece activo."
    )


def write_view_report(view: str, meta: Dict[str, str], data: Dict[str, pd.DataFrame]) -> None:
    report_dir = ROOT / view / "informe resultados"
    report_dir.mkdir(parents=True, exist_ok=True)
    make_figures(view, data, report_dir)

    comparison = sort_profile(data["comparison"])
    turnover = sort_profile(data["turnover"][data["turnover"]["window_role"] == "test_p4"])
    monthly_prob = (
        data["monthly"].groupby(["modelo", "scenario", "portfolio"], as_index=False)
        .agg(mean_monthly_abandon_probability=("monthly_abandon_probability", "mean"))
    )
    p4 = data["p4"].merge(monthly_prob, on=["modelo", "scenario", "portfolio"], how="left")
    behavior = data["behavior"].merge(monthly_prob, on=["modelo", "scenario", "portfolio"], how="left")
    p4 = sort_profile(p4)
    behavior = sort_profile(behavior)

    sections: List[str] = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.4cm}",
        rf"\title{{Informe de resultados: {tex_escape(meta['label'])} v1 plus}}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Analisis de resultados fuera de muestra}",
        "La iteracion v1 plus conserva la probabilidad de abandono tipo umbral logistico y explicita una restriccion de ruina: cuando la riqueza actual del cliente llega a cero, el cliente abandona forzosamente la plataforma. La evaluacion fuera de muestra mantiene la separacion de horizontes y compara Black--Litterman calibrado contra Markowitz base en el Horizonte 3.",
        latex_table(
            comparison,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("sharpe_bl_mean", "Sharpe BL", "num3"),
                ("sharpe_mk_mean", "Sharpe MK", "num3"),
                ("mejora_pct_sharpe_mean", "Mejora Sharpe", "pct"),
                ("drawdown_bl_mean", "Drawdown BL", "pct"),
                ("drawdown_mk_mean", "Drawdown MK", "pct"),
                ("pct_recomendado", "BL recomendado", "pct"),
            ],
            f"Comparacion fuera de muestra para {meta['label']}.",
            f"tab:test_{view}",
        ),
        r"\section{Resultados de la dinamica de portafolio}",
        "La dinamica del portafolio se interpreta desde la estabilidad operativa. Turnover bajo indica menor intensidad de transaccion semestral; HHI y peso del sector dominante permiten identificar si el desempeno proviene de una exposicion diversificada o de apuestas concentradas.",
        latex_table(
            turnover,
            [
                ("modelo", "Modelo", "text"),
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("turnover_max", "Turnover max.", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Sector top", "pct"),
            ],
            f"Dinamica de portafolio para {meta['label']}.",
            f"tab:dinamica_{view}",
        ),
        r"\section{Evaluacion Economica Monte Carlo P4 en Horizonte Limpio}",
        p4_interpretation(p4, meta["label"]),
        latex_table(
            p4,
            [
                ("modelo", "Modelo", "text"),
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("terminal_wealth_mean", "Riqueza", "money"),
                ("company_revenue_mean", "Utilidad empresa", "money"),
                ("p_accept_rebalance_mean", "P acepta reb.", "pct"),
                ("mean_weekly_abandon_probability", "P abandono sem.", "pct"),
                ("mean_monthly_abandon_probability", "P abandono mes", "pct"),
                ("final_active_clients_mean", "Clientes finales", "int"),
            ],
            f"Resultados economicos P4 con restriccion de ruina para {meta['label']}.",
            f"tab:p4_{view}",
        ),
        latex_table(
            behavior,
            [
                ("modelo", "Modelo", "text"),
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("p_accept_initial_portfolio", "P inicial", "pct"),
                ("p_accept_rebalance", "P reb.", "pct"),
                ("mean_weekly_abandon_probability", "P sem.", "pct"),
                ("mean_monthly_abandon_probability", "P mes", "pct"),
                ("initial_active_clients_mean", "Clientes iniciales", "int"),
                ("final_active_clients_mean", "Clientes finales", "int"),
            ],
            f"Probabilidades de comportamiento y clientes activos para {meta['label']}.",
            f"tab:behavior_{view}",
        ),
        r"\subsection{Trayectorias semanales y mensuales}",
    ]

    for scenario in SCENARIOS:
        for model in MODELS:
            slug = model_slug(model)
            clean = scenario_label(scenario)
            sections.extend(
                [
                    figure_block(
                        f"clientes_weekly_{scenario}_{slug}.png",
                        f"Clientes activos semanales por perfil, {model}, escenario {clean}.",
                        f"fig:clientes_weekly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"abandono_weekly_{scenario}_{slug}.png",
                        f"Probabilidad semanal de abandono por perfil, {model}, escenario {clean}.",
                        f"fig:abandono_weekly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"aceptacion_weekly_{scenario}_{slug}.png",
                        f"Probabilidad semanal de aceptacion de rebalanceo por perfil, {model}, escenario {clean}.",
                        f"fig:aceptacion_weekly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"ganancia_weekly_{scenario}_{slug}.png",
                        f"Ganancia semanal promedio por perfil, {model}, escenario {clean}.",
                        f"fig:ganancia_weekly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"clientes_monthly_{scenario}_{slug}.png",
                        f"Clientes activos mensuales por perfil, {model}, escenario {clean}.",
                        f"fig:clientes_monthly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"abandono_monthly_{scenario}_{slug}.png",
                        f"Probabilidad mensual de abandono por perfil, {model}, escenario {clean}.",
                        f"fig:abandono_monthly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"aceptacion_monthly_{scenario}_{slug}.png",
                        f"Probabilidad mensual de aceptacion de rebalanceo por perfil, {model}, escenario {clean}.",
                        f"fig:aceptacion_monthly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"ganancia_monthly_{scenario}_{slug}.png",
                        f"Ganancia mensual promedio por perfil, {model}, escenario {clean}.",
                        f"fig:ganancia_monthly_{view}_{scenario}_{slug}",
                    ),
                    figure_block(
                        f"ganancia_semiannual_{scenario}_{slug}.png",
                        f"Ganancia semestral promedio por perfil, {model}, escenario {clean}.",
                        f"fig:ganancia_semiannual_{view}_{scenario}_{slug}",
                    ),
                ]
            )

    sections.extend(
        [
            r"\section{Discusion de Robustez}",
            "La robustez se evalua comparando la persistencia de clientes, la probabilidad de abandono y la ganancia promedio a traves de escenarios con y sin pandemia. El objetivo no es que una view domine en todas las trayectorias, sino que mantenga una relacion defendible entre retorno, riesgo, permanencia de clientes y estabilidad operativa.",
            r"\section{Conclusiones}",
            "La version v1 plus mejora la interpretabilidad del modulo P4 porque separa abandono conductual y ruina economica. La restriccion de ruina evita que un cliente sin capital siga contabilizado como activo, mientras que las trayectorias semanales y mensuales permiten observar si la retencion se explica por ausencia de perdidas, tolerancia del perfil o simplemente por baja volatilidad de corto plazo.",
            r"\end{document}",
        ]
    )

    tex_path = report_dir / f"informe_resultados_{view}.tex"
    tex_path.write_text("\n\n".join(sections), encoding="utf-8")


def comparative_table(rows: Iterable[Dict[str, object]], caption: str, label: str) -> str:
    df = pd.DataFrame(rows)
    return latex_table(
        df,
        [
            ("view", "View", "text"),
            ("scenario", "Escenario", "text"),
            ("modelo", "Modelo", "text"),
            ("turnover_mean", "Turnover", "pct"),
            ("sector_hhi_mean", "HHI sector", "num3"),
            ("monthly_abandon_probability", "P abandono mes", "pct"),
            ("final_active_clients_mean", "Clientes finales", "int"),
            ("mean_active_gain_final", "Ganancia final", "money"),
        ],
        caption,
        label,
    )


def write_comparative_report(all_data: Dict[str, Dict[str, pd.DataFrame]]) -> None:
    rows = []
    for view, data in all_data.items():
        label = VIEWS[view]["label"]
        dyn = data["turnover"][data["turnover"]["window_role"] == "test_p4"]
        monthly = data["monthly"]
        final_month = monthly["month"].max()
        monthly_final = monthly[monthly["month"] == final_month]
        for scenario in SCENARIOS:
            for model in MODELS:
                dyn_s = dyn[(dyn["scenario"] == scenario) & (dyn["modelo"] == model)]
                mon_s = monthly_final[(monthly_final["scenario"] == scenario) & (monthly_final["modelo"] == model)]
                if dyn_s.empty or mon_s.empty:
                    continue
                rows.append(
                    {
                        "view": label,
                        "scenario": scenario,
                        "modelo": model,
                        "turnover_mean": dyn_s["turnover_mean"].mean(),
                        "sector_hhi_mean": dyn_s["sector_hhi_mean"].mean(),
                        "monthly_abandon_probability": mon_s["monthly_abandon_probability"].mean(),
                        "final_active_clients_mean": mon_s["active_clients_mean"].mean(),
                        "mean_active_gain_final": mon_s["mean_active_gain"].mean(),
                    }
                )
    comp = pd.DataFrame(rows)
    comp.to_csv(ROOT / "comparativo_views_v1_plus.csv", index=False)
    body = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.4cm}",
        r"\title{Informe comparativo views v1 plus}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Resultados de la Dinamica del Portafolio}",
        "La comparacion entre views se concentra en estabilidad operativa, concentracion sectorial y persistencia de clientes. La restriccion de ruina queda incorporada de forma homogenea en todas las simulaciones, por lo que las diferencias observadas responden a la view calibrada y no a cambios en la regla de abandono.",
        comparative_table(
            rows,
            "Sintesis comparativa de dinamica, abandono y ganancia final por view.",
            "tab:comparativo_views_v1_plus",
        ),
        r"\section{Discusion comparativa}",
        "Una view es preferible cuando combina bajo turnover, menor concentracion sectorial, abandono mensual controlado y ganancia final positiva en perfiles coherentes con su tolerancia al riesgo. Bajo esta lectura, las views de momentum deben evaluarse con especial atencion en perfiles agresivos, porque pueden elevar la ganancia esperada pero tambien amplificar concentracion y sensibilidad a perdidas acumuladas. La view macro de desempleo funciona como referencia defensiva, ya que tiende a expresar una senal mas agregada y menos dependiente de rankings individuales de activos.",
        r"\section{Conclusiones generales y recomendaciones}",
        "La recomendacion final debe priorizar la view que entregue resiliencia dinamica, no solo mayor riqueza terminal. Para presentacion ante comision, el criterio mas defendible es reportar por perfil la combinacion de Sharpe fuera de muestra, turnover, concentracion sectorial, abandono mensual y clientes finales. Esta arquitectura permite justificar una recomendacion segmentada y evita que una view sea elegida exclusivamente por un resultado economico puntual del Horizonte 3.",
        r"\end{document}",
    ]
    (ROOT / "informe_comparativo_views_v1_plus.tex").write_text("\n\n".join(body), encoding="utf-8")


def main() -> None:
    all_data = {}
    for view, meta in VIEWS.items():
        data = load_view(view)
        all_data[view] = data
        write_view_report(view, meta, data)
    write_comparative_report(all_data)
    print(f"Informes y figuras generados en {ROOT}")


if __name__ == "__main__":
    main()
