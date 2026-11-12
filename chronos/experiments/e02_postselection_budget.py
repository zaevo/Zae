"""E2 — The Postselection Budget Theorem (derived in REPORT.md §3).

If the past record R is (unconditionally) independent of the future message M —
which E1 shows is forced by linear Born-rule QM — then for ANY herald/postselection
event S with probability p = P(S):

        I(M ; R | S)  <=  log2(1/p)            (tight)

Proof sketch: I(M;R|S) = min_{Q_M,Q_R} D(P_{MR|S} || Q_M Q_R) <= D(P_{MR|S} || P_M P_R)
and P_{MR|S}(m,r) = P_M P_R P(S|m,r)/p <= P_M P_R / p, so D <= log(1/p).

So every "message from the future" obtained by postselection (P-CTCs, weak values,
quantum erasers, heralded teleportation) is paid for, bit-for-bit, by the
improbability of the herald — and the herald itself lives in the future.

Here we (a) verify on random instances, (b) run an adversarial optimiser trying
to break the bound, (c) show tightness."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import mutual_info


def cond_mi(pM, pR, like):
    joint = np.outer(pM, pR) * like
    p = joint.sum()
    return mutual_info(joint / p), p


def random_check(n=20000, seed=2):
    rng = np.random.default_rng(seed)
    worst_ratio = 0.0
    for _ in range(n):
        a, b = rng.integers(2, 9, size=2)
        pM = rng.dirichlet(np.ones(a) * rng.uniform(0.1, 2))
        pR = rng.dirichlet(np.ones(b) * rng.uniform(0.1, 2))
        like = rng.uniform(size=(a, b)) ** rng.uniform(0.2, 20)
        I, p = cond_mi(pM, pR, like)
        if p < 1 - 1e-12:
            worst_ratio = max(worst_ratio, I / np.log2(1 / p))
    return worst_ratio


def adversarial(restarts=40, steps=3000, seed=3):
    """Hill-climb on (pM, pR, likelihood) to maximise I / log2(1/p)."""
    rng = np.random.default_rng(seed)
    best = 0.0
    for _ in range(restarts):
        a, b = rng.integers(2, 6, size=2)
        th = [rng.normal(size=a), rng.normal(size=b), rng.normal(size=(a, b))]

        def score(th):
            pM = np.exp(th[0]); pM /= pM.sum()
            pR = np.exp(th[1]); pR /= pR.sum()
            like = 1 / (1 + np.exp(-th[2]))
            I, p = cond_mi(pM, pR, like)
            return I / np.log2(1 / p) if p < 1 - 1e-9 else 0.0
        s = score(th)
        step = 0.5
        for k in range(steps):
            cand = [t + step * rng.normal(size=t.shape) for t in th]
            sc = score(cand)
            if sc > s:
                th, s = cand, sc
            if k % 500 == 499:
                step *= 0.6
        best = max(best, s)
    return best


def tightness(nbits=(1, 2, 3, 4, 6)):
    out = []
    for n in nbits:
        N = 2 ** n
        pM = np.ones(N) / N; pR = np.ones(N) / N
        like = np.eye(N)  # herald = "past record happened to equal the message"
        I, p = cond_mi(pM, pR, like)
        out.append({"bits": n, "I(M;R|S)": I, "log2(1/p)": np.log2(1 / p)})
    return out


def run():
    return {"random_instances_max_ratio_I_over_log1p": random_check(),
            "adversarial_search_max_ratio": adversarial(),
            "tight_family": tightness(),
            "max_throughput_bits_per_trial_p_log1p": 1 / (np.e * np.log(2)),
            "interpretation": "ratio <= 1 always; equality reached. Throughput to an "
                              "observer who knows the herald is at most 0.531 bit/trial, "
                              "and 0 to anyone who does not."}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
