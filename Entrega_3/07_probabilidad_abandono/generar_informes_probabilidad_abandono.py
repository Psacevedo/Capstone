from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
TESTING_DIR = ROOT / "testing"

VERSIONS: Dict[str, Dict[str, str]] = {
    "Version 1": {
        "formula": r"""\[
P_{retiro,t}=
\begin{cases}
\dfrac{1}{1+\exp[-(loss_t-\hat{x}_1)]}, & loss_t>\hat{x}_1,\\
0, & loss_t\leq \hat{x}_1.
\end{cases}
\]""",
        "interpretation": (
            "Esta versión implementa un umbral duro: mientras la pérdida acumulada no supera la tolerancia, "
            "la probabilidad de retiro es cero. Una vez cruzado el umbral, la logística no escalada genera "
            "una probabilidad semanal cercana a 50% incluso para excesos pequeños."
        ),
    },
    "Version 2": {
        "formula": r"""\[
P_{retiro,t}=
\begin{cases}
\dfrac{0.1}{1+\exp[-(loss_t-\hat{x}_1)]}, & loss_t>\hat{x}_1,\\
0, & loss_t\leq \hat{x}_1.
\end{cases}
\]""",
        "interpretation": (
            "Esta versión conserva el umbral duro, pero impone un techo operacional de 10% semanal. "
            "El objetivo es mantener la lógica conductual de abandono al superar tolerancia, evitando que "
            "la primera semana de exceso de pérdida elimine de forma abrupta a la mitad de los clientes."
        ),
    },
    "Version 3": {
        "formula": r"""\[
P_{retiro,t}=
\begin{cases}
\dfrac{0.10}{1+\exp[-20(loss_t-\hat{x}_1)]}, & loss_t>\hat{x}_1,\\
0, & loss_t\leq \hat{x}_1.
\end{cases}
\]""",
        "interpretation": (
            "Esta versión combina techo de 10% semanal con una pendiente mayor. Con ello, el abandono "
            "se mantiene acotado, pero reacciona más rápido cuando la pérdida acumulada excede con claridad "
            "la tolerancia declarada del perfil."
        ),
    },
}

PROFILE_ORDER = ["Muy conservador", "Conservador", "Neutro", "Arriesgado", "Muy arriesgado"]


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


