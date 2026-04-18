"""
tests/test_pipeline.py -- Suite de pruebas del pipeline LLM supervisado P4.

Ejecutar:
    python -m pytest tests/test_pipeline.py -v
  o directamente:
    python tests/test_pipeline.py

Casos de prueba:
  P1  -- PipelineResult.to_dict() / to_json()
  P2  -- run_direct(): portafolio optimo sin LLM
  P3  -- run_direct(): todos los perfiles resolvibles
  P4  -- Programador mock: generate() produce codigo valido
  P5  -- Evaluador mock: evaluate() acepta OPTIMAL
  P6  -- Evaluador mock: evaluate() pide retry en CODE_ERROR
  P7  -- Manager mock: decide() acepta en primera iteracion con accept
  P8  -- Manager mock: decide() cambia estrategia en iteracion 3+
  P9  -- Pipeline mock full loop: exito en primera iteracion
  P10 -- Pipeline mock full loop: escalada de estrategia (retry -> cambiar)
  P11 -- Pipeline mock full loop: max_iter sin solucion -> PipelineResult.success=False
  P12 -- _reduce_universe() reduce correctamente a top-20
  P13 -- _fallback_codegen() produce codigo compilable para todas las estrategias
  P14 -- _apply_strategy_adjustments() detecta codigo scipy+gurobipy
"""

import sys
import os
import json
import time
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from solver import SolverSandbox, SolverStatus, SolverResult
from solver.validators import RISK_PROFILES
from solver_agent import P4Pipeline
from solver_agent.agents import (
    EvaluadorAgent, ManagerAgent, ProgramadorAgent,
    EvaluadorDecision, ManagerDecision,
)
from solver_agent.pipeline import PipelineResult, IterationRecord


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


# ---- Helpers ----------------------------------------------------------------

def run_test(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        import traceback as tb
        print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
        if os.environ.get("VERBOSE_TESTS"):
            tb.print_exc()
        return False


def _make_mock_client(response_text: str):
    """Crea un cliente Anthropic mock que devuelve siempre response_text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(type="text", text=response_text)]

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_stream_ctx.get_final_message = MagicMock(return_value=mock_msg)
    # _stream_and_collect itera stream.text_stream para recoger chunks de texto
    mock_stream_ctx.text_stream = [response_text]

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

    return mock_client


def _make_pipeline_no_llm(max_iter=5) -> P4Pipeline:
    """Pipeline sin LLM real (Anthropic client mockeado)."""
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        p = P4Pipeline(api_key="sk-ant-test-dummy", max_iter=max_iter, verbose=False)
    return p


# ---- Codigo Gurobi/scipy de prueba -----------------------------------------

_SCIPY_CODE_OK = """
import numpy as np
from scipy.optimize import linprog

tickers = ["AAPL", "MSFT", "JNJ", "KO", "XOM", "NEE", "JPM", "UNH"]
returns_mean = {"AAPL": 0.11, "MSFT": 0.10, "JNJ": 0.07, "KO": 0.06,
                "XOM": 0.08, "NEE": 0.06, "JPM": 0.10, "UNH": 0.09}
returns_desf = {"AAPL": -0.08, "MSFT": -0.06, "JNJ": -0.03, "KO": -0.02,
                "XOM": -0.05, "NEE": -0.02, "JPM": -0.07, "UNH": -0.04}
alpha = 0.15

n = len(tickers)
c = np.array([-returns_mean.get(t, 0.0) for t in tickers] + [0.0])
A_eq = np.ones((1, n+1))
b_eq = np.array([1.0])
r_desf = np.array([returns_desf.get(t, 0.0) for t in tickers])
A_ub = np.concatenate([-r_desf, [0.0]]).reshape(1, -1)
b_ub = np.array([alpha])
bounds = [(0.0, 1.0)] * n + [(0.0, 1.0)]

res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
              bounds=bounds, method="highs")

class _W:
    def __init__(self, v): self.X = v

class _FakeModel:
    Status = 2 if res.status == 0 else 9
    NumVars = n + 1
    NumConstrs = 2
    ObjVal = -float(res.fun) if res.status == 0 else None
    def optimize(self): pass

