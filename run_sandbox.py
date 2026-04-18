"""
run_sandbox.py — CLI para ejecutar el sandbox de portafolios P4.

Uso rápido:
    python run_sandbox.py                        # demo con datos de prueba
    python run_sandbox.py --profile arriesgado   # cambiar perfil
    python run_sandbox.py --tickers AAPL MSFT JNJ KO --profile conservador
    python run_sandbox.py --code mi_modelo.py    # ejecutar código Gurobi externo

Opciones:
    --profile   {muy_conservador, conservador, neutro, arriesgado, muy_arriesgado}
    --tickers   lista de tickers (del universo Historical_Stocks/)
    --code      ruta a archivo .py con código Gurobi (modo run_code)
    --fallback  forzar uso de scipy aunque Gurobi esté disponible
    --verbose   mostrar logs del solver
    --json      imprimir resultado completo en JSON
"""

import argparse
import json
import sys
import os

# Forzar UTF-8 en stdout/stderr para soportar caracteres Unicode en Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from solver import SolverSandbox, SolverStatus


# ---- Datos de demo ---------------------------------------------------------

DEMO_TICKERS = ["AAPL", "MSFT", "JNJ", "KO", "XOM", "NEE", "JPM", "UNH",
                "PG", "WMT", "V", "MA", "LLY", "ABBV", "CAT"]

DEMO_RETURNS_SCEN = {
    "desf": {
        "AAPL": -0.08, "MSFT": -0.06, "JNJ": -0.03, "KO": -0.02, "XOM": -0.05,
        "NEE": -0.02,  "JPM": -0.07,  "UNH": -0.04, "PG": -0.02, "WMT": -0.02,
        "V":   -0.06,  "MA":  -0.07,  "LLY": -0.04, "ABBV": -0.03, "CAT": -0.06,
    },
    "neutro": {
        "AAPL":  0.12, "MSFT":  0.11, "JNJ":  0.07, "KO":  0.06, "XOM":  0.08,
        "NEE":   0.06, "JPM":   0.10, "UNH":  0.09, "PG":  0.05, "WMT":  0.07,
        "V":     0.13, "MA":    0.14, "LLY":  0.10, "ABBV": 0.09, "CAT": 0.09,
    },
    "fav": {
        "AAPL":  0.28, "MSFT":  0.25, "JNJ":  0.14, "KO":  0.12, "XOM":  0.18,
        "NEE":   0.10, "JPM":   0.22, "UNH":  0.20, "PG":  0.10, "WMT":  0.14,
        "V":     0.28, "MA":    0.30, "LLY":  0.22, "ABBV": 0.18, "CAT": 0.20,
    },
}

DEMO_PROBS = {"desf": 0.25, "neutro": 0.50, "fav": 0.25}


