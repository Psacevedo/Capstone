from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent

VIEWS: Dict[str, Dict[str, str]] = {
    "desempleo_macro": {
        "label": "Desempleo macro",
        "short": "Desempleo",
        "script": "validacion_view_desempleo_macro.py",
    },
    "momentum_general": {
        "label": "Momentum general",
        "short": "Momentum general",
        "script": "validacion_view_momentum_general.py",
    },
    "momentum_top_marketcap_6m": {
        "label": "Momentum top market-cap 6M",
        "short": "Top market-cap 6M",
        "script": "validacion_view_momentum_top_marketcap_6m.py",
    },
    "momentum_top_bottom_1y": {
        "label": "Momentum top/bottom 1Y",
        "short": "Top/bottom 1Y",
        "script": "validacion_view_momentum_top_bottom_1y.py",
    },
}

PROFILE_ORDER = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]
SCENARIO_LABELS = {"sin_pandemia": "Sin pandemia", "con_pandemia": "Con pandemia"}
MODEL_COLORS = {"BL calibrado": (32, 92, 132), "Markowitz base": (146, 86, 44)}


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


def latex_table(
    df: pd.DataFrame,
    columns: List[Tuple[str, str, str]],
    caption: str,
    label: str,
    resize: bool = True,
) -> str:
    header = " & ".join(tex_escape(h) for _, h, _ in columns) + r" \\"
    body_lines = []
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
                cells.append(str(int(round(float(row[col])))) if pd.notna(row[col]) else "---")
            else:
                cells.append(tex_escape(row[col]))
        body_lines.append(" & ".join(cells) + r" \\")

    tabular = "\n".join(
        [
            r"\begin{tabular}{l" + "r" * (len(columns) - 1) + "}",
            r"\toprule",
            header,
            r"\midrule",
            *body_lines,
            r"\bottomrule",
            r"\end{tabular}",
        ]
    )
    if resize:
        tabular = "\\resizebox{\\textwidth}{!}{%\n" + tabular + "\n}"
    return "\n".join(
        [
            r"\begin{table}[H]",
            r"\centering",
            tabular,
            f"\\caption{{{tex_escape(caption)}}}",
            f"\\label{{{label}}}",
            r"\end{table}",
            "",
        ]
    )


def ensure_report_dirs(view_dir: Path) -> Tuple[Path, Path]:
    report_dir = view_dir / "informe resultados"
    figures_dir = report_dir / "figuras"
    figures_dir.mkdir(parents=True, exist_ok=True)
    return report_dir, figures_dir


def font(size: int = 16) -> ImageFont.ImageFont:
    for name in ["arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_grouped_bar(
    rows: pd.DataFrame,
    out_path: Path,
    title: str,
    value_cols: List[Tuple[str, str, Tuple[int, int, int]]],
    value_format: str = "num",
) -> None:
    width, height = 1200, 680
    margin_l, margin_r, margin_t, margin_b = 105, 50, 90, 135
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    f_title, f_axis, f_small = font(24), font(15), font(13)
    draw.text((margin_l, 30), title, fill=(30, 30, 30), font=f_title)
    plot_w, plot_h = width - margin_l - margin_r, height - margin_t - margin_b
    y0 = height - margin_b
    draw.line((margin_l, margin_t, margin_l, y0), fill=(70, 70, 70), width=2)
    draw.line((margin_l, y0, width - margin_r, y0), fill=(70, 70, 70), width=2)
    vmax = max([float(rows[col].max()) for col, _, _ in value_cols] + [1e-9])
    if value_format == "pct":
        vmax = max(vmax, 0.05)
    vmax *= 1.15
    for i in range(6):
        value = vmax * i / 5
        y = y0 - plot_h * i / 5
        draw.line((margin_l - 5, y, width - margin_r, y), fill=(230, 230, 230), width=1)
        label = f"{value * 100:.0f}%" if value_format == "pct" else f"{value:.2f}"
        draw.text((20, y - 8), label, fill=(80, 80, 80), font=f_small)

    n = len(rows)
    group_w = plot_w / max(n, 1)
    bar_w = min(34, group_w / (len(value_cols) + 1.5))
    for i, (_, row) in enumerate(rows.iterrows()):
        x_center = margin_l + group_w * (i + 0.5)
        start = x_center - (len(value_cols) * bar_w + (len(value_cols) - 1) * 5) / 2
        for j, (col, _, color) in enumerate(value_cols):
            val = float(row[col])
            x = start + j * (bar_w + 5)
            y = y0 - (val / vmax) * plot_h
            draw.rectangle((x, y, x + bar_w, y0), fill=color)
        label = str(row["portfolio"]).replace("Muy ", "M. ")
        draw.text((x_center - 45, y0 + 15), label, fill=(40, 40, 40), font=f_small)

    lx = margin_l
    for _, label, color in value_cols:
        draw.rectangle((lx, height - 55, lx + 18, height - 37), fill=color)
        draw.text((lx + 25, height - 58), label, fill=(45, 45, 45), font=f_axis)
        lx += 230
    img.save(out_path)


