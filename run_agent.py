"""
run_agent.py -- CLI para ejecutar el pipeline P4 supervisado por LLM.

Uso rapido:
    python run_agent.py                          # demo con datos de prueba
    python run_agent.py --profile arriesgado     # cambiar perfil de riesgo
    python run_agent.py --tickers AAPL MSFT JNJ  # tickers personalizados
    python run_agent.py --direct                 # modo directo (sin LLM)
    python run_agent.py --max-iter 3             # limitar iteraciones

Opciones:
    --profile    {muy_conservador, conservador, neutro, arriesgado, muy_arriesgado}
    --tickers    lista de tickers (default: 15 acciones demo)
    --max-iter   iteraciones maximas del loop LLM (default: 5)
    --max-weight concentracion maxima por accion (default: 1.0)
    --direct     omitir LLM y resolver directamente con sandbox
    --verbose    mostrar logs detallados de cada agente
    --json       imprimir resultado completo en JSON
    --api-key    ANTHROPIC_API_KEY (o variable de entorno)
"""

import argparse
import json
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from solver_agent import P4Pipeline
from solver import SolverStatus


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
        description="Pipeline P4 supervisado por LLM (OptiMUS + OR-LLM-Agent)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--profile", default="neutro",
        choices=["muy_conservador", "conservador", "neutro", "arriesgado", "muy_arriesgado"],
        help="Perfil de riesgo del cliente",
    )
    parser.add_argument(
        "--tickers", nargs="+", default=None,
        help="Lista de tickers (default: 15 acciones demo)",
    )
    parser.add_argument(
        "--max-iter", type=int, default=5,
        help="Iteraciones maximas del loop LLM (default: 5)",
    )
    parser.add_argument(
        "--max-weight", type=float, default=1.0,
        help="Concentracion maxima por accion (default: 1.0)",
    )
    parser.add_argument(
        "--direct", action="store_true",
        help="Modo directo: omitir LLM, resolver con sandbox",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar logs detallados de agentes y sandbox",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Imprimir resultado completo en JSON",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="ANTHROPIC_API_KEY (o variable de entorno ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    # Resolver tickers
    tickers = args.tickers if args.tickers else DEMO_TICKERS
    tickers = [t for t in tickers if t in DEMO_RETURNS_SCEN["neutro"]]
    if not tickers:
        print("ERROR: ningun ticker valido. Usando tickers demo.")
        tickers = DEMO_TICKERS

    print(f"\n{'='*60}")
    print(f"  Pipeline P4 -- Optimizador de Portafolios (LLM-supervisado)")
    print(f"{'='*60}")
    print(f"  Perfil:    {args.profile}")
    print(f"  Tickers:   {len(tickers)} acciones")
    if args.direct:
        print(f"  Modo:      directo (sin LLM)")
    else:
        print(f"  Modo:      supervisado por LLM (max {args.max_iter} iters)")
    print()

    # Crear pipeline
    pipeline = P4Pipeline(
        api_key    = args.api_key,
        max_iter   = args.max_iter,
        verbose    = args.verbose,
        time_limit = 9.0,
    )

    # Ejecutar
    if args.direct:
        # Modo directo: sin LLM
        result = pipeline.run_direct(
            tickers      = tickers,
            returns_scen = DEMO_RETURNS_SCEN,
            probs        = DEMO_PROBS,
            profile      = args.profile,
            max_weight   = args.max_weight,
        )
        _print_solver_result(result)
        if args.json:
            print(result.to_json())
        return 0 if result.ok() else 1

    else:
        # Modo LLM supervisado
        api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: Se requiere ANTHROPIC_API_KEY para el modo supervisado.")
            print("  Usa --api-key o define la variable de entorno ANTHROPIC_API_KEY.")
            print("  Para modo sin LLM usa --direct.")
            return 1

        pipeline_result = pipeline.run(
            tickers      = tickers,
            returns_scen = DEMO_RETURNS_SCEN,
            probs        = DEMO_PROBS,
            profile      = args.profile,
            max_weight   = args.max_weight,
        )

        pipeline_result.print_summary()

        if args.json:
            print(pipeline_result.to_json())

        return 0 if pipeline_result.success else 1


def _print_solver_result(result):
    """Imprime un SolverResult en modo directo."""
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

    print(f"  Estado:  {status_symbol}")
    print(f"  Solver:  {result.solver_used}")

    if result.ok():
        print(f"\n  Retorno esperado: {result.obj_value:.4f} ({result.obj_value:.2%})")
        print(f"\n  Portafolio optimo:")
        if result.weights:
            active = [(t, w) for t, w in result.weights.items() if w > 1e-4]
            active.sort(key=lambda x: -x[1])
            for t, w in active:
                bar = "#" * int(w * 30)
                print(f"    {t:<8} {w:>7.2%}  {bar}")
        if result.cash is not None and result.cash > 1e-4:
            bar = "#" * int(result.cash * 30)
            print(f"    {'CASH':<8} {result.cash:>7.2%}  {bar}")
    else:
        diag = result.diagnostic
        print(f"\n  Diagnostico: {diag.message[:200]}")
    print()


if __name__ == "__main__":
    sys.exit(main())
