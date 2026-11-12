"""E5 — Nonlinear quantum dynamics ⇒ signalling ⇒ (with Lorentz covariance) signals
into the past.  (Gisin 1990, Polchinski 1991, Czachor; counterpoint: Kent 2005.)

Bob holds half of a Bell pair. Alice (spacelike-separated, or later in Bob's
frame) chooses to measure Z (m=0) or X (m=1).  Bob's qubit then evolves under a
Weinberg-type state-dependent Hamiltonian H[psi] = eps <sigma_z>_psi sigma_x for time t,
and Bob measures sigma_y.

Two nonlinear models are tested:
  'branch'  — nonlinearity acts on the collapsed branch states (Weinberg/Gisin)
  'reduced' — nonlinearity acts on Bob's reduced density matrix (Kent-style)
Prediction: 'branch' signals; 'reduced' does not.  We also compute the
relativistic consequence: a spacelike signal of speed u relayed by a moving
partner returns before it was sent if u*v > c^2."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import ket, X, Y, Z, dm, blahut_arimoto
from scipy.linalg import expm

ZB = [ket('0'), ket('1')]
XB = [(ket('0') + ket('1')) / np.sqrt(2), (ket('0') - ket('1')) / np.sqrt(2)]


def evolve_branch(psi, eps, t, steps=400):
    dt = t / steps
    for _ in range(steps):
        Hs = eps * np.real(psi.conj() @ Z @ psi) * X
        psi = expm(-1j * Hs * dt) @ psi
        psi /= np.linalg.norm(psi)
    return psi


def evolve_reduced(rho, eps, t, steps=400):
    dt = t / steps
    for _ in range(steps):
        Hs = eps * np.real(np.trace(rho @ Z)) * X
        Ud = expm(-1j * Hs * dt)
        rho = Ud @ rho @ Ud.conj().T
    return rho


def bob_sigma_y(choice, eps, t, model):
    branches = ZB if choice == 0 else XB  # Bell state: Bob's conditional states mirror Alice's basis
    if model == 'branch':
        return float(np.mean([np.real(p.conj() @ Y @ p) for p in (evolve_branch(b, eps, t) for b in branches)]))
    rho = 0.5 * sum(dm(b) for b in branches)  # = I/2 either way
    return float(np.real(np.trace(evolve_reduced(rho, eps, t) @ Y)))


def run():
    rows = []
    for theta in [0.0, 1e-3, 1e-2, 0.1, 0.3, 0.785398, 1.570796]:
        r = {"eps*t": theta}
        for model in ('branch', 'reduced'):
            ys = [bob_sigma_y(c, 1.0, theta, model) for c in (0, 1)]
            Wm = [[(1 + y) / 2, (1 - y) / 2] for y in ys]
            r[model] = {"<sy>|Alice=Z": ys[0], "<sy>|Alice=X": ys[1],
                        "capacity_bits_per_trial": blahut_arimoto(Wm)}
        rows.append(r)
    # small-theta scaling of 'branch' capacity
    th = np.array([1e-3, 3e-3, 1e-2])
    caps = [blahut_arimoto([[(1 - np.sin(x)) / 2, (1 + np.sin(x)) / 2], [0.5, 0.5]]) for x in th]
    slope = np.polyfit(np.log(th), np.log(caps), 1)[0]
    # tachyonic antitelephone (units c=1): A sends at speed u to B at distance L (A frame);
    # B moves at speed v away and replies at speed u in B's frame.
    def return_time(u, v, L=1.0):
        # event B receives: in A frame, t1 = L/u, x1 = L. Reply in B frame with speed -u.
        g = 1 / np.sqrt(1 - v * v)
        tB, xB = g * (L / u - v * L), g * (L - v * L / u)
        # reply worldline in B frame: x' = xB - u (t' - tB). Reaches A's worldline x = 0 -> in B-frame x'=-g v t, t'=g t ... solve
        # A worldline in B coords: x' = -v t'. Intersection: xB - u (t' - tB) = -v t'
        tp = (xB + u * tB) / (u - v)
        xp = -v * tp
        return g * (tp + v * xp)  # back to A frame time
    tachyon = [{"u/c": u, "v/c": v, "reply_arrives_at_t (sent at t=0)": float(return_time(u, v))}
               for (u, v) in [(2.0, 0.3), (2.0, 0.6), (10.0, 0.5), (1e6, 0.2)]]
    return {"table": rows, "branch_capacity_scaling_exponent (C ~ (eps t)^k)": float(slope),
            "experimental_bound_note": "Bollinger et al. PRL 63, 1058 (1989): Weinberg nonlinearity "
                                       "< ~4e-27 of the 9Be+ binding energy per nucleon.",
            "tachyonic_antitelephone": tachyon}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
