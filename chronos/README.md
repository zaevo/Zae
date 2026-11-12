# Project Chronos: executable audit of backward-in-time information transfer

Start with **[REPORT.md](REPORT.md)**: derivations, results, hypothesis register, ranked pathways, and proposed experiments.

```bash
pip install numpy scipy qiskit qiskit-aer pytest   # qiskit is only needed for E10
python run_all.py            # all experiments (~2 min) -> results/*.json + scoreboard
python run_all.py e04 e08    # a subset
python -m pytest -q tests    # regression tests for the report's claims
```

| File | What it does |
|---|---|
| `chronos/qsim.py` | Dense-matrix quantum toolkit: partial trace, random channels, Blahut–Arimoto capacity |
| `chronos/dctc.py` | Deutsch-CTC fixed-point engine (max-entropy prescription, degeneracy detection) |
| `experiments/e01_no_signaling.py` | Trilemma baseline: random future channels vs past marginals; delayed-choice eraser |
| `experiments/e02_postselection_budget.py` | Postselection Budget Theorem I(M;R\|S) ≤ log2(1/p): random, adversarial, and tight cases |
| `experiments/e03_pctc.py` | Postselected CTCs: closed form vs circuit, message to the past, grandfather paradox |
| `experiments/e04_dctc.py` | Deutsch CTCs: 1-bit message to the past, BB84 discrimination, linearity trap |
| `experiments/e05_nonlinear_qm.py` | Weinberg vs Kent nonlinearity, signalling capacity, tachyonic antitelephone |
| `experiments/e06_born_rule.py` | \|ψ\|^(2+δ) rule: κ(δ), signalling capacity C(δ), bounds from experiment |
| `experiments/e07_valentini.py` | 2D pilot-wave simulation: equilibrium vs non-equilibrium signalling |
| `experiments/e08_causal_loops.py` | Enumeration of all 3-party classical processes; Baumeler–Wolf causal-game violation |
| `experiments/e09_weak_values.py` | Weak values with a delayed postselection choice |
| `experiments/e10_hardware_circuits.py` | Qiskit circuits under a noise model; OpenQASM exported to `hardware/` |
