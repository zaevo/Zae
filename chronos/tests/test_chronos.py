"""Fast regression tests: each asserts a claim made in REPORT.md."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from experiments import e01_no_signaling as e1, e02_postselection_budget as e2, e03_pctc as e3
from experiments import e04_dctc as e4, e05_nonlinear_qm as e5, e09_weak_values as e9


def test_no_future_operation_changes_past_marginal():
    r = e1.stress_test(trials=60)
    assert r["max_trace_distance_between_past_marginals"] < 1e-12
    assert r["max_capacity_bits"] < 1e-12


def test_eraser_is_conditional_only():
    r = e1.eraser()
    assert r["capacity_b_to_s_unconditional_bits"] < 1e-12
    assert abs(r["X_eraser"]["I(S;I|b) bits"] - 1) < 1e-9


def test_postselection_budget_theorem():
    assert e2.random_check(n=3000) <= 1 + 1e-9
    assert e2.adversarial(restarts=5, steps=600) <= 1 + 1e-9
    for row in e2.tightness():
        assert abs(row["I(M;R|S)"] - row["log2(1/p)"]) < 1e-9


def test_pctc_formula_and_message():
    assert e3.verify_formula(n=50) < 1e-10
    m = e3.message_to_past()
    assert m["capacity_unconditional_bits"] < 1e-12
    assert abs(m["capacity_conditional_bits"] - 1) < 1e-9
    assert abs(m["m=0"]["P(herald)"] - 0.25) < 1e-12


def test_pctc_grandfather_always_misfires():
    for row in e3.grandfather():
        assert row["P(misfire | consistent history)"] > 1 - 1e-9


def test_dctc_message_and_nonlinearity():
    m = e4.message_to_past()
    assert abs(m["capacity_unconditional_bits"] - 1) < 1e-9
    b = e4.bhw()
    assert b["found"] and min(b["P(correct | psi_k) for |0>,|1>,|+>,|->"]) > 1 - 1e-9
    assert b["linearity_defect_trace_distance"] > 0.1
    assert e4.grandfather()["fixed-space dimension (1 => unique)"] > 1


def test_nonlinear_branch_signals_reduced_does_not():
    yb = [e5.bob_sigma_y(c, 1.0, 0.3, 'branch') for c in (0, 1)]
    yr = [e5.bob_sigma_y(c, 1.0, 0.3, 'reduced') for c in (0, 1)]
    assert abs(yb[0] - yb[1]) > 0.3
    assert abs(yr[0] - yr[1]) < 1e-12


def test_weak_values_no_unconditional_info():
    r = e9.run()
    assert r["I(m ; pointer) unconditional bits"] < 1e-10
    assert r["I(m ; pointer | postselected) bits"] <= r["budget log2(1/P(postselect))"]
    a = r["m0_anomalous"]
    assert abs(a["simulated conditional shift"] - a["predicted shift g*A_w"]) < 0.02
