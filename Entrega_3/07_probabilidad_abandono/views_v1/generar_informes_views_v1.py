from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent

VIEWS: Dict[str, Dict[str, str]] = {
    "desempleo_macro_v1": {"label": "Desempleo macro", "short": "Desempleo"},
    "momentum_general_v1": {"label": "Momentum general", "short": "Momentum general"},
    "momentum_top_bottom_1y_v1": {"label": "Momentum top/bottom 1Y", "short": "Top/bottom 1Y"},
    "momentum_top_marketcap_6m_v1": {"label": "Momentum top market-cap 6M", "short": "Top market-cap 6M"},
}

PROFILE_ORDER = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]
SCENARIO_ORDER = {"sin_pandemia": 0, "con_pandemia": 1}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def tex_escape(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    for old, new in {
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
    }.items():
        text = text.replace(old, new)
    return text


def fmt_pct(value: object, digits: int = 1) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value) * 100:.{digits}f}\\%"


def fmt_num(value: object, digits: int = 3) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value):.{digits}f}"


def fmt_money(value: object) -> str:
    if pd.isna(value):
        return "---"
    return f"{float(value):,.0f}".replace(",", ".")


def sort_sp(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["scenario_order"] = out["scenario"].map(SCENARIO_ORDER)
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values(["scenario_order", "profile_order"]).drop(columns=["scenario_order", "profile_order"])


def table(df: pd.DataFrame, cols: List[Tuple[str, str, str]], caption: str, label: str) -> str:
    header = " & ".join(tex_escape(h) for _, h, _ in cols) + r" \\"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col, _, kind in cols:
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
        rows.append(" & ".join(cells) + r" \\")
    tabular = "\n".join(
        [
            r"\begin{tabular}{l" + "r" * (len(cols) - 1) + "}",
            r"\toprule",
            header,
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
        ]
    )
    return "\n".join(
        [
            r"\begin{table}[H]",
            r"\centering",
            r"\resizebox{\textwidth}{!}{%",
            tabular,
            r"}",
            f"\\caption{{{tex_escape(caption)}}}",
            f"\\label{{{label}}}",
            r"\end{table}",
            "",
        ]
    )


def load(view: str) -> Dict[str, pd.DataFrame]:
    out = ROOT / view / "outputs"
    return {
        "config": read_csv(out / "03_configuracion_congelada.csv"),
        "comparison": read_csv(out / "test_p4" / "test_limpio_comparacion_resumen.csv"),
        "turnover": read_csv(out / "portfolio_dynamics" / "turnover_summary.csv"),
        "p4": read_csv(out / "test_p4" / "p4_test_limpio_resumen.csv"),
        "behavior": read_csv(out / "behavior" / "behavior_probabilities_clients_summary.csv"),
        "composition": read_csv(out / "portfolio_dynamics" / "composition_stability.csv"),
        "sector": read_csv(out / "portfolio_dynamics" / "sector_return_concentration_summary.csv"),
    }


def copy_figures(view: str, report_dir: Path) -> None:
    fig_dir = report_dir / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)
    src_dir = ROOT / view / "outputs" / "behavior"
    for name in [
        "fig_probabilidades_con_pandemia.png",
        "fig_probabilidades_sin_pandemia.png",
        "fig_clientes_con_pandemia.png",
        "fig_clientes_sin_pandemia.png",
    ]:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, fig_dir / name)


