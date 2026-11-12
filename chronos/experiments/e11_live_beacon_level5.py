"""E11: a LIVE Level-5 attempt against genuinely future-generated data.

For each of K pre-registered trials:
  t0  RECEIVER: runs the strongest candidate mechanism found in E1–E10 that is
      realisable without new physics, the P-CTC channel (one per message bit),
      in Cirq with a Willow-class noise model. Measures the past register R,
      decodes a 17-bit guess, and COMMITS it (hash + guess + latest pulse seen)
      for a beacon pulse that is 2 minutes in the future.
  t1  The NIST beacon publishes the target pulse -> message CHRONOS-YYYY-NNNNN.
  t2  SENDER: writes the message bits into the CTC (Bell measurement against the
      stored partner qubits, which a simulator can hold for minutes and a real
      QPU cannot) -> heralds.
  t3  VERIFIER: checks commitments and scores
        (a) unconditional matches (the Level-5 criterion);
        (b) herald-conditional matches (uses post-commit information, so
            reported but disqualified).
Noise: 1q 0.035%, 2q 0.33%, readout 0.77% (approximate published Willow-class figures).
To run on Google hardware: see run_on_engine() (requires Quantum Engine access)."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import cirq
from chronos import protocol as P

P1, P2, PRO = 3.5e-4, 3.3e-3, 7.7e-3
LEDGER = os.path.join(os.path.dirname(__file__), '..', 'ledger')
NB = 17


class WillowLikeNoise(cirq.NoiseModel):
    def noisy_operation(self, op):
        if cirq.is_measurement(op):
            return [cirq.bit_flip(PRO).on_each(*op.qubits), op]
        if len(op.qubits) == 1:
            return [op, cirq.depolarize(P1).on(*op.qubits)]
        return [op, cirq.depolarize(P2, n_qubits=2).on(*op.qubits)]


A, B, R, Q = cirq.LineQubit.range(4)
SIM = cirq.DensityMatrixSimulator(noise=WillowLikeNoise(), seed=None)


def receiver_bit():
    c = cirq.Circuit(cirq.H(A), cirq.CNOT(A, B), cirq.CNOT(A, R), cirq.measure(R, key='r'))
    res = SIM.simulate(c, qubit_order=[A, B, R, Q])
    return int(res.measurements['r'][0]), res.final_density_matrix  # stored quantum memory


def sender_bit(rho, m):
    ops = ([cirq.X(Q)] if m else []) + [cirq.CNOT(Q, B), cirq.H(Q), cirq.measure(Q, B, key='bell')]
    res = SIM.simulate(cirq.Circuit(ops), qubit_order=[A, B, R, Q], initial_state=rho)
    q, b = res.measurements['bell']
    return int(q == 0 and b == 0)  # herald = Phi+


def run(K=10, lead=2, out_name=None):
    os.makedirs(LEDGER, exist_ok=True)
    trials = []
    seen = P.last_pulse()
    plan = {"protocol": "CVP v1", "K": K, "lead_pulses": lead, "registered_at_pulse": seen["pulseIndex"],
            "mechanism": "P-CTC per bit, Cirq Willow-like noise"}
    plan_hash = P.commit(plan)
    for k in range(K):
        seen = P.last_pulse()
        target = seen["pulseIndex"] + lead
        bits, mems = [], []
        for _ in range(NB):
            r, rho = receiver_bit(); bits.append(r); mems.append(rho)
        guess = P.from_bits(bits)
        rec = {"trial": k, "target_pulse": target, "latest_pulse_seen": seen["pulseIndex"],
               "latest_pulse_value_prefix": seen["outputValue"][:32], "guess_bits": bits,
               "guess_message_digits": f"{guess:05d}", "committed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec["sha256"] = P.commit(rec)
        trials.append({"commit": rec, "mems": mems})
        print(f"[commit] trial {k} guess {guess:05d} for pulse {target}", flush=True)
        time.sleep(61)
    # wait until final target exists
    while P.last_pulse()["pulseIndex"] < trials[-1]["commit"]["target_pulse"]:
        time.sleep(10)
    results = []
    for t in trials:
        c = t["commit"]
        assert P.commit({k: v for k, v in c.items() if k != "sha256"}) == c["sha256"]
        p = P.pulse(c["target_pulse"])
        msg, n = P.message_from_pulse(p)
        assert p["pulseIndex"] > c["latest_pulse_seen"]
        mbits = P.to_bits(n, NB)
        heralds = [sender_bit(rho, m) for rho, m in zip(t["mems"], mbits)]
        unc = sum(int(g == m) for g, m in zip(c["guess_bits"], mbits))
        hb = [(g, m) for g, m, h in zip(c["guess_bits"], mbits, heralds) if h]
        results.append({**{k: c[k] for k in ("trial", "target_pulse", "latest_pulse_seen", "guess_message_digits", "sha256", "committed_utc")},
                        "true_message": msg, "pulse_timestamp": p["timeStamp"],
                        "exact_message_match": c["guess_message_digits"] == f"{n:05d}",
                        "unconditional_bit_matches": unc, "bits": NB,
                        "heralded_bits": len(hb), "heralded_bit_matches": sum(int(g == m) for g, m in hb)})
    U = sum(r["unconditional_bit_matches"] for r in results); N = NB * len(results)
    HB = sum(r["heralded_bits"] for r in results); HM = sum(r["heralded_bit_matches"] for r in results)
    summary = {"plan": plan, "plan_sha256": plan_hash, "trials": results,
               "exact_message_matches": sum(r["exact_message_match"] for r in results),
               "expected_exact_matches_by_chance": len(results) * 1e-5,
               "LEVEL5_unconditional_bit_accuracy": U / N, "LEVEL5_p_value (X>=U)": P.binom_sf(U, N),
               "DISQUALIFIED_herald_conditional_accuracy": HM / HB if HB else None,
               "herald_rate": HB / N, "postselection_budget_bits_per_bit": float(np.log2(N / HB)) if HB else None}
    out = os.path.join(LEDGER, out_name or f"e11_live_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "trials"}, indent=2))
    return summary


def run_on_engine(project_id, processor_id, shots=100000):
    """Real-hardware variant (coherence is ~100 us, so the 'future' message comes from an
    in-circuit quantum coin measured AFTER R, not from the beacon)."""
    import cirq_google
    C = cirq.LineQubit(4)
    c = cirq.Circuit(cirq.H(A), cirq.CNOT(A, B), cirq.CNOT(A, R), cirq.measure(R, key='r'),
                     cirq.H(C), cirq.CNOT(C, Q), cirq.CNOT(Q, B), cirq.H(Q),
                     cirq.measure(Q, B, key='bell'), cirq.measure(C, key='m'))
    sampler = cirq_google.get_engine(project_id).get_sampler(processor_id)
    return sampler.run(c, repetitions=shots)  # map LineQubits to device qubits before use


if __name__ == "__main__":
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run(K)
