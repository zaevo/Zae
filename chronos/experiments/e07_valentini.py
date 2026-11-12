"""E7 — Pilot-wave (de Broglie–Bohm) quantum non-equilibrium (Valentini 1991, 2002).

Two entangled particles in 1D (hbar=m=1). Alice chooses at t=0 between
  choice 0: free evolution of particle 1
  choice 1: particle 1 in a harmonic trap (omega=1.5)
Bob never touches particle 2 and records x2 at time T.

We evolve psi on a 2D grid (split-step FFT), integrate Bohm trajectories
(dx/dt = Im(grad psi / psi)) for an ensemble drawn from
  (a) quantum equilibrium  rho = |psi|^2
  (b) non-equilibrium      rho = narrowed in x1 (sub-quantum 'relic' distribution)
and compare Bob's x2 statistics across Alice's choice.  Same initial positions
are used for both choices (paired design) to remove sampling noise.

Prediction: (a) Bob's distribution is invariant although individual
trajectories move (hidden nonlocality, no signal); (b) Bob's distribution
shifts -> instantaneous signalling. In Valentini's theory this is signalling
relative to a preferred foliation: superluminal, but NOT backward in time
unless combined with relativity-of-simultaneity."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from scipy.ndimage import map_coordinates

Lbox, N = 30.0, 192
x = np.linspace(-Lbox / 2, Lbox / 2, N, endpoint=False)
dx = x[1] - x[0]
k = 2 * np.pi * np.fft.fftfreq(N, d=dx)
X1, X2 = np.meshgrid(x, x, indexing='ij')
K1, K2 = np.meshgrid(k, k, indexing='ij')
sp, sm = 1.6, 0.5  # widths of (x1+x2) and (x1-x2): strongly entangled


def psi0():
    p = np.exp(-((X1 + X2) ** 2) / (8 * sp ** 2) - ((X1 - X2) ** 2) / (8 * sm ** 2)).astype(complex)
    return p / np.sqrt(np.sum(np.abs(p) ** 2) * dx * dx)


def step(psi, V, dt):
    psi = psi * np.exp(-0.5j * V * dt)
    psi = np.fft.ifft2(np.fft.fft2(psi) * np.exp(-0.5j * (K1 ** 2 + K2 ** 2) * dt))
    return psi * np.exp(-0.5j * V * dt)


def velocity(psi):
    f = np.fft.fft2(psi)
    d1 = np.fft.ifft2(1j * K1 * f); d2 = np.fft.ifft2(1j * K2 * f)
    den = np.abs(psi) ** 2 + 1e-30
    return np.imag(np.conj(psi) * d1) / den, np.imag(np.conj(psi) * d2) / den


def interp(F, pos):
    idx = (pos - x[0]) / dx
    return map_coordinates(F, idx, order=1, mode='nearest')


def simulate(choice, pts, T=3.0, dt=0.005):
    V = 0.5 * 1.5 ** 2 * X1 ** 2 if choice == 1 else np.zeros_like(X1)
    psi = psi0(); pts = pts.copy()
    for _ in range(int(T / dt)):
        v1, v2 = velocity(psi)
        mid = pts + 0.5 * dt * np.stack([interp(v1, pts), interp(v2, pts)])
        psi_half = step(psi, V, dt / 2)
        v1h, v2h = velocity(psi_half)
        pts = pts + dt * np.stack([interp(v1h, mid), interp(v2h, mid)])
        psi = step(psi, V, dt)
    marg = np.sum(np.abs(psi) ** 2, axis=0) * dx  # Born marginal of x2
    return pts, marg


def sample(n, rng, noneq):
    # equilibrium covariance of |psi0|^2 in (u=x1+x2, w=x1-x2): var u = 4 sp^2... use exact:
    # |psi0|^2 = exp(-u^2/(4 sp^2) - w^2/(4 sm^2)) -> var u = 2 sp^2, var w = 2 sm^2
    u = rng.normal(0, np.sqrt(2) * sp, n); w = rng.normal(0, np.sqrt(2) * sm, n)
    x1, x2 = (u + w) / 2, (u - w) / 2
    if noneq:  # squeeze particle-1 coordinate: rho != |psi|^2
        x1 = 0.35 * x1
    return np.stack([x1, x2])


def tv_hist(a, b, bins):
    ha, _ = np.histogram(a, bins=bins); hb, _ = np.histogram(b, bins=bins)
    return 0.5 * np.sum(np.abs(ha / ha.sum() - hb / hb.sum()))


def run(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    out = {}
    bins = np.linspace(-8, 8, 33)
    for label, noneq in (("equilibrium", False), ("non_equilibrium", True)):
        p0 = sample(n, rng, noneq)
        (r0, m0), (r1, m1) = simulate(0, p0), simulate(1, p0)
        x2a, x2b = r0[1], r1[1]
        out[label] = {
            "mean_x2 | Alice free": float(x2a.mean()), "mean_x2 | Alice trap": float(x2b.mean()),
            "var_x2 | Alice free": float(x2a.var()), "var_x2 | Alice trap": float(x2b.var()),
            "mean |per-trajectory displacement of x2 caused by Alice|": float(np.mean(np.abs(x2a - x2b))),
            "TV distance of Bob's histograms": tv_hist(x2a, x2b, bins),
            "z-score of variance change (|dVar| / std.err)": float(abs(x2a.var() - x2b.var()) /
                                                              (np.sqrt(2.0 / n) * 0.5 * (x2a.var() + x2b.var())))}
        out["born_marginal_TV_between_choices (exact)"] = float(0.5 * np.sum(np.abs(m0 - m1)) * dx)
    # sampling-noise floor for TV with two independent equilibrium samples
    a = sample(n, rng, False)[1]; b = sample(n, rng, False)[1]
    out["TV noise floor (independent samples, same dist)"] = tv_hist(a, b, bins)
    return out


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
