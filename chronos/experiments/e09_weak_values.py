"""E9 — Two-state vector formalism / weak values with a *delayed, free* choice of
post-selection (Aharonov–Albert–Vaidman 1988; ABL 1964).

Qubit pre-selected in |psi>, weakly coupled (strength g) to a Gaussian pointer
(width s) via exp(-i g sigma_z ⊗ p). LATER the future agent chooses which state
|phi_m> to post-select on (m = 0: near-orthogonal -> anomalous weak value;
m = 1: trivial).  We compute:
  * conditional pointer shift  vs  g Re <phi|sz|psi>/<phi|psi>  (weak value)
  * unconditional pointer distribution for each m (should be identical)
  * the information the past pointer carries about m, conditional vs not,
    checked against the Postselection Budget Theorem."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import ket, Z, mutual_info


def run(g=0.01, s=1.0, alpha=0.04):
    q = np.linspace(-12, 12, 4801)
    G = lambda c: np.exp(-(q - c) ** 2 / (4 * s * s))
    psi = (ket('0') + ket('1')) / np.sqrt(2)
    # pointer-conditioned amplitudes: |0> shifts +g, |1> shifts -g
    branch = [psi[0] * G(+g), psi[1] * G(-g)]  # amplitude of qubit basis state j at pointer q
    targets = {"m0_anomalous": np.array([np.cos(np.pi / 4 + alpha), -np.sin(np.pi / 4 + alpha)], dtype=complex),
               "m1_trivial": psi.copy()}
    out = {}
    hist_uncond, hist_cond, psucc = [], [], []
    for name, phi in targets.items():
        phi_perp = np.array([np.conj(phi[1]), -np.conj(phi[0])])
        amp = lambda f: np.conj(f[0]) * branch[0] + np.conj(f[1]) * branch[1]
        Pcond = np.abs(amp(phi)) ** 2
        Pperp = np.abs(amp(phi_perp)) ** 2
        p = Pcond.sum() / (Pcond.sum() + Pperp.sum())
        mean_cond = (q * Pcond).sum() / Pcond.sum()
        uncond = (Pcond + Pperp); uncond /= uncond.sum()
        wv = np.real((phi.conj() @ Z @ psi) / (phi.conj() @ psi))
        out[name] = {"P(postselect)": float(p), "weak value Re A_w": float(wv),
                     "predicted shift g*A_w": float(g * wv), "simulated conditional shift": float(mean_cond),
                     "unconditional mean pointer": float((q * uncond).sum())}
        hist_uncond.append(uncond); hist_cond.append(Pcond / Pcond.sum()); psucc.append(p)
    # info about the future choice m in the past pointer (coarse-grained to 48 bins)
    def coarse(h):
        return h.reshape(-1, 100).sum(1) if h.size % 100 == 0 else np.add.reduceat(h, np.arange(0, h.size, 100))
    Hu = np.array([coarse(h) for h in hist_uncond]) * 0.5
    Hc = np.array([coarse(h) for h in hist_cond])
    joint_c = Hc * (np.array(psucc)[:, None] * 0.5); joint_c /= joint_c.sum()
    p_all = 0.5 * sum(psucc)
    out["I(m ; pointer) unconditional bits"] = mutual_info(Hu)
    out["I(m ; pointer | postselected) bits"] = mutual_info(joint_c)
    out["budget log2(1/P(postselect))"] = float(np.log2(1 / p_all))
    out["note"] = "unconditional pointer is identical for both future choices; amplification lives only in the rare post-selected subensemble"
    return out


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
