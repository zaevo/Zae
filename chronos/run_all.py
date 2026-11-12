"""Run every Chronos experiment, save JSON results, and print the scoreboard."""
import importlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXPS = ["e01_no_signaling", "e02_postselection_budget", "e03_pctc", "e04_dctc", "e05_nonlinear_qm",
        "e06_born_rule", "e07_valentini", "e08_causal_loops", "e09_weak_values", "e10_hardware_circuits"]
HERE = os.path.dirname(os.path.abspath(__file__))


def main(only=None):
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    R = {}
    for name in EXPS:
        if only and not any(o in name for o in only):
            continue
        t = time.time()
        mod = importlib.import_module(f"experiments.{name}")
        try:
            R[name] = mod.run()
        except ImportError as e:  # e.g. qiskit missing
            R[name] = {"skipped": str(e)}
        with open(os.path.join(HERE, "results", f"{name}.json"), "w") as f:
            json.dump(R[name], f, indent=2, default=float)
        print(f"[{time.time() - t:6.1f}s] {name}")
    if not only:
        print_scoreboard(R)


def print_scoreboard(R):
    g = lambda *ks: _get(R, ks)
    rows = [
        ("Standard QM, global order (E1)", "yes", "yes", "yes", g("e01_no_signaling", "stress_test", "max_capacity_bits")),
        ("Delayed-choice eraser (E1)", "yes", "yes", "yes", g("e01_no_signaling", "delayed_choice_eraser", "capacity_b_to_s_unconditional_bits")),
        ("Weak values + delayed postsel. (E9)", "yes", "yes", "yes", g("e09_weak_values", "I(m ; pointer) unconditional bits")),
        ("P-CTC, lab-realised (E3)", "yes", "yes", "yes", g("e03_pctc", "message_to_past", "capacity_unconditional_bits")),
        ("P-CTC, herald assumed (E3)", "NO (renorm.)", "yes", "no", g("e03_pctc", "message_to_past", "capacity_conditional_bits")),
        ("D-CTC (E4)", "NO (fixed pt)", "yes", "no", g("e04_dctc", "message_to_past", "capacity_unconditional_bits")),
        ("Weinberg branch nonlinearity, eps*t=0.3 (E5)", "NO", "yes", "yes", g("e05_nonlinear_qm", "table", 4, "branch", "capacity_bits_per_trial")),
        ("Kent-type reduced-state nonlinearity (E5)", "NO", "yes", "yes", g("e05_nonlinear_qm", "table", 4, "reduced", "capacity_bits_per_trial")),
        ("|psi|^(2+d) rule at kappa bound (E6)", "yes", "NO", "yes", g("e06_born_rule", "implied max signalling capacity bits/trial")),
        ("Classical process w/o causal order (E8)", "yes", "n/a", "NO", "cyclic; game " + str(g("e08_causal_loops", "game_value_BW")) + " > 0.75"),
    ]
    print("\nSCOREBOARD — signalling capacity from a later choice to an earlier record")
    print(f"{'model':48s} {'linear':14s} {'Born':5s} {'order':6s} capacity (bits/use)")
    for r in rows:
        v = r[4]
        vs = f"{v:.3g}" if isinstance(v, float) else str(v)
        print(f"{r[0]:48s} {r[1]:14s} {r[2]:5s} {r[3]:6s} {vs}")


def _get(d, ks):
    try:
        for k in ks:
            d = d[k]
        return d
    except (KeyError, IndexError, TypeError):
        return "n/a"


if __name__ == "__main__":
    main(sys.argv[1:] or None)