def scenario_profile_sort(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["scenario_order"] = out["scenario"].map({"sin_pandemia": 0, "con_pandemia": 1})
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values(["scenario_order", "profile_order"]).drop(columns=["scenario_order", "profile_order"])


def latex_table(df: pd.DataFrame, columns: List[Tuple[str, str, str]], caption: str, label: str) -> str:
    header = " & ".join(tex_escape(name) for _, name, _ in columns) + r" \\"
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
                cells.append(str(int(round(float(row[col])))) if pd.notna(row[col]) else "---")
            else:
                cells.append(tex_escape(row[col]))
        rows.append(" & ".join(cells) + r" \\")
    tabular = "\n".join(
        [
            r"\begin{tabular}{l" + "r" * (len(columns) - 1) + "}",
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


def copy_figures(version_dir: Path, report_dir: Path) -> None:
    fig_dir = report_dir / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "fig_probabilidades_con_pandemia.png",
        "fig_probabilidades_sin_pandemia.png",
        "fig_clientes_con_pandemia.png",
        "fig_clientes_sin_pandemia.png",
    ]:
        src = version_dir / "outputs" / "behavior" / name
        if src.exists():
            shutil.copy2(src, fig_dir / name)


def load_version(version: str) -> Dict[str, pd.DataFrame]:
    out = TESTING_DIR / version / "outputs"
    return {
        "comparison": read_csv(out / "test_p4" / "test_limpio_comparacion_resumen.csv"),
        "turnover": read_csv(out / "portfolio_dynamics" / "turnover_summary.csv"),
        "p4": read_csv(out / "test_p4" / "p4_test_limpio_resumen.csv"),
        "behavior": read_csv(out / "behavior" / "behavior_probabilities_clients_summary.csv"),
    }


def p4_behavior_table(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    p4 = data["p4"][data["p4"]["modelo"] == "BL calibrado"].copy()
    behavior = data["behavior"][data["behavior"]["modelo"] == "BL calibrado"].copy()
    merged = p4.merge(
        behavior[
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
        "mean_weekly_abandon_probability",
        "mean_semiannual_abandon_probability",
        "p_accept_rebalance",
        "realized_abandon_rate_260w",
    ]:
        if target not in merged.columns:
            candidates = [col for col in merged.columns if col.startswith(target)]
            if candidates:
                merged[target] = merged[candidates].bfill(axis=1).iloc[:, 0]
    return scenario_profile_sort(merged)


def conclusion_rows(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    p4 = p4_behavior_table(data)
    out = (
        p4.groupby("portfolio", as_index=False)
        .agg(
            abandono_sem=("mean_semiannual_abandon_probability", "mean"),
            retiro_260w=("realized_abandon_rate_260w", "mean"),
            retencion=("client_retention_rate", "mean"),
            clientes_finales=("final_active_clients_mean", "mean"),
            utilidad=("company_revenue_mean", "mean"),
            riqueza=("terminal_wealth_mean", "mean"),
        )
    )
    out["lectura"] = np.where(
        out["retencion"] >= 0.70,
        "Estable",
        np.where(out["retencion"] >= 0.35, "Intermedia", "Crítica"),
    )
    out["profile_order"] = out["portfolio"].map({p: i for i, p in enumerate(PROFILE_ORDER)})
    return out.sort_values("profile_order").drop(columns="profile_order")


def narrative(version: str, data: Dict[str, pd.DataFrame]) -> str:
    p4 = p4_behavior_table(data)
    retention = p4["client_retention_rate"].mean()
    semi = p4["mean_semiannual_abandon_probability"].mean()
    realized = p4["realized_abandon_rate_260w"].mean()
    utility = p4["company_revenue_mean"].mean()
    return (
        f"En el promedio de escenarios y perfiles, la probabilidad semestral de abandono es {fmt_pct(semi)}, "
        f"la tasa de retiro realizada en 260 semanas es {fmt_pct(realized)}, la retención de clientes activos es "
        f"{fmt_pct(retention)} y la utilidad media de la empresa alcanza {fmt_money(utility)}. "
        f"Estos resultados permiten evaluar si {tex_escape(version)} corrige la saturación observada en la iteración previa "
        "sin producir una permanencia artificial de clientes ante pérdidas materialmente superiores a su tolerancia."
    )


def write_report(version: str) -> None:
    data = load_version(version)
    version_dir = TESTING_DIR / version
    report_dir = version_dir / "informe resultados"
    report_dir.mkdir(parents=True, exist_ok=True)
    copy_figures(version_dir, report_dir)

    comparison = scenario_profile_sort(data["comparison"])
    turnover = scenario_profile_sort(
        data["turnover"][(data["turnover"]["modelo"] == "BL calibrado") & (data["turnover"]["window_role"] == "test_p4")]
    )
    p4 = p4_behavior_table(data)
    conclusions = conclusion_rows(data)
    info = VERSIONS[version]

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
        f"\\title{{Testing probabilidad de abandono: {tex_escape(version)}}}",
        r"\author{FinPUC}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Análisis de resultados fuera de muestra}",
        "La validación financiera se replica desde la iteración de desempleo macro, manteniendo fija la arquitectura de tres horizontes y la calibración Black-Litterman. El objetivo de esta carpeta no es volver a seleccionar una view, sino aislar el efecto de la función de abandono sobre la capa económica P4.",
        info["formula"],
        info["interpretation"],
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
                ("pct_recomendado", "% recomendado", "pct"),
            ],
            f"Comparación financiera fuera de muestra para {version}.",
            f"tab:{version.replace(' ', '_').lower()}:oos",
        ),
        r"\section{Resultados de la dinámica de portafolio}",
        "La dinámica de portafolio se mantiene como control metodológico: cualquier diferencia material entre versiones debe provenir de la simulación de abandono y no de cambios en pesos, rebalanceos o concentración sectorial.",
        latex_table(
            turnover,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("turnover_mean", "Turnover", "pct"),
                ("n_effective_assets_mean", "N efectivo", "num2"),
                ("sector_hhi_mean", "HHI sector", "num3"),
                ("top_sector_weight_mean", "Peso sector líder", "pct"),
            ],
            f"Dinámica de portafolio de la view desempleo macro bajo {version}.",
            f"tab:{version.replace(' ', '_').lower()}:dinamica",
        ),
        r"\section{Evaluación Económica Monte Carlo P4 en Horizonte Limpio}",
        "La simulación P4 usa 2000 trayectorias por cruce modelo-escenario-perfil y un horizonte de 260 semanas. La utilidad de la empresa se calcula ex-post con una comisión de 0,5\\% mensual sobre el saldo administrado activo. La probabilidad de abandono se evalúa semanalmente, pero se reporta también como probabilidad semestral para la presentación.",
        narrative(version, data),
        latex_table(
            p4,
            [
                ("scenario", "Escenario", "text"),
                ("portfolio", "Perfil", "text"),
                ("terminal_wealth_mean", "Riqueza", "money"),
                ("company_revenue_mean", "Utilidad", "money"),
                ("p_accept_rebalance", "P acepta reb.", "pct"),
                ("mean_weekly_abandon_probability", "P abandono semanal", "pct"),
                ("mean_semiannual_abandon_probability", "P abandono semestre", "pct"),
                ("realized_abandon_rate_260w", "Retiro 260w", "pct"),
                ("client_retention_rate", "Retención", "pct"),
                ("final_active_clients_mean", "Clientes finales", "int"),
            ],
            f"Resultados P4 y comportamiento de clientes para {version}.",
            f"tab:{version.replace(' ', '_').lower()}:p4",
        ),
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.88\textwidth]{figuras/fig_probabilidades_sin_pandemia.png}",
        f"\\caption{{Probabilidades de aceptación y abandono semestral sin pandemia para {tex_escape(version)}.}}",
        f"\\label{{fig:{version.replace(' ', '_').lower()}:prob_sin}}",
        r"\end{figure}",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=0.88\textwidth]{figuras/fig_probabilidades_con_pandemia.png}",
        f"\\caption{{Probabilidades de aceptación y abandono semestral con pandemia para {tex_escape(version)}.}}",
        f"\\label{{fig:{version.replace(' ', '_').lower()}:prob_con}}",
        r"\end{figure}",
        r"\section{Discusión de Robustez}",
        "La robustez se interpreta como estabilidad económica y conductual bajo escenarios con y sin pandemia. Una función de abandono demasiado agresiva reduce artificialmente el saldo administrado y deprime la utilidad; una función demasiado laxa puede esconder pérdidas relevantes al mantener clientes que deberían retirarse según su tolerancia.",
        r"\section{Conclusiones}",
        latex_table(
            conclusions,
            [
                ("portfolio", "Perfil", "text"),
                ("abandono_sem", "P abandono semestre", "pct"),
                ("retiro_260w", "Retiro 260w", "pct"),
                ("retencion", "Retención", "pct"),
                ("clientes_finales", "Clientes finales", "int"),
                ("utilidad", "Utilidad", "money"),
                ("lectura", "Lectura", "text"),
            ],
            f"Conclusión segmentada por perfil para {version}.",
            f"tab:{version.replace(' ', '_').lower()}:conclusiones",
        ),
        "La versión debe seleccionarse según su capacidad de evitar la saturación semestral y, al mismo tiempo, mantener sensibilidad ante pérdidas por encima de la tolerancia. En particular, la comparación entre versiones permite defender una especificación conductual calibrada por estabilidad de clientes y no solo por riqueza terminal.",
        r"\end{document}",
    ]
    (report_dir / "informe_resultados.tex").write_text("\n".join(tex), encoding="utf-8")


def write_comparison_csv() -> None:
    rows = []
    for version in VERSIONS:
        data = load_version(version)
        p4 = p4_behavior_table(data)
        rows.append(
            {
                "version": version,
                "mean_weekly_abandon_probability": p4["mean_weekly_abandon_probability"].mean(),
                "mean_semiannual_abandon_probability": p4["mean_semiannual_abandon_probability"].mean(),
                "realized_abandon_rate_260w": p4["realized_abandon_rate_260w"].mean(),
                "client_retention_rate": p4["client_retention_rate"].mean(),
                "final_active_clients_mean": p4["final_active_clients_mean"].mean(),
                "company_revenue_mean": p4["company_revenue_mean"].mean(),
                "terminal_wealth_mean": p4["terminal_wealth_mean"].mean(),
            }
        )
    pd.DataFrame(rows).to_csv(ROOT / "comparativo_probabilidad_abandono.csv", index=False)


def main() -> None:
    for version in VERSIONS:
        write_report(version)
    write_comparison_csv()


if __name__ == "__main__":
    main()
