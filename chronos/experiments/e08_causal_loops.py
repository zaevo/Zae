"""E8 — Logically consistent causal loops with freedom of choice
(Baumeler & Wolf 2016; Baumeler, Costa, Ralph, Wolf, Zych 2019; Tobar & Costa 2020).

A deterministic 3-party classical 'process' omega maps the parties' output bits
(a0,a1,a2) to their input bits (x0,x1,x2). Each party applies ANY local operation
a_k = f_k(x_k). The process is *logically consistent* if for every choice of
local operations the loop x = omega(f(x)) has exactly one solution — i.e. no
grandfather paradox and no bootstrap ambiguity, whatever the agents freely do.

We enumerate all 4096 processes in which x_k depends only on the other parties'
outputs, keep the consistent ones, and test each for causal order (recursive
definition: some party's input is constant, and for every value of its output
the remaining process is again causal — this includes dynamical orders).

Non-causal consistent processes are the cleanest known mathematical objects
in which every party both influences and is influenced by every other — a
message 'loop' with no paradox and with linear (probabilistic) dynamics.
We then play a causal game: each party gets a uniform bit y_k and must output
g_k = NOT(y_{k+1}) AND y_{k+2}; all three must win. In any causal process the
first party has a constant input, so its guess depends only on y_k, while its
target is independent of y_k and equals 1 w.p. 1/4  ->  P(win) <= 3/4.
(Convex mixtures cannot exceed this.)"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np

BITS = list(itertools.product((0, 1), repeat=3))
LOCAL = [lambda x: 0, lambda x: 1, lambda x: x, lambda x: 1 - x]


def make_process(codes):
    """codes[k] in 0..15 is the truth table of x_k as a function of the other two outputs."""
    others = [(1, 2), (0, 2), (0, 1)]
    def omega(a):
        return tuple((codes[k] >> (2 * a[others[k][0]] + a[others[k][1]])) & 1 for k in range(3))
    return omega


def consistent(omega):
    for fs in itertools.product(LOCAL, repeat=3):
        sols = sum(1 for xv in BITS if omega(tuple(fs[k](xv[k]) for k in range(3))) == xv)
        if sols != 1:
            return False
    return True


def is_causal(omega, parties=(0, 1, 2), fixed=None):
    fixed = dict(fixed or {})
    free = [p for p in parties if p not in fixed]
    if not free:
        return True
    def inp(k, assign):
        a = [assign.get(i, 0) for i in range(3)]
        return omega(tuple(a))[k]
    for k in free:
        rest = [p for p in free if p != k]
        # x_k constant over all outputs of the remaining free parties (given fixed ones)?
        vals = set()
        for combo in itertools.product((0, 1), repeat=len(free)):
            assign = dict(fixed); assign.update(dict(zip(free, combo)))
            vals.add(inp(k, assign))
        if len(vals) == 1:
            if all(is_causal(omega, parties, {**fixed, k: ak}) for ak in (0, 1)):
                return True
    return False


def signalling_graph(omega):
    g = set()
    for s in range(3):
        for r in range(3):
            if s != r:
                for a in BITS:
                    b = list(a); b[s] ^= 1
                    if omega(a)[r] != omega(tuple(b))[r]:
                        g.add((s, r)); break
    return sorted(g)


def game_value(omega):
    """Max over all local strategies: a_k = A_k(x_k, y_k), g_k = G_k(x_k, y_k)."""
    funcs2 = list(range(16))  # truth tables over (x,y)
    ev = lambda t, x, y: (t >> (2 * x + y)) & 1
    ys = BITS
    best = 0.0
    for A in itertools.product(funcs2, repeat=3):
        xs = []
        for y in ys:
            sol = [xv for xv in BITS if omega(tuple(ev(A[k], xv[k], y[k]) for k in range(3))) == xv]
            xs.append(sol[0])
        # correctness tables C_k[g, yi]
        C = np.zeros((3, 16, 8), dtype=bool)
        for k in range(3):
            for gt in funcs2:
                for i, y in enumerate(ys):
                    C[k, gt, i] = ev(gt, xs[i][k], y[k]) == int((1 - y[(k + 1) % 3]) and y[(k + 2) % 3])
        joint = (C[0][:, None, None, :] & C[1][None, :, None, :] & C[2][None, None, :, :]).sum(-1)
        best = max(best, joint.max() / 8)
        if best == 1.0:
            break
    return best


def run():
    cons, noncausal = [], []
    for codes in itertools.product(range(16), repeat=3):
        om = make_process(codes)
        if consistent(om):
            cons.append(codes)
            if not is_causal(om):
                noncausal.append(codes)
    # Baumeler–Wolf process: x_k = NOT(a_{k+1}) AND a_{k+2}  (indices mod 3) -- check it's found
    bw = lambda a: tuple(int((1 - a[(k + 1) % 3]) and a[(k + 2) % 3]) for k in range(3))
    res = {"processes_enumerated": 4096, "logically_consistent": len(cons),
           "consistent_and_NON_causal": len(noncausal),
           "BW_process_consistent": consistent(bw), "BW_process_causal": is_causal(bw),
           "BW_signalling_graph": signalling_graph(bw)}
    res["game_value_BW"] = game_value(bw)
    rng = np.random.default_rng(8)
    causal = [c for c in cons if c not in noncausal]
    sample = [causal[i] for i in rng.choice(len(causal), size=min(12, len(causal)), replace=False)]
    res["game_value_max_over_sampled_causal"] = max(game_value(make_process(c)) for c in sample)
    res["game_value_max_over_noncausal"] = max(game_value(make_process(c)) for c in noncausal) if noncausal else None
    return res


if __name__ == "__main__":
    import json; print(json.dumps(run(), indent=2))
