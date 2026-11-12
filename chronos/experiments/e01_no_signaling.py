"""E1 — Baseline theorem, stress-tested: in linear, Born-rule QM with a global
time order, NO operation in the future changes any past marginal.

Setup per trial: random pure state on P (past lab) ⊗ F (future lab) ⊗ E (environment).
P is read out at t1. At t2 > t1 the future agent picks one of K "messages",
each encoded as an arbitrary CPTP map (random Kraus channel, random unitary,
or a non-selective measurement) acting jointly on F⊗E. We compute rho_P(m) and
the classical capacity of the channel m -> P's measurement record.

Then the delayed-choice quantum eraser: correlations *conditioned* on the future
record exist (the "retrocausal-looking" pattern) while the unconditional past
record carries zero information about the future choice."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import (random_state, dm, random_kraus, random_unitary, apply_kraus,
                          ptrace, trace_distance, blahut_arimoto, mutual_info, H, I2, kron, bell, op_on)


def stress_test(trials=300, K=4, seed=1):
    rng = np.random.default_rng(seed)
    worst = 0.0
    caps = []
    for t in range(trials):
        dP, dF, dE = rng.choice([2, 3]), rng.choice([2, 3]), 2
        dims = [dP, dF, dE]
        rho = dm(random_state(dP * dF * dE, rng))
        # past measurement basis (random)
        Ub = random_unitary(dP, rng)
        marg = []
        for m in range(K):
            kind = m % 3
            if kind == 0:
                kr = random_kraus(dF * dE, 3, rng)
            elif kind == 1:
                kr = [random_unitary(dF * dE, rng)]
            else:  # non-selective projective measurement in random basis
                V = random_unitary(dF * dE, rng)
                kr = [np.outer(V[:, i], V[:, i].conj()) for i in range(dF * dE)]
            out = apply_kraus(rho, kr, [1, 2], dims)
            rP = ptrace(out, [0], dims)
            marg.append(rP)
        base = marg[0]
        for r in marg[1:]:
            worst = max(worst, trace_distance(base, r))
        W = np.array([np.real(np.diag(Ub.conj().T @ r @ Ub)) for r in marg])
        W = np.clip(W, 0, None); W /= W.sum(1, keepdims=True)
        caps.append(blahut_arimoto(W))
    return {"trials": trials, "messages_per_trial": K,
            "max_trace_distance_between_past_marginals": worst,
            "max_capacity_bits": max(caps)}


def eraser():
    """Signal photon S (past, measured in Z) entangled with idler I (future).
    Future agent chooses basis b in {Z ('which-path'), X ('eraser')} for I.
    Returns P(s | b) and P(s | b, i)."""
    psi = bell(0)  # (|00>+|11>)/sqrt2 on S,I ; S measured in X basis = "screen"
    rho = dm(psi)
    out = {}
    for b, U in (("Z_whichpath", I2), ("X_eraser", H)):
        R = kron(H, U)  # measure S in X ("interference fringe"), I in basis b
        p = np.real(np.diag(R.conj().T @ rho @ R)).reshape(2, 2)  # p[s,i]
        out[b] = {"P(s)": p.sum(1).tolist(),
                  "P(s|i=0)": (p[:, 0] / p[:, 0].sum()).tolist(),
                  "P(s|i=1)": (p[:, 1] / p[:, 1].sum()).tolist(),
                  "I(S;I|b) bits": mutual_info(p)}
    # channel b -> s (unconditional)
    W = np.array([out[k]["P(s)"] for k in out])
    out["capacity_b_to_s_unconditional_bits"] = blahut_arimoto(W)
    return out


def run():
    return {"stress_test": stress_test(), "delayed_choice_eraser": eraser()}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