def draw_scatter_p4(df: pd.DataFrame, out_path: Path, title: str) -> None:
    width, height = 1100, 650
    margin_l, margin_r, margin_t, margin_b = 105, 70, 90, 95
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    f_title, f_axis, f_small = font(24), font(15), font(12)
    draw.text((margin_l, 30), title, fill=(30, 30, 30), font=f_title)
    x = df["terminal_wealth_mean"].astype(float)
    y = df["company_revenue_mean"].astype(float)
    xmin, xmax = x.min() * 0.98, x.max() * 1.02
    ymin, ymax = y.min() * 0.95, y.max() * 1.05
    plot_w, plot_h = width - margin_l - margin_r, height - margin_t - margin_b
    x0, y0 = margin_l, height - margin_b
    draw.line((x0, margin_t, x0, y0), fill=(70, 70, 70), width=2)
    draw.line((x0, y0, width - margin_r, y0), fill=(70, 70, 70), width=2)
    for _, row in df.iterrows():
        px = x0 + (float(row["terminal_wealth_mean"]) - xmin) / max(xmax - xmin, 1e-9) * plot_w
        py = y0 - (float(row["company_revenue_mean"]) - ymin) / max(ymax - ymin, 1e-9) * plot_h
        color = MODEL_COLORS.get(row["modelo"], (60, 60, 60))
        draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill=color)
        draw.text((px + 9, py - 7), str(row["portfolio"]).replace("Muy ", "M. "), fill=(35, 35, 35), font=f_small)
    draw.text((margin_l + plot_w / 2 - 110, height - 45), "Riqueza terminal media", fill=(45, 45, 45), font=f_axis)
    draw.text((12, margin_t + plot_h / 2), "Utilidad empresa", fill=(45, 45, 45), font=f_axis)
    lx = width - margin_r - 320
    for model, color in MODEL_COLORS.items():
        draw.ellipse((lx, 50, lx + 14, 64), fill=color)
        draw.text((lx + 22, 46), model, fill=(45, 45, 45), font=f_axis)
        lx += 160
    img.save(out_path)


def draw_comparative_bar(df: pd.DataFrame, col: str, out_path: Path, title: str, pct: bool = False) -> None:
    rows = df.sort_values(col, ascending=False).copy()
    rows["portfolio"] = rows["view_short"]
    draw_grouped_bar(
        rows,
        out_path,
        title,
        [(col, col.replace("_", " "), (36, 103, 141))],
        "pct" if pct else "num",
    )