def p4_behavior(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    p4 = data["p4"][data["p4"]["modelo"] == "BL calibrado"].copy()
    beh = data["behavior"][data["behavior"]["modelo"] == "BL calibrado"].copy()
    merged = p4.merge(
        beh[
            [
                "scenario",
                "portfolio",
                "p_accept_rebalance",
                "mean_weekly_abandon_probability",
                "mean_semiannual_abandon_probability",
                "realized_abandon_rate_260w",
                "client_retention_rate",
            ]
        ],
        on=["scenario", "portfolio"],
        how="left",
    )
    for target in [
        "p_accept_rebalance",
        "mean_weekly_abandon_probability",
        "mean_semiannual_abandon_probability",
        "realized_abandon_rate_260w",
    ]:
        if target not in merged.columns:
            candidates = [c for c in merged.columns if c.startswith(target)]
            if candidates:
                merged[target] = merged[candidates].bfill(axis=1).iloc[:, 0]
    return sort_sp(merged)


def config_text(data: Dict[str, pd.DataFrame]) -> str:
    cfg = data["config"].iloc[0]
    return (
        f"familia {tex_escape(cfg.get('family', '---'))}, lookback {int(cfg.get('lookback_days', 0))} dias, "
        f"ponderacion {tex_escape(cfg.get('p_weighting', '---'))}, q\\_scale={fmt_num(cfg.get('q_scale'), 1)}, "
        f"confianza={fmt_pct(cfg.get('confidence'), 0)} y $\\tau$={fmt_num(cfg.get('tau'), 3)}"
    )


def conclusions_table(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    p4 = p4_behavior(data)
    out = (
        p4.groupby("portfolio", as_index=False)
        .agg(
            riqueza=("terminal_wealth_mean", "mean"),
            utilidad=("company_revenue_mean", "mean"),
            abandono_sem=("mean_semiannual_abandon_probability", "mean"),
            retiro_260w=("realized_abandon_rate_260w", "mean"),
            retencion=("client_retention_rate", "mean"),
            clientes_finales=("final_active_clients_mean", "mean"),
        )
    )
    out["lectura"] = np.where(
        out["retencion"] >= 0.85,
        "Estable",
        np.where(out["retencion"] >= 0.60, "Intermedia", "Critica"),
    )
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values("profile_order").drop(columns="profile_order")


def write_view_report(view: str) -> None:
    info = VIEWS[view]
    data = load(view)
    report_dir = ROOT / view / "informe resultados"
    report_dir.mkdir(parents=True, exist_ok=True)
    copy_figures(view, report_dir)
    comp = sort_sp(data["comparison"])
    dyn = sort_sp(
        data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
    )
    p4 = p4_behavior(data)
    concl = conclusions_table(data)
    label = info["label"]
    file_stem = f"informe_resultados_{view}"
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
        f"\\title{{Informe de resultados {tex_escape(label)} - abandono V1}}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Análisis de resultados fuera de muestra}",
        (
            f"Esta iteracion calibra y valida la view \\textit{{{tex_escape(label)}}} bajo la arquitectura robustecida de tres horizontes. "
            f"La configuracion congelada resultante corresponde a {config_text(data)}. La capa P4 usa la Version 1 de abandono: "
            r"$p_{retiro,t}=0$ si $loss_t\leq\hat{x}_1$ y $p_{retiro,t}=[1+\exp(-(loss_t-\hat{x}_1))]^{-1}$ si $loss_t>\hat{x}_1$."
        ),
        table(
            comp,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("sharpe_bl_mean", "Sharpe BL", "num3"),
                ("sharpe_mk_mean", "Sharpe MK", "num3"),
                ("mejora_pct_sharpe_mean", "Mejora Sharpe", "pct"),
                ("drawdown_bl_mean", "DD BL", "pct"),
                ("drawdown_mk_mean", "DD MK", "pct"),
                ("pct_recomendado", "% recomendado", "pct"),
            ],
            f"Comparacion fuera de muestra para {label} con abandono V1.",
            f"tab:{view}:oos",
        ),
        r"\section{Resultados de la dinámica de portafolio}",
        (
            "La dinamica del portafolio se evalua antes de la simulacion economica para separar el comportamiento financiero del modelo "
            "de la respuesta conductual del cliente. El turnover semestral, el numero efectivo de activos y la concentracion sectorial "
            "permiten medir si la view es implementable sin exigir cambios excesivos de composicion."
        ),
        table(
            dyn,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("pct_turnover_gt_20", "Turn. >20%", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Peso sector lider", "pct"),
            ],
            f"Dinamica de portafolio de Black-Litterman para {label}.",
            f"tab:{view}:dinamica",
        ),
        r"\section{Evaluación Económica Monte Carlo P4 en Horizonte Limpio}",
        (
            "La simulacion Monte Carlo P4 se ejecuta solo en el horizonte limpio, con 2000 trayectorias por cruce modelo-escenario-perfil "
            "y 260 semanas. La utilidad de empresa es ex-post y corresponde al 0,5\\% mensual del saldo administrado activo. "
            "El abandono se calcula semanalmente y se reporta tambien en equivalente semestral."
        ),
        table(
            p4,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("terminal_wealth_mean", "Riqueza", "money"),
                ("company_revenue_mean", "Utilidad", "money"),
                ("p_accept_rebalance", "P acepta reb.", "pct"),
                ("mean_weekly_abandon_probability", "P abandono semanal", "pct"),
                ("mean_semiannual_abandon_probability", "P abandono sem.", "pct"),
                ("realized_abandon_rate_260w", "Retiro 260w", "pct"),
                ("client_retention_rate", "Retencion", "pct"),
                ("final_active_clients_mean", "Clientes finales", "int"),
            ],
            f"Resultados P4 para {label} con abandono V1.",
            f"tab:{view}:p4",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.86\textwidth]{figuras/fig_probabilidades_sin_pandemia.png}",
        f"\\caption{{Probabilidades conductuales sin pandemia para {tex_escape(label)} con abandono V1.}}",
        f"\\label{{fig:{view}:prob_sin}}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.86\textwidth]{figuras/fig_probabilidades_con_pandemia.png}",
        f"\\caption{{Probabilidades conductuales con pandemia para {tex_escape(label)} con abandono V1.}}",
        f"\\label{{fig:{view}:prob_con}}",
        r"\end{figure}",
        r"\section{Discusión de Robustez}",
        (
            "La robustez se interpreta como la capacidad de sostener desempeno fuera de muestra, estabilidad de composicion y retencion "
            "de clientes bajo escenarios con y sin pandemia. La Version 1 elimina el abandono artificial cuando no hay exceso de perdida, "
            "pero mantiene una respuesta intensa cuando la perdida cruza la tolerancia."
        ),
        r"\section{Conclusiones}",
        table(
            concl,
            [
                ("portfolio", "Perfil", "text"),
                ("riqueza", "Riqueza", "money"),
                ("utilidad", "Utilidad", "money"),
                ("abandono_sem", "P abandono sem.", "pct"),
                ("retiro_260w", "Retiro 260w", "pct"),
                ("retencion", "Retencion", "pct"),
                ("clientes_finales", "Clientes finales", "int"),
                ("lectura", "Lectura", "text"),
            ],
            f"Conclusion segmentada para {label} con abandono V1.",
            f"tab:{view}:conclusiones",
        ),
        (
            "La recomendacion final de esta view debe considerar simultaneamente mejora financiera, estabilidad dinamica y retencion. "
            "Cuando el modelo aumenta Sharpe pero exige alto turnover o concentra retornos en pocos sectores, su uso debe presentarse "
            "como tactico y condicionado al perfil de riesgo."
        ),
        r"\end{document}",
    ]
    (report_dir / f"{file_stem}.tex").write_text("\n".join(tex), encoding="utf-8")


