"""E4 — Deutsch CTCs: the one model in which a controllable message to the past
genuinely works (if a CTC exists) — and the price it pays.

(a) Message to the past: past register A, CTC qubit C, future message B.
    U = SWAP(B,C) after CNOT(C->A).  D-CTC consistency forces tau = |m><m|,
    so A reads m *unconditionally*: a 1-bit/use channel into the past.
(b) Grandfather paradox: tau = X tau X has a continuum of solutions
    (non-uniqueness); Deutsch picks max entropy -> coin flip.
(c) Brun–Harrington–Wilde-style perfect discrimination of the non-orthogonal BB84
    states (violates Helstrom/Holevo).  Construction found by exhaustive search.
(d) Bennett–Leung–Smith–Smolin 'linearity trap': D-CTC output on a mixture differs
    from the mixture of outputs, so 'what the past receives' depends on whether
    the future agent's randomness is proper or improper.  We quantify it."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import (ket, dm, kron, op_on, ptrace, cnot, swap_op, I2, X, H,
                          trace_distance, blahut_arimoto)
from chronos.dctc import dctc_output, fixed_points


def message_to_past():
    # CR = [A, B] (dcr=4), CTC = C (dc=2); full ordering [A, B, C]
    dims = [2, 2, 2]
    U = op_on(swap_op(), [1, 2], dims) @ op_on(cnot(), [2, 0], dims)
    W = []
    res = {}
    for m in (0, 1):
        rho_cr = dm(kron(ket('0'), ket(str(m))).ravel() if False else np.kron(ket('0'), ket(str(m))))
        out, tau, ndeg = dctc_output(rho_cr, U, 4, 2)
        pA = np.real(np.diag(ptrace(out, [0], [2, 2])))
        W.append(pA)
        res[f"m={m}"] = {"P(A) in the past": pA.round(12).tolist(), "fixed-space dim": ndeg}
    # quantum message: B=|+>  -> A gets a classical copy (Z-dephased)
    rho_cr = dm(np.kron(ket('0'), (ket('0') + ket('1')) / np.sqrt(2)))
    out, tau, _ = dctc_output(rho_cr, U, 4, 2)
    res["m=|+>: rho_A"] = np.real(ptrace(out, [0], [2, 2])).round(12).tolist()
    res["capacity_unconditional_bits"] = blahut_arimoto(W)
    return res


def grandfather():
    U = np.kron(I2, X)  # CR spectator, CTC bit flips itself
    rho_cr = dm(ket('0'))
    L, ndeg = fixed_points(rho_cr, U, 2, 2)
    out, tau, _ = dctc_output(rho_cr, U, 2, 2)
    return {"fixed-space dimension (1 => unique)": ndeg,
            "Deutsch max-entropy tau": np.real(tau).round(12).tolist()}


# ---- (c) BB84 discrimination --------------------------------------------------
STATES = [ket('0'), ket('1'), (ket('0') + ket('1')) / np.sqrt(2), (ket('0') - ket('1')) / np.sqrt(2)]
W_GATES = [I2, X, H, X @ H]  # W_j psi_j = |0>


def perms_sending_00_to(j):
    out = []
    for p in itertools.permutations(range(4)):
        if p[0] == j:
            P = np.zeros((4, 4)); P[list(p), range(4)] = 1
            out.append(P.astype(complex))
    return out


def chain_ok(Us):
    """For every input k, the D-CTC dynamics on the CTC label j must have the unique
    stationary distribution delta_k."""
    for k in range(4):
        T = np.zeros((4, 4))
        for j in range(4):
            v = Us[j] @ np.kron(STATES[k], ket('0'))
            T[:, j] = np.abs(v) ** 2
        w, V = np.linalg.eig(T)
        if np.sum(np.abs(w - 1) < 1e-9) != 1:
            return False
        s = np.real(V[:, np.argmin(np.abs(w - 1))]); s /= s.sum()
        if abs(s[k] - 1) > 1e-9:
            return False
    return True


def find_bhw():
    cands = [perms_sending_00_to(j) for j in range(4)]
    for combo in itertools.product(*cands):
        Us = [combo[j] @ np.kron(W_GATES[j], I2) for j in range(4)]
        if chain_ok(Us):
            return Us
    return None


def bhw_unitary(Us):
    # CR = 2 qubits (input, ancilla), CTC = 2 qubits. U = SWAP(CR,CTC) · sum_j U_j ⊗ |j><j|
    ctrl = sum(np.kron(Us[j], dm(np.eye(4)[j])) for j in range(4))
    S = np.zeros((16, 16), dtype=complex)
    for a in range(4):
        for b in range(4):
            S[b * 4 + a, a * 4 + b] = 1
    return S @ ctrl


def bhw():
    Us = find_bhw()
    if Us is None:
        return {"found": False}
    U = bhw_unitary(Us)
    probs = []
    for k in range(4):
        rho = dm(np.kron(STATES[k], ket('0')))
        out, tau, ndeg = dctc_output(rho, U, 4, 4)
        probs.append(float(np.real(out[k, k])))
    # Linearity trap: mixture of |0> and |+>
    rho_mix = 0.5 * dm(np.kron(STATES[0], ket('0'))) + 0.5 * dm(np.kron(STATES[2], ket('0')))
    out_mix, _, _ = dctc_output(rho_mix, U, 4, 4)
    outs = [dctc_output(dm(np.kron(STATES[k], ket('0'))), U, 4, 4)[0] for k in (0, 2)]
    mix_of_out = 0.5 * outs[0] + 0.5 * outs[1]
    # Helstrom optimum for 4 equiprobable BB84 states (standard QM)
    return {"found": True,
            "P(correct | psi_k) for |0>,|1>,|+>,|->": probs,
            "standard-QM optimum (pretty-good = Helstrom here)": 0.5,
            "linearity_defect_trace_distance": trace_distance(out_mix, mix_of_out),
            "output_on_mixture_diag": np.real(np.diag(out_mix)).round(6).tolist(),
            "mixture_of_outputs_diag": np.real(np.diag(mix_of_out)).round(6).tolist()}


def run():
    return {"message_to_past": message_to_past(), "grandfather": grandfather(), "bhw_discrimination": bhw()}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
