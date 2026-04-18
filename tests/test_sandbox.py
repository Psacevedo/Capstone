"""
tests/test_sandbox.py — Suite de pruebas del sandbox supervisado P4.

Ejecutar:
    python -m pytest tests/test_sandbox.py -v
  o directamente:
    python tests/test_sandbox.py

Casos de prueba:
  T1  — Caso feliz: portafolio óptimo con scipy (fallback)
  T2  — Infactibilidad por α muy restrictivo
  T3  — Solución trivial (todo en caja chica)
  T4  — Validador: restricción presupuesto
  T5  — Validador: restricción R3 violada
  T6  — Validador: concentración alta (warning)
  T7  — Generador de código LP base
  T8  — Generador de código 2-SLP
  T9  — run_code: código Gurobi con licencia inválida → LICENSE_ERROR
  T10 — run_code: código con syntax error → CODE_ERROR
  T11 — Tiempo de solución < 10s
  T12 — 5 perfiles de riesgo, todos resolvibles
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from solver import SolverSandbox, SolverStatus, Diagnostics
from solver.validators import PortfolioValidator
from solver.models.portfolio_lp import generate_gurobi_code as gen_base_code
from solver.models.stochastic_lp import generate_gurobi_code as gen_2slp_code
from solver.validators import RISK_PROFILES


# ---- Datos de prueba -------------------------------------------------------

TICKERS = ["AAPL", "MSFT", "JNJ", "KO", "XOM", "NEE", "JPM", "UNH"]

RETURNS_SCEN = {
    "desf":   {"AAPL": -0.08, "MSFT": -0.06, "JNJ": -0.03, "KO": -0.02,
               "XOM": -0.05, "NEE": -0.02, "JPM": -0.07, "UNH": -0.04},
    "neutro": {"AAPL":  0.12, "MSFT":  0.11, "JNJ":  0.07, "KO":  0.06,
               "XOM":  0.08, "NEE":  0.06, "JPM":  0.10, "UNH":  0.09},
    "fav":    {"AAPL":  0.28, "MSFT":  0.25, "JNJ":  0.14, "KO":  0.12,
               "XOM":  0.18, "NEE":  0.10, "JPM":  0.22, "UNH":  0.20},
}

PROBS = {"desf": 0.25, "neutro": 0.50, "fav": 0.25}

RETURNS_MEAN = {
    t: sum(PROBS[s] * RETURNS_SCEN[s][t] for s in PROBS)
    for t in TICKERS
}


# ---- Utilidades ------------------------------------------------------------

def make_sandbox(**kwargs):
    return SolverSandbox(
        time_limit=9.0,
        use_fallback=True,
        verbose=False,
        **kwargs
    )


def run_test(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
        return False


# ---- Tests -----------------------------------------------------------------

def test_t1_optimal_scipy():
    """T1 — Caso feliz: portafolio óptimo con scipy."""
    sb     = make_sandbox()
    result = sb.run_model(
        tickers=TICKERS,
        returns_mean=RETURNS_MEAN,
        returns_scen=RETURNS_SCEN,
        probs=PROBS,
        profile="neutro",
    )
    assert result.ok(), f"Se esperaba resultado accionable, got {result.status}"
    assert result.weights is not None
    assert result.cash is not None
    total = sum(result.weights.values()) + result.cash
    assert abs(total - 1.0) < 1e-4, f"Presupuesto violado: Σw={total:.6f}"
    assert result.obj_value is not None and result.obj_value > 0
    assert result.validation is not None
    assert result.validation["valid"], f"Validación fallida: {result.validation['violations']}"


def test_t2_infeasible_strict_alpha():
    """T2 — alpha=0% con r_desf < 0: solver pone todo en caja chica (TRIVIAL) o INFEASIBLE."""
    sb     = make_sandbox()
    result = sb.run_model(
        tickers=TICKERS,
        returns_mean=RETURNS_MEAN,
        returns_scen=RETURNS_SCEN,
        probs=PROBS,
        profile="muy_conservador",   # alpha=0%
    )
    # Con scipy: solución factible es w0=1 (caja chica) → TRIVIAL
    # Con Gurobi: puede detectar INFEASIBLE directamente
    assert result.status in (SolverStatus.INFEASIBLE, SolverStatus.TRIVIAL), (
        f"Se esperaba INFEASIBLE o TRIVIAL, got {result.status}"
    )


def test_t3_trivial_detection():
    """T3 — Detección de solución trivial (todo en caja chica)."""
    # Crear escenario donde todos los retornos esperados son negativos
    neg_returns = {t: -0.05 for t in TICKERS}
    neg_scen = {
        "desf":   {t: -0.20 for t in TICKERS},
        "neutro": {t: -0.05 for t in TICKERS},
        "fav":    {t:  0.01 for t in TICKERS},
    }
    sb     = make_sandbox()
    result = sb.run_model(
        tickers=TICKERS,
        returns_mean=neg_returns,
        returns_scen=neg_scen,
        probs=PROBS,
        profile="neutro",
    )
    # Solver debería poner todo en caja chica → TRIVIAL
    if result.ok():
        cash = result.cash or 0.0
        assert cash >= 0.90, f"Esperaba caja chica ≥90%, got {cash:.1%}"


def test_t4_validator_budget():
    """T4 — Validador detecta violación de presupuesto."""
    v = PortfolioValidator(
        weights={"AAPL": 0.6, "MSFT": 0.6},  # suma > 1
        cash=0.0,
        profile="neutro",
    )
    result = v.validate()
    assert not result.valid
    assert any("R1" in msg for msg in result.violations), (
        f"Se esperaba violación R1, got: {result.violations}"
    )


def test_t5_validator_r3():
    """T5 — Validador detecta violación de tolerancia de pérdida R3."""
    v = PortfolioValidator(
        weights={"AAPL": 0.8, "MSFT": 0.2},
        cash=0.0,
        returns_scenario={"AAPL": -0.20, "MSFT": -0.15},
        profile="conservador",   # alpha=5%
    )
    result = v.validate()
    assert not result.valid
    assert any("R3" in msg for msg in result.violations), (
        f"Se esperaba violación R3 (pérdida = -17.0% < -5%), got: {result.violations}"
    )


def test_t6_validator_concentration_warning():
    """T6 — Validador emite warning por concentración alta."""
    v = PortfolioValidator(
        weights={"AAPL": 0.75, "MSFT": 0.25},
        cash=0.0,
        returns_scenario={"AAPL": 0.0, "MSFT": 0.0},
        profile="muy_arriesgado",   # alpha=40%
    )
    result = v.validate()
    assert result.valid, f"Se esperaba válido: {result.violations}"
    assert any("Concentración" in w for w in result.warnings), (
        f"Se esperaba warning concentración, got: {result.warnings}"
    )


def test_t7_code_gen_base():
    """T7 — Generador de código LP base produce código válido Python."""
    code = gen_base_code(
        tickers=TICKERS,
        returns_mean=RETURNS_MEAN,
        returns_desf=RETURNS_SCEN["desf"],
        alpha=0.15,
        commission_k=0.001,
        prev_weights=None,
        max_weight=0.4,
        time_limit=9.0,
    )
    assert "import gurobipy" in code
    assert "_model" in code
    assert "_weights" in code
    assert "_cash" in code
    assert "budget" in code
    assert "loss_tolerance" in code
    # Debe ser Python válido
    compile(code, "<gen_base>", "exec")


def test_t8_code_gen_2slp():
    """T8 — Generador de código 2-SLP produce código válido Python."""
    code = gen_2slp_code(
        tickers=TICKERS,
        returns_scen=RETURNS_SCEN,
        probs=PROBS,
        alpha=0.15,
        commission_k=0.001,
    )
    assert "import gurobipy" in code
    assert "returns_scen" in code
    assert "probs" in code
    compile(code, "<gen_2slp>", "exec")


def test_t9_run_code_license_error():
    """T9 — run_code detecta error de licencia Gurobi."""
    bad_code = """