def copy_behavior_figures(outputs: Path, figures_dir: Path) -> None:
    behavior = outputs / "behavior"
    for name in [
        "fig_probabilidades_con_pandemia.png",
        "fig_probabilidades_sin_pandemia.png",
        "fig_clientes_con_pandemia.png",
        "fig_clientes_sin_pandemia.png",
    ]:
        src = behavior / name
        if src.exists():
            shutil.copy2(src, figures_dir / name)


def load_view_data(view_key: str) -> Dict[str, pd.DataFrame]:
    out = ROOT / view_key / "outputs"
    return {
        "config": read_csv(out / "03_configuracion_congelada.csv"),
        "comparison": read_csv(out / "test_p4" / "test_limpio_comparacion_resumen.csv"),
        "p4": read_csv(out / "test_p4" / "p4_test_limpio_resumen.csv"),
        "behavior": read_csv(out / "behavior" / "behavior_probabilities_clients_summary.csv"),
        "turnover": read_csv(out / "portfolio_dynamics" / "turnover_summary.csv"),
        "composition": read_csv(out / "portfolio_dynamics" / "composition_stability.csv"),
        "sector": read_csv(out / "portfolio_dynamics" / "sector_return_concentration_summary.csv"),
    }


def scenario_profile_sort(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["scenario_order"] = result["scenario"].map({"sin_pandemia": 0, "con_pandemia": 1})
    result["profile_order"] = result["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return result.sort_values(["scenario_order", "profile_order"]).drop(columns=["scenario_order", "profile_order"])


def make_view_figures(view_key: str, data: Dict[str, pd.DataFrame], figures_dir: Path) -> None:
    comparison = scenario_profile_sort(data["comparison"])
    turnover = scenario_profile_sort(data["turnover"][(data["turnover"]["window_role"] == "test_p4")])
    p4 = scenario_profile_sort(data["p4"])
    for scenario in ["sin_pandemia", "con_pandemia"]:
        comp_s = comparison[comparison["scenario"] == scenario].copy()
        comp_s["portfolio"] = pd.Categorical(comp_s["portfolio"], PROFILE_ORDER, ordered=True)
        comp_s = comp_s.sort_values("portfolio")
        draw_grouped_bar(
            comp_s,
            figures_dir / f"sharpe_{scenario}.png",
            f"Sharpe fuera de muestra - {SCENARIO_LABELS[scenario]}",
            [
                ("sharpe_bl_mean", "BL calibrado", MODEL_COLORS["BL calibrado"]),
                ("sharpe_mk_mean", "Markowitz", MODEL_COLORS["Markowitz base"]),
            ],
            "num",
        )
        turn_s = turnover[turnover["scenario"] == scenario].copy()
        pivot = (
            turn_s.pivot_table(index="portfolio", columns="modelo", values="turnover_mean", aggfunc="mean")
            .reindex(PROFILE_ORDER)
            .reset_index()
            .fillna(0)
        )
        draw_grouped_bar(
            pivot,
            figures_dir / f"turnover_{scenario}.png",
            f"Turnover semestral medio - {SCENARIO_LABELS[scenario]}",
            [
                ("BL calibrado", "BL calibrado", MODEL_COLORS["BL calibrado"]),
                ("Markowitz base", "Markowitz", MODEL_COLORS["Markowitz base"]),
            ],
            "pct",
        )
        p4_s = p4[p4["scenario"] == scenario].copy()
        draw_scatter_p4(
            p4_s,
            figures_dir / f"p4_riqueza_utilidad_{scenario}.png",
            f"P4: riqueza y utilidad ex-post - {SCENARIO_LABELS[scenario]}",
        )
    copy_behavior_figures(ROOT / view_key / "outputs", figures_dir)


def config_sentence(config: pd.Series) -> str:
    parts = [
        f"familia {tex_escape(config.get('family', '---'))}",
        f"lookback {int(config.get('lookback_days', 0))} días",
        f"long/short {int(config.get('long_short_size', 0))}",
        f"ponderación {tex_escape(config.get('p_weighting', '---'))}",
        f"q\\_scale={fmt_num(config.get('q_scale'), 1)}",
        f"confianza={fmt_pct(config.get('confidence'), 0)}",
        f"$\\tau$={fmt_num(config.get('tau'), 3)}",
    ]
    return ", ".join(parts)


def interpretation_for_view(view_key: str, data: Dict[str, pd.DataFrame]) -> str:
    comp = data["comparison"].copy()
    bl_turn = data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
    bl_sector = bl_turn["sector_hhi_mean"].mean()
    turnover_mean = bl_turn["turnover_mean"].mean()
    pct_rec = comp["pct_recomendado"].mean()
    sharpe_gain = comp["mejora_pct_sharpe_mean"].mean()
    if turnover_mean < 0.10 and bl_sector < 0.18:
        dynamics = "La señal produce una dinámica operacionalmente estable: bajo turnover, alta diversificación efectiva y una concentración sectorial acotada."
    elif turnover_mean < 0.22:
        dynamics = "La señal mantiene una intensidad transaccional moderada, aunque requiere monitorear la concentración sectorial en perfiles de mayor riesgo."
    else:
        dynamics = "La señal mejora algunos frentes de retorno, pero lo hace a costa de mayor rotación y de una concentración más visible de la exposición."
    return (
        f"En promedio, la mejora porcentual de Sharpe frente a Markowitz fue {fmt_pct(sharpe_gain)}, "
        f"con una fracción recomendada media de {fmt_pct(pct_rec)} sobre los cruces escenario-perfil. "
        f"{dynamics}"
    )


def profile_conclusion_table(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    comp = data["comparison"].copy()
    turn = data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
    merged = comp.merge(
        turn[["scenario", "portfolio", "turnover_mean", "sector_hhi_mean", "n_effective_assets_mean"]],
        on=["scenario", "portfolio"],
        how="left",
    )
    out = (
        merged.groupby("portfolio", as_index=False)
        .agg(
            mejora_sharpe=("mejora_pct_sharpe_mean", "mean"),
            pct_recomendado=("pct_recomendado", "mean"),
            turnover=("turnover_mean", "mean"),
            hhi_sector=("sector_hhi_mean", "mean"),
            n_efectivo=("n_effective_assets_mean", "mean"),
        )
        .assign(
            recomendacion=lambda x: np.where(
                (x["pct_recomendado"] >= 0.50) & (x["turnover"] <= 0.25),
                "Recomendable",
                np.where(x["mejora_sharpe"] > 0, "Condicional", "No preferente"),
            )
        )
    )
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values("profile_order").drop(columns="profile_order")


def write_view_report(view_key: str) -> None:
    info = VIEWS[view_key]
    view_dir = ROOT / view_key
    report_dir, figures_dir = ensure_report_dirs(view_dir)
    data = load_view_data(view_key)
    make_view_figures(view_key, data, figures_dir)

    config = data["config"].iloc[0]
    comparison = scenario_profile_sort(data["comparison"])
    turn_bl = scenario_profile_sort(
        data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
    )
    p4_bl = scenario_profile_sort(data["p4"][data["p4"]["modelo"] == "BL calibrado"])
    behavior_bl = scenario_profile_sort(data["behavior"][data["behavior"]["modelo"] == "BL calibrado"])
    p4_behavior = p4_bl.merge(
        behavior_bl[
            [
                "scenario",
                "portfolio",
                "p_accept_initial_portfolio",
                "p_accept_rebalance",
                "mean_weekly_abandon_probability",
                "mean_semiannual_abandon_probability",
                "initial_active_clients_mean",
                "final_active_clients_mean",
                "client_retention_rate",
            ]
        ],
        on=["scenario", "portfolio"],
        how="left",
    )
    for target, candidates in {
        "p_accept_initial_portfolio": ["p_accept_initial_portfolio", "p_accept_initial_portfolio_mean"],
        "p_accept_rebalance": ["p_accept_rebalance", "p_accept_rebalance_mean"],
        "mean_weekly_abandon_probability": [
            "mean_weekly_abandon_probability",
            "mean_weekly_abandon_probability_x",
            "mean_weekly_abandon_probability_y",
        ],
        "mean_semiannual_abandon_probability": [
            "mean_semiannual_abandon_probability",
            "mean_semiannual_abandon_probability_x",
            "mean_semiannual_abandon_probability_y",
        ],
        "initial_active_clients_mean": ["initial_active_clients_mean", "initial_active_clients_mean_x", "initial_active_clients_mean_y"],
        "final_active_clients_mean": ["final_active_clients_mean", "final_active_clients_mean_x", "final_active_clients_mean_y"],
    }.items():
        if target not in p4_behavior.columns:
            available = [col for col in candidates if col in p4_behavior.columns]
            if available:
                p4_behavior[target] = p4_behavior[available].bfill(axis=1).iloc[:, 0]
    conclusions = profile_conclusion_table(data)
    label = info["label"]

    tex = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage{amsmath}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{geometry}",
        r"\usepackage{array}",
        r"\geometry{margin=2.5cm}",
        r"\setlength{\parskip}{0.65em}",
        r"\setlength{\parindent}{0pt}",
        f"\\title{{Informe de resultados: {tex_escape(label)}}}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        "",
        r"\section{Análisis de resultados fuera de muestra}",
        (
            f"Esta iteración evalúa la view \\textit{{{tex_escape(label)}}} dentro de la misma arquitectura de tres horizontes "
            "y ventanas móviles utilizada en la validación robustecida. La etapa de calibración no vuelve a competir contra "
            "otras familias de views; en cambio, fija la familia analizada y calibra secuencialmente su estructura interna "
            f"hasta congelar la configuración final: {config_sentence(config)}."
        ),
        interpretation_for_view(view_key, data),
        latex_table(
            comparison,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("sharpe_bl_mean", "Sharpe BL", "num3"),
                ("sharpe_mk_mean", "Sharpe MK", "num3"),
                ("mejora_pct_sharpe_mean", "Mejora Sharpe", "pct"),
                ("drawdown_bl_mean", "DD BL", "pct"),
                ("drawdown_mk_mean", "DD MK", "pct"),
                ("pct_recomendado", "% ventanas recomendado", "pct"),
            ],
            f"Comparación fuera de muestra en horizonte limpio para {label}.",
            f"tab:{view_key}:resultados_oos",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.92\textwidth]{figuras/sharpe_sin_pandemia.png}",
        f"\\caption{{Sharpe fuera de muestra sin pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:sharpe_sin}}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.92\textwidth]{figuras/sharpe_con_pandemia.png}",
        f"\\caption{{Sharpe fuera de muestra con pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:sharpe_con}}",
        r"\end{figure}",
        "",
        r"\section{Resultados de la dinámica de portafolio}",
        (
            "La dinámica del portafolio se analiza como una condición de implementabilidad. Un modelo puede mejorar el Sharpe "
            "fuera de muestra, pero si lo hace mediante rotación excesiva, concentración sectorial o inestabilidad de pesos, "
            "su recomendación debe ser tratada como condicional."
        ),
        latex_table(
            turn_bl,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("pct_turnover_gt_20", "Turn. >20%", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Peso sector líder", "pct"),
            ],
            f"Dinámica de portafolio de Black-Litterman calibrado para {label}.",
            f"tab:{view_key}:dinamica",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.92\textwidth]{figuras/turnover_sin_pandemia.png}",
        f"\\caption{{Turnover semestral medio sin pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:turnover_sin}}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.92\textwidth]{figuras/turnover_con_pandemia.png}",
        f"\\caption{{Turnover semestral medio con pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:turnover_con}}",
        r"\end{figure}",
        "",
        r"\section{Evaluación Económica Monte Carlo P4 en Horizonte Limpio}",
        (
            "La simulación Monte Carlo P4 se ejecuta únicamente en el Horizonte 3. Por diseño, la utilidad de la empresa es "
            "un resultado ex-post asociado al saldo administrado activo, calculado con una tasa de 0,5\\% mensual, y no entra en el optimizador de portafolios. En esta "
            "iteración se reportan explícitamente la probabilidad de aceptación inicial, la probabilidad de aceptación del "
            "rebalanceo, la probabilidad semestral de abandono y el número de clientes activos al final de las 260 semanas. "
            "La probabilidad semestral se calcula desde la probabilidad semanal simulada como $1-(1-p_{sem})^{26}$."
        ),
        latex_table(
            p4_behavior,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("terminal_wealth_mean", "Riqueza", "money"),
                ("company_revenue_mean", "Utilidad empresa", "money"),
                ("p_accept_initial_portfolio", "P acepta inicial", "pct"),
                ("p_accept_rebalance", "P acepta reb.", "pct"),
                ("mean_semiannual_abandon_probability", "P abandono sem.", "pct"),
                ("initial_active_clients_mean", "Clientes iniciales", "int"),
                ("final_active_clients_mean", "Clientes finales", "int"),
            ],
            f"Resultados P4 y comportamiento de clientes para {label}.",
            f"tab:{view_key}:p4",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.88\textwidth]{figuras/p4_riqueza_utilidad_sin_pandemia.png}",
        f"\\caption{{Relación entre riqueza terminal y utilidad ex-post sin pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:p4_sin}}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.88\textwidth]{figuras/p4_riqueza_utilidad_con_pandemia.png}",
        f"\\caption{{Relación entre riqueza terminal y utilidad ex-post con pandemia para {tex_escape(label)}.}}",
        f"\\label{{fig:{view_key}:p4_con}}",
        r"\end{figure}",
        "",
        r"\section{Discusión de Robustez}",
        (
            f"El contraste con y sin pandemia permite separar rendimiento promedio de resiliencia. Para {tex_escape(label)}, "
            "la lectura relevante no es si Black-Litterman domina todos los cruces, sino si la señal conserva un balance "
            "defendible entre Sharpe, drawdown, estabilidad de composición y comportamiento económico de los clientes. "
            "Los perfiles con mejora financiera pero rotación alta deben considerarse de mayor costo operativo y menor "
            "robustez implementable."
        ),
        "",
        r"\section{Conclusiones}",
        latex_table(
            conclusions,
            [
                ("portfolio", "Perfil", "text"),
                ("mejora_sharpe", "Mejora Sharpe media", "pct"),
                ("pct_recomendado", "% recomendado", "pct"),
                ("turnover", "Turnover", "pct"),
                ("hhi_sector", "HHI sector", "num3"),
                ("n_efectivo", "N efectivo", "num2"),
                ("recomendacion", "Lectura", "text"),
            ],
            f"Recomendación segmentada para {label}.",
            f"tab:{view_key}:conclusiones",
        ),
        (
            "En síntesis, la recomendación metodológica de esta view debe leerse por perfil de riesgo y no como una regla "
            "única. Cuando la mejora de Sharpe se sostiene junto con baja rotación y baja concentración, la señal es apta "
            "para recomendación directa. Cuando la mejora viene acompañada de turnover elevado o concentración sectorial, "
            "su uso debe limitarse a perfiles que toleren cambios frecuentes y mayor exposición táctica."
        ),
        r"\end{document}",
    ]
    (report_dir / "informe_resultados.tex").write_text("\n".join(tex), encoding="utf-8")