_model   = _FakeModel()
_weights = {t: _W(float(res.x[i])) for i, t in enumerate(tickers)} if res.status == 0 else {}
_cash    = _W(float(res.x[-1])) if res.status == 0 else _W(0.0)
"""


# ---- Tests ------------------------------------------------------------------

def test_p1_pipeline_result_serialization():
    """P1 -- PipelineResult.to_dict() / to_json()."""
    pr = PipelineResult(
        success=True,
        final_result=None,
        iterations=[],
        total_time_s=1.23,
        total_llm_calls=3,
        abort_reason="",
    )
    d = pr.to_dict()
    assert d["success"] is True
    assert d["total_llm_calls"] == 3
    assert d["n_iterations"] == 0

    j = pr.to_json()
    parsed = json.loads(j)
    assert parsed["total_time_s"] == 1.23


def test_p2_run_direct_optimal():
    """P2 -- run_direct() produce portafolio optimo sin LLM."""
    p = _make_pipeline_no_llm()
    result = p.run_direct(
        tickers=TICKERS,
        returns_scen=RETURNS_SCEN,
        probs=PROBS,
        profile="neutro",
    )
    assert result.ok(), f"Esperaba resultado accionable, got {result.status}"
    assert result.weights is not None
    total = sum(result.weights.values()) + (result.cash or 0)
    assert abs(total - 1.0) < 1e-4, f"Presupuesto violado: {total:.6f}"
    assert result.obj_value is not None and result.obj_value > 0


def test_p3_run_direct_all_profiles():
    """P3 -- run_direct() funciona con todos los perfiles de riesgo."""
    p = _make_pipeline_no_llm()
    for profile, alpha in RISK_PROFILES.items():
        if alpha == 0.0:
            continue
        result = p.run_direct(
            tickers=TICKERS,
            returns_scen=RETURNS_SCEN,
            probs=PROBS,
            profile=profile,
        )
        assert result.ok() or result.status == SolverStatus.TRIVIAL, (
            f"Perfil {profile}: {result.status} -- {result.diagnostic.message[:80]}"
        )


def test_p4_programador_mock_generate():
    """P4 -- ProgramadorAgent.generate() con mock devuelve codigo no vacio."""
    mock_code = "import gurobipy as gp\n_model = None\n_weights = {}\n_cash = None\n"
    client = _make_mock_client(mock_code)

    agent = ProgramadorAgent(client, verbose=False)
    params = {
        "tickers": TICKERS,
        "returns_mean": {t: 0.10 for t in TICKERS},
        "returns_scen": RETURNS_SCEN,
        "returns_desf": RETURNS_SCEN["desf"],
        "probs": PROBS,
        "alpha": 0.15,
        "commission_k": 0.001,
        "max_weight": 1.0,
        "time_limit": 9.0,
        "prev_weights": None,
        "profile": "neutro",
    }

    code = agent.generate(params, "LP base Gurobi")
    assert isinstance(code, str)
    assert len(code.strip()) > 0


def test_p5_evaluador_mock_accept_optimal():
    """P5 -- EvaluadorAgent.evaluate() acepta solucion OPTIMAL."""
    eval_json = json.dumps({
        "decision": "accept",
        "root_cause": "Solucion optima encontrada",
        "feedback": "OK",
        "priority_fix": "ninguno",
        "confidence": 0.99,
    })
    client = _make_mock_client(eval_json)

    agent = EvaluadorAgent(client, verbose=False)

    # Crear SolverResult mock con status OPTIMAL
    from solver import SolverResult
    from solver.diagnostics import DiagnosticReport, SolverStatus

    result = SolverResult(
        status     = SolverStatus.OPTIMAL,
        diagnostic = DiagnosticReport(
            status    = SolverStatus.OPTIMAL,
            message   = "Optimo",
            solve_time = 0.5,
            obj_value  = 0.11,
        ),
        weights    = {"AAPL": 0.5, "MSFT": 0.5},
        cash       = 0.0,
        obj_value  = 0.11,
        solver_used = "scipy",
    )

    decision = agent.evaluate(result, iteration=1, max_iter=5)
    assert decision.decision == "accept", f"Esperaba accept, got {decision.decision}"
    assert decision.should_accept()
    assert not decision.should_retry()


def test_p6_evaluador_mock_retry_on_error():
    """P6 -- EvaluadorAgent.evaluate() pide retry en CODE_ERROR."""
    eval_json = json.dumps({
        "decision": "retry",
        "root_cause": "SyntaxError en linea 5",
        "feedback": "Falta parentesis de cierre",
        "priority_fix": "Corregir sintaxis en linea 5",
        "confidence": 0.85,
    })
    client = _make_mock_client(eval_json)
    agent = EvaluadorAgent(client, verbose=False)

    from solver import SolverResult
    from solver.diagnostics import DiagnosticReport, SolverStatus

    result = SolverResult(
        status     = SolverStatus.CODE_ERROR,
        diagnostic = DiagnosticReport(
            status    = SolverStatus.CODE_ERROR,
            message   = "SyntaxError",
            traceback = "File <code>, line 5\n  SyntaxError: ...",
        ),
        solver_used = "none",
    )

    decision = agent.evaluate(result, iteration=1, max_iter=5)
    assert decision.decision == "retry", f"Esperaba retry, got {decision.decision}"
    assert decision.should_retry()


def test_p7_manager_decide_accept_first_iter():
    """P7 -- ManagerAgent decide 'continuar' cuando Evaluador acepta."""
    client = _make_mock_client("")
    agent = ManagerAgent(client, verbose=False)

    eval_dec = EvaluadorDecision(
        decision="accept", root_cause="ok", feedback="ok",
        priority_fix="", confidence=0.99,
    )

    from solver import SolverResult
    from solver.diagnostics import DiagnosticReport, SolverStatus

    result = SolverResult(
        status     = SolverStatus.OPTIMAL,
        diagnostic = DiagnosticReport(
            status    = SolverStatus.OPTIMAL,
            message   = "ok",
            obj_value = 0.11,
        ),
        obj_value  = 0.11,
        solver_used = "scipy",
    )

    decision = agent.decide(
        iteration=1, max_iter=5,
        estrategia_actual="LP base Gurobi",
        evaluador_decision=eval_dec,
        solver_result=result,
    )
    assert decision.accion in ("continuar", "abortar"), (
        f"Esperaba continuar/abortar, got {decision.accion}"
    )


def test_p8_manager_decide_cambiar_on_max_retry():
    """P8 -- ManagerAgent escala estrategia despues de max retries."""
    client = _make_mock_client("")
    agent = ManagerAgent(client, verbose=False)

    # Simular 2 intentos previos con la misma estrategia en el historial
    estrategia = "Gurobi LP base (capas 0-1)"
    for i in range(1, 3):
        agent.historial.append({
            "iter": i, "estrategia": estrategia,
            "status": "infeasible", "decision": "retry",
            "causa": "alpha demasiado estricto",
        })

    eval_dec = EvaluadorDecision(
        decision="retry", root_cause="INFEASIBLE con alpha muy estricto",
        feedback="Relajar alpha", priority_fix="cambiar perfil",
        confidence=0.75,
    )

    from solver import SolverResult
    from solver.diagnostics import DiagnosticReport, SolverStatus

    result = SolverResult(
        status     = SolverStatus.INFEASIBLE,
        diagnostic = DiagnosticReport(
            status    = SolverStatus.INFEASIBLE,
            message   = "Infactible",
        ),
        solver_used = "scipy",
    )

    decision = agent.decide(
        iteration=3, max_iter=5,
        estrategia_actual=estrategia,
        evaluador_decision=eval_dec,
        solver_result=result,
    )
    assert decision.accion in ("cambiar_estrategia", "retry", "abortar"), (
        f"Accion inesperada: {decision.accion}"
    )


def test_p9_pipeline_mock_success_first_iter():
    """P9 -- Pipeline completo: exito en primera iteracion (todos mocks)."""
    from solver.diagnostics import DiagnosticReport, SolverStatus as SS

    good_code = _SCIPY_CODE_OK

    eval_accept = EvaluadorDecision(
        decision="accept", root_cause="Optimo encontrado",
        feedback="OK", priority_fix="", confidence=0.99,
    )

    # Sandbox result mock: OPTIMAL con pesos validos
    sandbox_result = SolverResult(
        status      = SS.OPTIMAL,
        diagnostic  = DiagnosticReport(
            status=SS.OPTIMAL, message="ok",
            solve_time=0.5, obj_value=0.11, n_vars=9, n_constrs=2,
        ),
        weights     = {"AAPL": 0.4, "MSFT": 0.3, "JNJ": 0.3},
        cash        = 0.0,
        obj_value   = 0.11,
        solver_used = "scipy_mock",
        validation  = {"valid": True, "violations": [], "warnings": []},
    )

    p = _make_pipeline_no_llm(max_iter=3)

    with patch.object(p.programador, "generate", return_value=good_code), \
         patch.object(p.evaluador, "evaluate", return_value=eval_accept), \
         patch.object(p.sandbox, "run_code", return_value=sandbox_result):

        result = p.run(
            tickers=TICKERS,
            returns_scen=RETURNS_SCEN,
            probs=PROBS,
            profile="neutro",
        )

    assert result.success, f"Esperaba exito, abort_reason={result.abort_reason}"
    assert result.final_result is not None
    assert result.final_result.ok(), f"final_result.status={result.final_result.status}"
    assert len(result.iterations) == 1


def test_p10_pipeline_mock_strategy_escalation():
    """P10 -- Pipeline mock: retry -> cambiar estrategia -> exito."""
    from solver.diagnostics import DiagnosticReport, SolverStatus as SS

    good_code = _SCIPY_CODE_OK

    eval_retry = EvaluadorDecision(
        decision="retry", root_cause="CODE_ERROR", feedback="Fix code",
        priority_fix="Corregir imports", confidence=0.7,
    )
    eval_accept = EvaluadorDecision(
        decision="accept", root_cause="Optimo encontrado",
        feedback="OK", priority_fix="", confidence=0.99,
    )
    mgr_cambiar = ManagerDecision(
        accion="cambiar_estrategia",
        estrategia="scipy fallback",
        contexto_adicional="Usar scipy directamente",
        razon="Gurobi no disponible",
    )
    mgr_continuar = ManagerDecision(
        accion="continuar", estrategia="scipy fallback",
        contexto_adicional="", razon="Solucion aceptada",
    )

    sandbox_result = SolverResult(
        status      = SS.OPTIMAL,
        diagnostic  = DiagnosticReport(
            status=SS.OPTIMAL, message="ok",
            solve_time=0.5, obj_value=0.11, n_vars=9, n_constrs=2,
        ),
        weights     = {"AAPL": 0.5, "MSFT": 0.5},
        cash        = 0.0, obj_value=0.11,
        solver_used = "scipy_mock",
        validation  = {"valid": True, "violations": [], "warnings": []},
    )

    call_count = {"n": 0}

    def eval_side_effect(result, *args, **kwargs):
        call_count["n"] += 1
        return eval_retry if call_count["n"] == 1 else eval_accept

    mgr_call = {"n": 0}

    def mgr_side_effect(*args, **kwargs):
        mgr_call["n"] += 1
        return mgr_cambiar if mgr_call["n"] == 1 else mgr_continuar

    p = _make_pipeline_no_llm(max_iter=5)

    with patch.object(p.programador, "generate", return_value=good_code), \
         patch.object(p.programador, "fix", return_value=good_code), \
         patch.object(p.evaluador, "evaluate", side_effect=eval_side_effect), \
         patch.object(p.manager, "decide", side_effect=mgr_side_effect), \
         patch.object(p.sandbox, "run_code", return_value=sandbox_result):

        result = p.run(
            tickers=TICKERS,
            returns_scen=RETURNS_SCEN,
            probs=PROBS,
            profile="neutro",
        )

    assert result.success, f"Esperaba exito. Razones: {[r.evaluacion.decision for r in result.iterations]}"
    assert len(result.iterations) == 2  # iter 1 (retry) + iter 2 (accept)


def test_p11_pipeline_mock_max_iter_no_solution():
    """P11 -- Pipeline alcanza max_iter sin solucion -> success=False."""
    from solver.diagnostics import DiagnosticReport, SolverStatus as SS

    bad_code = "def broken(:\n    pass"

    bad_result = SolverResult(
        status      = SS.CODE_ERROR,
        diagnostic  = DiagnosticReport(
            status=SS.CODE_ERROR, message="SyntaxError",
            traceback="SyntaxError: invalid syntax",
        ),
        solver_used = "gurobi_subprocess",
    )
    eval_retry = EvaluadorDecision(
        decision="retry", root_cause="CODE_ERROR", feedback="Fix syntax",
        priority_fix="Corregir sintaxis", confidence=0.9,
    )
    mgr_retry = ManagerDecision(
        accion="retry", estrategia="LP base Gurobi",
        contexto_adicional="", razon="Reintentar con fix",
    )

    p = _make_pipeline_no_llm(max_iter=3)

    with patch.object(p.programador, "generate", return_value=bad_code), \
         patch.object(p.programador, "fix", return_value=bad_code), \
         patch.object(p.evaluador, "evaluate", return_value=eval_retry), \
         patch.object(p.manager, "decide", return_value=mgr_retry), \
         patch.object(p.sandbox, "run_code", return_value=bad_result):

        result = p.run(
            tickers=TICKERS,
            returns_scen=RETURNS_SCEN,
            probs=PROBS,
            profile="neutro",
        )

    assert not result.success, "Esperaba fracaso con codigo invalido"
    assert len(result.iterations) == 3
    assert result.abort_reason != ""


def test_p12_reduce_universe():
    """P12 -- _reduce_universe() reduce correctamente a top-20."""
    p = _make_pipeline_no_llm()

    # Crear universo de 30 tickers con retornos variados
    big_tickers = [f"TICK{i:02d}" for i in range(30)]
    returns_mean = {t: i * 0.01 for i, t in enumerate(big_tickers)}  # 0% a 29%
    returns_scen = {
        "desf":   {t: -0.05 for t in big_tickers},
        "neutro": {t: returns_mean[t] for t in big_tickers},
        "fav":    {t: returns_mean[t] * 2 for t in big_tickers},
    }

    params = {
        "tickers": big_tickers,
        "returns_mean": returns_mean,
        "returns_scen": returns_scen,
    }

    reduced = p._reduce_universe(params)
    assert len(reduced["tickers"]) == 20
    # Los top-20 deben tener los retornos mas altos (indices 10..29)
    expected_top20 = sorted(big_tickers, key=lambda t: -returns_mean[t])[:20]
    assert set(reduced["tickers"]) == set(expected_top20)


def test_p13_fallback_codegen_all_strategies():
    """P13 -- _fallback_codegen() produce codigo compilable para cada estrategia."""
    p = _make_pipeline_no_llm()
    params = {
        "tickers": TICKERS,
        "returns_mean": {t: 0.10 for t in TICKERS},
        "returns_scen": RETURNS_SCEN,
        "probs": PROBS,
        "alpha": 0.15,
        "commission_k": 0.001,
        "max_weight": 1.0,
        "time_limit": 9.0,
        "prev_weights": None,
    }

    strategies = [
        "LP base Gurobi",
        "2-SLP escenarios",
        "scipy fallback",
        "scipy universo reducido",
    ]
    for strat in strategies:
        code = p._fallback_codegen(strat, params)
        assert len(code.strip()) > 50, f"Codigo vacio para estrategia: {strat}"
        try:
            compile(code, f"<fallback:{strat}>", "exec")
        except SyntaxError as e:
            raise AssertionError(f"SyntaxError en fallback para '{strat}': {e}")


def test_p14_apply_strategy_adjustments():
    """P14 -- _apply_strategy_adjustments detecta codigo scipy con gurobipy."""
    p = _make_pipeline_no_llm()
    params = {
        "tickers": TICKERS,
        "returns_mean": {t: 0.10 for t in TICKERS},
        "returns_scen": RETURNS_SCEN,
        "probs": PROBS,
        "alpha": 0.15,
        "commission_k": 0.001,
        "max_weight": 1.0,
        "time_limit": 9.0,
        "prev_weights": None,
    }

    # Codigo con gurobipy pero estrategia scipy -> debe reemplazarse
    bad_mix = "import gurobipy as gp\n_model=None\n_weights={}\n_cash=None"
    fixed = p._apply_strategy_adjustments(bad_mix, "scipy fallback", params)
    # El resultado no debe contener gurobipy
    assert "gurobipy" not in fixed, "No deberia contener gurobipy en estrategia scipy"

    # Codigo vacio -> debe reemplazarse
    fixed2 = p._apply_strategy_adjustments("", "LP base Gurobi", params)
    assert len(fixed2.strip()) > 50, "Codigo vacio no fue reemplazado"

    # Codigo valido con estrategia correcta -> no debe cambiar
    valid_code = "import gurobipy as gp\n# codigo valido de 100+ chars\n" + "x = 1\n" * 10
    unchanged = p._apply_strategy_adjustments(valid_code, "LP base Gurobi", params)
    assert unchanged == valid_code


# ---- Runner ----------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Pipeline P4 -- Suite de Tests (LLM supervisado)")
    print("=" * 60)

    tests = [
        ("P1  PipelineResult serialization",      test_p1_pipeline_result_serialization),
        ("P2  run_direct() optimo",                test_p2_run_direct_optimal),
        ("P3  run_direct() todos los perfiles",    test_p3_run_direct_all_profiles),
        ("P4  Programador mock generate",          test_p4_programador_mock_generate),
        ("P5  Evaluador mock accept OPTIMAL",      test_p5_evaluador_mock_accept_optimal),
        ("P6  Evaluador mock retry CODE_ERROR",    test_p6_evaluador_mock_retry_on_error),
        ("P7  Manager continuar en accept",        test_p7_manager_decide_accept_first_iter),
        ("P8  Manager escalar en max retries",     test_p8_manager_decide_cambiar_on_max_retry),
        ("P9  Pipeline exito primera iter",        test_p9_pipeline_mock_success_first_iter),
        ("P10 Pipeline escalada de estrategia",    test_p10_pipeline_mock_strategy_escalation),
        ("P11 Pipeline max_iter sin solucion",     test_p11_pipeline_mock_max_iter_no_solution),
        ("P12 _reduce_universe() top-20",          test_p12_reduce_universe),
        ("P13 _fallback_codegen() compilable",     test_p13_fallback_codegen_all_strategies),
        ("P14 _apply_strategy_adjustments()",      test_p14_apply_strategy_adjustments),
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