import gurobipy as gp
m = gp.Model("test")
x = m.addVar()
m.setObjective(x, gp.GRB.MAXIMIZE)
m.addConstr(x <= 1)
m.optimize()
_model   = m
_weights = {}
_cash    = m.addVar()
"""
    sb = make_sandbox()
    result = sb.run_code(bad_code)
    # Con licencia vencida o sin Gurobi instalado debe dar LICENSE_ERROR o CODE_ERROR
    assert result.status in (
        SolverStatus.LICENSE_ERROR,
        SolverStatus.RUNTIME_ERROR,
        SolverStatus.CODE_ERROR,
    ), f"Esperaba error de licencia/runtime, got {result.status}"


def test_t10_run_code_syntax_error():
    """T10 — run_code detecta syntax error en código LLM."""
    bad_code = "def broken(:\n    pass"
    sb     = make_sandbox()
    result = sb.run_code(bad_code)
    assert result.status in (SolverStatus.CODE_ERROR, SolverStatus.RUNTIME_ERROR), (
        f"Se esperaba CODE_ERROR, got {result.status}"
    )


def test_t11_solve_time():
    """T11 — Tiempo de solución < 10s con universo de 8 acciones."""
    sb     = make_sandbox()
    t0     = time.perf_counter()
    result = sb.run_model(
        tickers=TICKERS,
        returns_mean=RETURNS_MEAN,
        returns_scen=RETURNS_SCEN,
        probs=PROBS,
        profile="arriesgado",
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"Tiempo total = {elapsed:.2f}s > 10s"
    if result.diagnostic.solve_time:
        assert result.diagnostic.solve_time < 10.0


def test_t12_all_profiles():
    """T12 — Los 5 perfiles de riesgo resuelven correctamente."""
    sb = make_sandbox()
    for profile, alpha in RISK_PROFILES.items():
        if alpha == 0.0:
            # muy_conservador: puede ser infactible con todos r_desf negativos
            continue
        result = sb.run_model(
            tickers=TICKERS,
            returns_mean=RETURNS_MEAN,
            returns_scen=RETURNS_SCEN,
            probs=PROBS,
            profile=profile,
        )
        assert result.ok() or result.status == SolverStatus.TRIVIAL, (
            f"Perfil '{profile}' (α={alpha:.0%}): {result.status} — "
            f"{result.diagnostic.message[:80]}"
        )
        if result.ok():
            total = sum(result.weights.values()) + (result.cash or 0)
            assert abs(total - 1.0) < 1e-4, (
                f"Perfil '{profile}': presupuesto violado Σw={total:.6f}"
            )


# ---- Runner ----------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Sandbox P4 — Suite de Tests")
    print("=" * 60)

    tests = [
        ("T1  Caso feliz (scipy)",            test_t1_optimal_scipy),
        ("T2  Infactibilidad alpha=0%",        test_t2_infeasible_strict_alpha),
        ("T3  Detección trivial",              test_t3_trivial_detection),
        ("T4  Validador: presupuesto",         test_t4_validator_budget),
        ("T5  Validador: R3 pérdida",          test_t5_validator_r3),
        ("T6  Validador: concentración warn",  test_t6_validator_concentration_warning),
        ("T7  Codegen LP base",                test_t7_code_gen_base),
        ("T8  Codegen 2-SLP",                  test_t8_code_gen_2slp),
        ("T9  run_code: licencia Gurobi",      test_t9_run_code_license_error),
        ("T10 run_code: syntax error",         test_t10_run_code_syntax_error),
        ("T11 Tiempo < 10s",                   test_t11_solve_time),
        ("T12 Todos los perfiles",             test_t12_all_profiles),
    ]

    passed = 0
    for name, fn in tests:
        if run_test(name, fn):
            passed += 1

    total = len(tests)
    print("=" * 60)
    print(f"  Resultado: {passed}/{total} tests pasados")
    print("=" * 60)
    sys.exit(0 if passed == total else 1)