# ---- Main ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sandbox supervisado de optimización de portafolios P4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--profile",
        default="neutro",
        choices=["muy_conservador", "conservador", "neutro", "arriesgado", "muy_arriesgado"],
        help="Perfil de riesgo del cliente",
    )
    parser.add_argument(
        "--tickers", nargs="+", default=None,
        help="Lista de tickers a incluir (default: 15 acciones demo)",
    )
    parser.add_argument(
        "--code", default=None,
        help="Archivo .py con código Gurobi a ejecutar (modo run_code)",
    )
    parser.add_argument(
        "--fallback", action="store_true",
        help="Forzar uso de scipy aunque Gurobi esté disponible",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar logs del solver",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Imprimir resultado completo en JSON",
    )
    parser.add_argument(
        "--max-weight", type=float, default=1.0,
        help="Concentración máxima por acción (ej: 0.25)",
    )
    args = parser.parse_args()

    tickers = args.tickers or DEMO_TICKERS
    # Filtrar tickers no disponibles en los datos demo
    if not args.tickers:
        tickers = [t for t in DEMO_TICKERS if t in DEMO_RETURNS_SCEN["neutro"]]

    print(f"\n{'='*60}")
    print(f"  Sandbox P4 — Optimizador de Portafolios FinPUC")
    print(f"{'='*60}")
    print(f"  Perfil:    {args.profile}")
    print(f"  Tickers:   {len(tickers)} acciones")
    print(f"  Solver:    {'scipy (forzado)' if args.fallback else 'Gurobi (+ fallback scipy)'}")
    if args.code:
        print(f"  Modo:      run_code ({args.code})")
    print()

    sb = SolverSandbox(
        time_limit=9.0,
        use_fallback=True,
        verbose=args.verbose,
    )

    # Modo run_code: ejecutar archivo .py externo
    if args.code:
        if not os.path.isfile(args.code):
            print(f"ERROR: archivo no encontrado: {args.code}")
            sys.exit(1)
        with open(args.code, "r", encoding="utf-8") as f:
            code_str = f.read()
        result = sb.run_code(code_str, profile=args.profile)

    # Modo run_model: modelo parametrizado
    else:
        returns_mean = {
            t: sum(DEMO_PROBS[s] * DEMO_RETURNS_SCEN[s].get(t, 0.0) for s in DEMO_PROBS)
            for t in tickers
        }
        result = sb.run_model(
            tickers=tickers,
            returns_mean=returns_mean,
            returns_scen={s: {t: DEMO_RETURNS_SCEN[s].get(t, 0.0) for t in tickers}
                          for s in DEMO_RETURNS_SCEN},
            probs=DEMO_PROBS,
            profile=args.profile,
            max_weight=args.max_weight,
        )

    # ---- Imprimir resultado ------------------------------------------------

    diag = result.diagnostic
    status_symbol = {
        SolverStatus.OPTIMAL:        "[OK] OPTIMO",
        SolverStatus.TRIVIAL:        "[!] TRIVIAL",
        SolverStatus.INFEASIBLE:     "[X] INFACTIBLE",
        SolverStatus.UNBOUNDED:      "[X] NO ACOTADO",
        SolverStatus.TIME_LIMIT:     "[T] TIEMPO LIMITE",
        SolverStatus.TIME_LIMIT_SOL: "[T] TIEMPO LIMITE (con solucion)",
        SolverStatus.LICENSE_ERROR:  "[!] ERROR LICENCIA",
        SolverStatus.CODE_ERROR:     "[X] ERROR CODIGO",
        SolverStatus.RUNTIME_ERROR:  "[X] ERROR EJECUCION",
    }.get(result.status, f"? {result.status.value}")

    print(f"  Estado:    {status_symbol}")
    print(f"  Solver:    {result.solver_used}")
    if diag.solve_time is not None:
        print(f"  Tiempo:    {diag.solve_time:.4f}s")
    if diag.n_vars is not None:
        print(f"  Variables: {diag.n_vars} vars, {diag.n_constrs} restricciones")

    if result.ok():
        print(f"\n  Retorno esperado: {result.obj_value:.4f} ({result.obj_value:.2%})")
        print(f"\n  Portafolio óptimo:")
        if result.weights:
            active = [(t, w) for t, w in result.weights.items() if w > 1e-4]
            active.sort(key=lambda x: -x[1])
            for t, w in active:
                bar = "#" * int(w * 30)
                print(f"    {t:<8} {w:>7.2%}  {bar}")
        if result.cash is not None and result.cash > 1e-4:
            bar = "#" * int(result.cash * 30)
            print(f"    {'CASH':<8} {result.cash:>7.2%}  {bar}")

        if result.summary:
            s = result.summary
            print(f"\n  Resumen:")
            print(f"    Posiciones activas: {s['n_active_positions']}")
            print(f"    Invertido en acciones: {s['total_invested']:.2%}")
            print(f"    Caja chica: {s['cash_weight']:.2%}")

        if result.validation and not result.validation["valid"]:
            print(f"\n  [!] VIOLACIONES DE RESTRICCIONES:")
            for v in result.validation["violations"]:
                print(f"    - {v}")

    else:
        print(f"\n  Diagnóstico: {diag.message[:200]}")
        if diag.suggestions:
            print(f"\n  Sugerencias:")
            for s in diag.suggestions:
                print(f"    → {s}")
        if diag.traceback:
            print(f"\n  Traceback (últimas líneas):")
            lines = diag.traceback.strip().splitlines()
            for line in lines[-8:]:
                print(f"    {line}")

    if diag.warnings:
        print(f"\n  Advertencias:")
        for w in diag.warnings:
            print(f"    [!] {w}")

    print()

    if args.json:
        print(result.to_json())

    return 0 if result.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
