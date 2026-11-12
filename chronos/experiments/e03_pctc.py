"""E3 — Postselected CTCs (Lloyd et al. 2011; Svetlichny; Bennett-Schumacher).

A P-CTC is a Bell pair (A,B): A 'emerges' at t1 into the past lab, B is
Bell-measured at t2 together with the system Q that 'enters' the CTC, and the
run is kept only if the outcome is Phi+. Conditioned on success, A *was* Q.

We (1) verify the closed-form P-CTC map rho -> T rho T^dag / tr, T = Tr_C U,
against full circuit simulation; (2) send a message to the past and report both
the conditional and the unconditional channels; (3) simulate the grandfather
paradox with an imperfect gun and show the 'paradox suppression / misfire
amplification' effect; (4) check the Postselection Budget Theorem."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from chronos.qsim import (ket, dm, kron, op_on, ptrace, bell, cnot, random_unitary,
                          random_state, trace_distance, mutual_info, blahut_arimoto, I2, X)

PHI = bell(0)


def pctc_circuit(rho_S, U):
    """Full simulation. Systems: [S, A, B, Q]. A,B start in Phi+.
    U acts on (S, A) at t1 (A is the CTC qubit as it emerges).
    The CTC qubit after interaction is A; it 'enters' the CTC at t2: Bell-project (A,B)."""
    dims = [2, 2, 2]  # S, A, B
    rho = kron(rho_S, dm(PHI))
    Uf = op_on(U, [0, 1], dims)
    rho = Uf @ rho @ Uf.conj().T
    P = op_on(dm(PHI), [1, 2], dims)
    post = P @ rho @ P
    p = np.real(np.trace(post))
    return ptrace(post, [0], dims) / p, p


def pctc_formula(rho_S, U):
    T = np.einsum('iaja->ij', U.reshape(2, 2, 2, 2))  # Tr over CTC (2nd factor)
    out = T @ rho_S @ T.conj().T
    return out / np.real(np.trace(out))


def verify_formula(n=200, seed=4):
    rng = np.random.default_rng(seed)
    worst = 0
    for _ in range(n):
        rho = dm(random_state(2, rng)); U = random_unitary(4, rng)
        a, _ = pctc_circuit(rho, U); b = pctc_formula(rho, U)
        worst = max(worst, trace_distance(a, b))
    return worst


def message_to_past():
    """Systems [R, A, B, Q]. A,B = Phi+.  t1: past lab copies A into R (CNOT A->R).
    t2: future agent prepares Q=|m> and Bell-measures (Q,B); keep Phi+."""
    dims = [2, 2, 2, 2]
    res = {}
    W_uncond, W_cond = [], []
    for m in (0, 1):
        psi = np.kron(np.kron(ket('0'), PHI), ket(str(m)))
        rho = dm(psi)
        C = op_on(cnot(), [1, 0], dims)  # control A, target R
        rho = C @ rho @ C.conj().T
        R_uncond = np.real(np.diag(ptrace(rho, [0], dims)))
        P = op_on(dm(PHI), [3, 2], dims)
        post = P @ rho @ P
        p = np.real(np.trace(post))
        R_cond = np.real(np.diag(ptrace(post, [0], dims))) / p
        res[f"m={m}"] = {"P(R) unconditional": R_uncond.round(12).tolist(),
                         "P(R | herald)": R_cond.round(12).tolist(), "P(herald)": p}
        W_uncond.append(R_uncond); W_cond.append(R_cond)
    res["capacity_unconditional_bits"] = blahut_arimoto(W_uncond)
    res["capacity_conditional_bits"] = blahut_arimoto(W_cond)
    res["budget_log2_1/p"] = float(np.log2(1 / res["m=0"]["P(herald)"]))
    return res


def grandfather(eps_list=(0.5, 0.2, 0.1, 0.03, 0.01, 0.001)):
    """Gun G in cos(e)|fire> + sin(e)|misfire>. CTC bit = 'grandfather alive'.
    If gun fires, it flips the CTC bit (kills grandfather -> paradox)."""
    out = []
    U = kron(dm(ket('0')), X) + kron(dm(ket('1')), I2)
    for e in eps_list:
        g = np.cos(e) * ket('0') + np.sin(e) * ket('1')
        rhoG, p = pctc_circuit(dm(g), U)
        out.append({"misfire_amplitude^2 (prior)": float(np.sin(e) ** 2),
                    "P(herald)": float(p),
                    "P(misfire | consistent history)": float(np.real(rhoG[1, 1]))})
    return out


def run():
    return {"formula_vs_circuit_max_trace_distance": verify_formula(),
            "message_to_past": message_to_past(),
            "grandfather_paradox": grandfather()}


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
