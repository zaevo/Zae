"""E6 — Born-rule deviations: the κ ↔ signalling bridge.

Hypothesis family: outcome weights w ∝ |amplitude|^(2+delta).
 (1) Sorkin's third-order interference κ becomes nonzero for delta != 0.
 (2) The same rule makes Bob's marginal depend on Alice's (remote or future)
     basis choice -> signalling capacity C(delta) > 0.
We map both as functions of delta, then invert the experimental bound on κ
(Kauten et al. NJP 19, 033017 (2017): higher-order interference > 4 orders of
magnitude below pairwise; we use |κ| < 1e-4 as an illustrative bound) into a
bound on how much retro/FTL signalling such a deviation could deliver."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import random_unitary, random_state, blahut_arimoto


def kappa(delta, n_phase=400):
    """Max |κ| over relative phases for three equal-amplitude paths at a point detector."""
    best = 0.0
    I = lambda amps: np.abs(np.sum(amps)) ** (2 + delta)
    for p2 in np.linspace(0, 2 * np.pi, 41):
        for p3 in np.linspace(0, 2 * np.pi, 41):
            a = np.array([1, np.exp(1j * p2), np.exp(1j * p3)]) / np.sqrt(3)
            PA, PB, PC = (I(a[[k]]) for k in range(3))
            PAB, PAC, PBC = I(a[[0, 1]]), I(a[[0, 2]]), I(a[[1, 2]])
            PABC = I(a)
            num = PABC - PAB - PAC - PBC + PA + PB + PC
            den = abs(PAB - PA - PB) + abs(PAC - PA - PC) + abs(PBC - PB - PC)
            if den > 1e-3:
                best = max(best, abs(num) / den)
    return best


def signalling_capacity(delta, samples=300, seed=5):
    rng = np.random.default_rng(seed)
    best = 0.0
    for _ in range(samples):
        psi = random_state(4, rng)
        A0, A1, B = random_unitary(2, rng), random_unitary(2, rng), random_unitary(2, rng)
        W = []
        for A in (A0, A1):
            amps = (np.kron(A, B).conj().T @ psi).reshape(2, 2)  # amps[i,j]
            w = np.abs(amps) ** (2 + delta)
            w /= w.sum()
            W.append(w.sum(0))  # Bob's marginal
        best = max(best, blahut_arimoto(W))
    return best


def run():
    rows = []
    for d in [0.0, 1e-4, 1e-3, 1e-2, 0.05, 0.1, 0.3]:
        rows.append({"delta": d, "max|kappa|": kappa(d), "max_signal_capacity_bits": signalling_capacity(d)})
    nz = [r for r in rows if r["delta"] > 0]
    kslope = np.polyfit(np.log([r["delta"] for r in nz]), np.log([r["max|kappa|"] for r in nz]), 1)
    cslope = np.polyfit(np.log([r["delta"] for r in nz]), np.log([r["max_signal_capacity_bits"] for r in nz]), 1)
    kappa_bound = 1e-4
    delta_max = float(np.exp((np.log(kappa_bound) - kslope[1]) / kslope[0]))
    cap_max = float(np.exp(cslope[1]) * delta_max ** cslope[0])
    return {"table": rows,
            "fit kappa ~ a*delta^k": {"k": float(kslope[0]), "a": float(np.exp(kslope[1]))},
            "fit C ~ b*delta^k": {"k": float(cslope[0]), "b": float(np.exp(cslope[1]))},
            "assumed |kappa| bound": kappa_bound,
            "implied |delta| bound": delta_max,
            "implied max signalling capacity bits/trial": cap_max,
            "trials needed for 1 bit": 1 / cap_max}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
