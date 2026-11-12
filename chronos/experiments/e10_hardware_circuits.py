"""E10 — Hardware-ready circuits (Qiskit), executed here on Aer with a realistic
noise model, and exported as OpenQASM 2 for IBM / any gate-model QPU.

Circuit A  'pctc_message': P-CTC message to the past. The past register R is
           measured mid-circuit BEFORE the message bit m is even written.
Circuit B  'delayed_choice': Bell pair; signal measured first; a quantum coin
           (measured last) later decides the idler's basis. Tests whether the
           earlier record carries ANY information about the later coin, and
           gives a statistical upper bound on a retrocausal bias."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from qiskit import QuantumCircuit, transpile, qasm2
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
from chronos.qsim import mutual_info, blahut_arimoto

OUT = os.path.join(os.path.dirname(__file__), '..', 'hardware')


def noise_model(p1=1e-3, p2=1e-2, ro=0.02):
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1), ['h', 'x', 'sx', 'rz'])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ['cx', 'ecr'])
    nm.add_all_qubit_readout_error(ReadoutError([[1 - ro, ro], [ro, 1 - ro]]))
    return nm


def pctc_message(m):
    # qubits: 0=A (CTC out), 1=B (CTC partner), 2=R (past register), 3=Q (message)
    qc = QuantumCircuit(4, 3, name=f"pctc_message_m{m}")
    qc.h(0); qc.cx(0, 1)          # CTC = Bell pair
    qc.cx(0, 2)                   # t1: past lab copies the CTC qubit
    qc.measure(2, 0)              # past record fixed NOW
    qc.barrier()
    if m: qc.x(3)                 # t2: future agent writes the message
    qc.cx(3, 1); qc.h(3)          # Bell measurement on (Q, B)
    qc.measure(3, 1); qc.measure(1, 2)
    return qc


def delayed_choice():
    # 0=S signal, 1=I idler, 2=coin
    qc = QuantumCircuit(3, 3, name="delayed_choice")
    qc.h(0); qc.cx(0, 1)
    qc.h(0); qc.measure(0, 0)     # signal measured in X first
    qc.barrier()
    qc.h(2)                       # quantum coin
    qc.ch(2, 1)                   # coin decides idler basis (Z or X) -- after S is recorded
    qc.measure(1, 1); qc.measure(2, 2)
    return qc


def counts_to_array(counts, nbits):
    arr = np.zeros([2] * nbits)
    for k, v in counts.items():
        bits = [int(b) for b in k.replace(' ', '')[::-1]]  # clbit 0 first
        arr[tuple(bits)] += v
    return arr


def run(shots=40000, seed=11):
    os.makedirs(OUT, exist_ok=True)
    sim = AerSimulator(noise_model=noise_model(), seed_simulator=seed)
    res = {}
    # ---- A
    rows = {}
    W_unc, W_cond = [], []
    for m in (0, 1):
        qc = pctc_message(m)
        with open(os.path.join(OUT, f"{qc.name}.qasm"), "w") as f:
            f.write(qasm2.dumps(qc))
        c = counts_to_array(sim.run(transpile(qc, sim), shots=shots, seed_simulator=seed + 17 * (m + 1)).result().get_counts(), 3)  # [R, q3, q1]
        pR = c.sum((1, 2)) / c.sum()
        her = c[:, 0, 0]
        rows[f"m={m}"] = {"P(R=1) unconditional": float(pR[1]), "P(R=1 | herald)": float(her[1] / her.sum()),
                          "P(herald)": float(her.sum() / c.sum())}
        W_unc.append(c.sum((1, 2))); W_cond.append(her)
    rows["I(m;R) unconditional (bits, plug-in)"] = mutual_info(np.array(W_unc))
    rows["I(m;R | herald) (bits)"] = mutual_info(np.array(W_cond))
    res["A_pctc_message_noisy"] = rows
    # ---- B
    qc = delayed_choice()
    with open(os.path.join(OUT, "delayed_choice.qasm"), "w") as f:
        f.write(qasm2.dumps(qc))
    N = shots * 5
    c = counts_to_array(sim.run(transpile(qc, sim), shots=N).result().get_counts(), 3)  # [s, i, coin]
    p_s0_c = [c[0, :, k].sum() / c[:, :, k].sum() for k in (0, 1)]
    n_c = [c[:, :, k].sum() for k in (0, 1)]
    diff = p_s0_c[0] - p_s0_c[1]
    se = np.sqrt(sum(p * (1 - p) / n for p, n in zip(p_s0_c, n_c)))
    sc = {}
    for k, name in ((0, "coin=0 (Z, which-path)"), (1, "coin=1 (X, eraser)")):
        sub = c[:, :, k]
        sc[name] = {"I(S;I) bits": mutual_info(sub)}
    res["B_delayed_choice_noisy"] = {
        "shots": int(N), "P(s=0|coin=0)": float(p_s0_c[0]), "P(s=0|coin=1)": float(p_s0_c[1]),
        "retro bias estimate": float(diff), "95% upper bound on |retro bias|": float(abs(diff) + 1.96 * se),
        "implied capacity upper bound (bits/trial)": blahut_arimoto([[0.5 + (abs(diff) + 1.96 * se) / 2, 0.5 - (abs(diff) + 1.96 * se) / 2], [0.5, 0.5]]),
        "conditional correlations": sc}
    res["qasm_files"] = sorted(os.listdir(OUT))
    return res


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