def comparative_rows() -> pd.DataFrame:
    rows = []
    for view_key, info in VIEWS.items():
        data = load_view_data(view_key)
        turn = data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
        comp = data["composition"][(data["composition"]["modelo"] == "BL calibrado") & (data["composition"]["window_role"] == "test_p4")]
        sector = data["sector"][(data["sector"]["modelo"] == "BL calibrado") & (data["sector"]["window_role"] == "test_p4")]
        comparison = data["comparison"]
        p4 = data["p4"][data["p4"]["modelo"] == "BL calibrado"]
        cfg = data["config"].iloc[0]
        rows.append(
            {
                "view_key": view_key,
                "view": info["label"],
                "view_short": info["short"],
                "config_id": cfg.get("config_id", "---"),
                "family": cfg.get("family", "---"),
                "turnover_mean": turn["turnover_mean"].mean(),
                "turnover_gt20_mean": turn["pct_turnover_gt_20"].mean(),
                "n_effective_assets_mean": turn["n_effective_assets_mean"].mean(),
                "sector_hhi_mean": turn["sector_hhi_mean"].mean(),
                "top_sector_weight_mean": turn["top_sector_weight_mean"].mean(),
                "distance_l1_initial_final": comp["distance_l1_initial_final"].mean(),
                "top10_overlap_initial_final": comp["top10_overlap_initial_final"].mean(),
                "top3_sector_share_abs_return": sector["top3_sector_share_abs_return"].mean(),
                "sharpe_gain_mean": comparison["mejora_pct_sharpe_mean"].mean(),
                "pct_recomendado_mean": comparison["pct_recomendado"].mean(),
                "mean_semiannual_abandon_probability": p4["mean_semiannual_abandon_probability"].mean()
                if "mean_semiannual_abandon_probability" in p4.columns
                else np.nan,
                "terminal_wealth_mean": p4["terminal_wealth_mean"].mean(),
                "company_revenue_mean": p4["company_revenue_mean"].mean(),
                "withdrawal_rate_mean": p4["withdrawal_rate_mean"].mean(),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "comparativo_views_resumen.csv", index=False)
    return df


def write_comparative_report() -> None:
    figures_dir = ROOT / "figuras"
    figures_dir.mkdir(exist_ok=True)
    df = comparative_rows()
    draw_comparative_bar(df, "turnover_mean", figures_dir / "comparativo_turnover_views.png", "Turnover promedio por view", pct=True)
    draw_comparative_bar(
        df,
        "sector_hhi_mean",
        figures_dir / "comparativo_hhi_sector_views.png",
        "Concentración sectorial promedio por view",
        pct=False,
    )
    draw_comparative_bar(
        df,
        "n_effective_assets_mean",
        figures_dir / "comparativo_n_efectivo_views.png",
        "Número efectivo de activos por view",
        pct=False,
    )

    duplicated = df[df.duplicated(["turnover_mean", "sector_hhi_mean", "sharpe_gain_mean"], keep=False)]
    convergence_note = ""
    if not duplicated.empty:
        names = ", ".join(tex_escape(v) for v in duplicated["view"].tolist())
        convergence_note = (
            f"Un resultado relevante de la calibración es la convergencia empírica entre {names}: "
            "ambas iteraciones terminan seleccionando la misma estructura congelada de market-cap momentum, por lo que "
            "sus métricas de test limpio y dinámica de portafolio coinciden."
        )

    best_stability = df.sort_values(["turnover_mean", "sector_hhi_mean"], ascending=True).iloc[0]
    best_perf = df.sort_values(["sharpe_gain_mean", "pct_recomendado_mean"], ascending=False).iloc[0]
    tex = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage{amsmath}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.5cm}",
        r"\setlength{\parskip}{0.65em}",
        r"\setlength{\parindent}{0pt}",
        r"\title{Informe comparativo de views Black-Litterman}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Objetivo del contraste}",
        (
            "Este informe compara las cuatro familias de views evaluadas bajo la misma arquitectura de tres horizontes, "
            "ventanas móviles y test limpio P4. El foco principal es la dinámica del portafolio, porque esta dimensión "
            "determina si una mejora financiera puede implementarse sin inducir rotación, concentración o inestabilidad "
            "excesiva en la recomendación."
        ),
        r"\section{Resultados de la dinámica del portafolio}",
        latex_table(
            df,
            [
                ("view", "View", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("turnover_gt20_mean", "Turn. >20%", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Peso sector líder", "pct"),
                ("distance_l1_initial_final", "Drift L1", "num3"),
                ("top10_overlap_initial_final", "Overlap top-10", "pct"),
                ("top3_sector_share_abs_return", "Top-3 retorno sector", "pct"),
            ],
            "Comparación agregada de dinámica de portafolio por view.",
            "tab:comparativo:dinamica",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.86\textwidth]{figuras/comparativo_turnover_views.png}",
        r"\caption{Turnover promedio en el horizonte de test limpio por view.}",
        r"\label{fig:comparativo:turnover}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.86\textwidth]{figuras/comparativo_hhi_sector_views.png}",
        r"\caption{Concentración sectorial promedio en el horizonte de test limpio por view.}",
        r"\label{fig:comparativo:hhi}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.86\textwidth]{figuras/comparativo_n_efectivo_views.png}",
        r"\caption{Número efectivo de activos promedio en el horizonte de test limpio por view.}",
        r"\label{fig:comparativo:neff}",
        r"\end{figure}",
        r"\section{Lectura financiera y económica}",
        latex_table(
            df,
            [
                ("view", "View", "text"),
                ("sharpe_gain_mean", "Mejora Sharpe", "pct"),
                ("pct_recomendado_mean", "% recomendado", "pct"),
                ("mean_semiannual_abandon_probability", "P abandono sem.", "pct"),
                ("terminal_wealth_mean", "Riqueza P4", "money"),
                ("company_revenue_mean", "Utilidad ex-post", "money"),
                ("withdrawal_rate_mean", "Tasa retiro", "pct"),
            ],
            "Resumen financiero y económico agregado por view.",
            "tab:comparativo:p4",
        ),
        (
            "La comparación muestra que la view con mejor estabilidad operacional no necesariamente coincide con la de mayor "
            "impulso de Sharpe. En particular, "
            f"{tex_escape(best_stability['view'])} presenta el menor costo dinámico agregado, mientras que "
            f"{tex_escape(best_perf['view'])} entrega la señal financiera promedio más intensa. "
            "Esta diferencia es central para la recomendación final: FinPUC no solo debe elegir la mayor rentabilidad esperada, "
            "sino una política que pueda sostenerse bajo rebalanceos semestrales y distintos regímenes de mercado."
        ),
        convergence_note,
        r"\section{Conclusiones generales y recomendaciones}",
        (
            f"Como recomendación base para una implementación robusta, {tex_escape(best_stability['view'])} es la view más defendible "
            "cuando se prioriza estabilidad, baja rotación y diversificación sectorial. Para perfiles más tolerantes a riesgo, "
            f"{tex_escape(best_perf['view'])} puede considerarse una alternativa táctica si el comité acepta el mayor costo dinámico "
            "que aparece en la rotación y en la concentración de retornos."
        ),
        (
            "Las views de momentum basadas en market-cap deben presentarse como señales de uso condicionado: su calibración puede "
            "identificar estructuras con mejora parcial, pero la dinámica del portafolio revela mayor sensibilidad a cambios de "
            "régimen. Por ello, su incorporación final debería limitarse a perfiles que toleren más rebalanceo y exposición "
            "sectorial, o bien usarse como módulo complementario y no como recomendación dominante para toda la base de clientes."
        ),
        r"\end{document}",
    ]
    (ROOT / "informe_comparativo_views.tex").write_text("\n".join(tex), encoding="utf-8")


def main() -> None:
    for view_key in VIEWS:
        write_view_report(view_key)
    write_comparative_report()


if __name__ == "__main__":
    main()