def comparative() -> pd.DataFrame:
    rows = []
    for view, info in VIEWS.items():
        data = load(view)
        dyn = data["turnover"][
            (data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")
        ]
        comp = data["composition"][
            (data["composition"]["modelo"] == "BL calibrado") & (data["composition"]["window_role"] == "test_p4")
        ]
        sector = data["sector"][
            (data["sector"]["modelo"] == "BL calibrado") & (data["sector"]["window_role"] == "test_p4")
        ]
        p4 = p4_behavior(data)
        comparison = data["comparison"]
        rows.append(
            {
                "view": info["label"],
                "view_key": view,
                "turnover_mean": dyn["turnover_mean"].mean(),
                "turnover_gt20_mean": dyn["pct_turnover_gt_20"].mean(),
                "n_effective_assets_mean": dyn["n_effective_assets_mean"].mean(),
                "sector_hhi_mean": dyn["sector_hhi_mean"].mean(),
                "top_sector_weight_mean": dyn["top_sector_weight_mean"].mean(),
                "distance_l1_initial_final": comp["distance_l1_initial_final"].mean(),
                "top10_overlap_initial_final": comp["top10_overlap_initial_final"].mean(),
                "top3_sector_share_abs_return": sector["top3_sector_share_abs_return"].mean(),
                "sharpe_gain_mean": comparison["mejora_pct_sharpe_mean"].mean(),
                "pct_recomendado_mean": comparison["pct_recomendado"].mean(),
                "semiannual_abandon_mean": p4["mean_semiannual_abandon_probability"].mean(),
                "retention_mean": p4["client_retention_rate"].mean(),
                "company_revenue_mean": p4["company_revenue_mean"].mean(),
                "terminal_wealth_mean": p4["terminal_wealth_mean"].mean(),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "comparativo_views_v1.csv", index=False)
    return df


def write_comparative_report() -> None:
    df = comparative()
    best_stability = df.sort_values(["turnover_mean", "sector_hhi_mean"], ascending=True).iloc[0]
    best_sharpe = df.sort_values(["sharpe_gain_mean", "pct_recomendado_mean"], ascending=False).iloc[0]
    tex = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage{booktabs}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.5cm}",
        r"\setlength{\parskip}{0.65em}",
        r"\setlength{\parindent}{0pt}",
        r"\title{Comparativo de views con probabilidad de abandono V1}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Objetivo}",
        "Este informe compara las cuatro views de Black-Litterman usando la misma probabilidad de abandono V1. El foco principal es la dinamica del portafolio, porque determina la implementabilidad del recomendador antes de evaluar la respuesta economica del cliente.",
        r"\section{Resultados de la Dinámica del Portafolio}",
        table(
            df,
            [
                ("view", "View", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("turnover_gt20_mean", "Turn. >20%", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Peso sector lider", "pct"),
                ("distance_l1_initial_final", "Drift L1", "num3"),
                ("top10_overlap_initial_final", "Overlap top-10", "pct"),
                ("top3_sector_share_abs_return", "Top-3 retorno sector", "pct"),
            ],
            "Comparacion de dinamica de portafolio entre views con abandono V1.",
            "tab:comparativo_v1_dinamica",
        ),
        (
            f"La view con mejor estabilidad dinamica agregada es {tex_escape(best_stability['view'])}, al combinar menor turnover "
            "y menor concentracion sectorial. En contraste, la view con mayor mejora promedio de Sharpe es "
            f"{tex_escape(best_sharpe['view'])}, aunque esta lectura debe ser ponderada por su intensidad de rebalanceo y concentracion."
        ),
        r"\section{Resultados Económicos P4}",
        table(
            df,
            [
                ("view", "View", "text"),
                ("sharpe_gain_mean", "Mejora Sharpe", "pct"),
                ("pct_recomendado_mean", "% recomendado", "pct"),
                ("semiannual_abandon_mean", "P abandono sem.", "pct"),
                ("retention_mean", "Retencion", "pct"),
                ("terminal_wealth_mean", "Riqueza", "money"),
                ("company_revenue_mean", "Utilidad", "money"),
            ],
            "Sintesis economica por view bajo abandono V1.",
            "tab:comparativo_v1_p4",
        ),
        r"\section{Conclusiones generales y recomendaciones}",
        (
            "La recomendacion general es privilegiar la view que logre estabilidad de portafolio antes de maximizar riqueza simulada. "
            "Bajo abandono V1, el modulo conductual deja de saturar el abandono cuando las perdidas estan dentro de tolerancia, por lo que "
            "las diferencias entre views vuelven a depender principalmente de su estructura financiera: rotacion, diversificacion efectiva "
            "y concentracion sectorial."
        ),
        (
            f"Para una implementacion base de FinPUC, {tex_escape(best_stability['view'])} es la candidata mas defendible si se prioriza "
            "robustez operacional. Las views de momentum pueden recomendarse de manera tactica cuando la mejora de Sharpe compense su mayor "
            "rotacion o concentracion, especialmente en perfiles con mayor tolerancia al riesgo."
        ),
        r"\end{document}",
    ]
    (ROOT / "informe_comparativo_views_v1.tex").write_text("\n".join(tex), encoding="utf-8")


def main() -> None:
    for view in VIEWS:
        write_view_report(view)
    write_comparative_report()


if __name__ == "__main__":
    main()
