"""Minimal dense-matrix quantum toolkit (numpy only). Little-endian is NOT used:
subsystem 0 is the leftmost tensor factor."""
import numpy as np

I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)


def ket(bits, d=2):
    """|b0 b1 ...> for a string/list of digits."""
    v = np.array([1.0 + 0j])
    for b in bits:
        e = np.zeros(d, dtype=complex)
        e[int(b)] = 1
        v = np.kron(v, e)
    return v


def dm(psi):
    psi = np.asarray(psi, dtype=complex)
    return np.outer(psi, psi.conj())


def kron(*ops):
    out = np.array([[1.0 + 0j]])
    for o in ops:
        out = np.kron(out, o)
    return out


def op_on(op, targets, dims):
    """Embed `op` (acting on subsystems `targets`, in that order) into the full space."""
    n = len(dims)
    targets = list(targets)
    rest = [i for i in range(n) if i not in targets]
    order = targets + rest
    dt = int(np.prod([dims[i] for i in targets]))
    dr = int(np.prod([dims[i] for i in rest])) if rest else 1
    full = np.kron(op, np.eye(dr))
    # full acts on ordering `order`; permute back to natural ordering
    perm_dims = [dims[i] for i in order]
    full = full.reshape(perm_dims * 2)
    inv = np.argsort(order)
    full = full.transpose(list(inv) + [n + i for i in inv])
    D = int(np.prod(dims))
    return full.reshape(D, D)


def ptrace(rho, keep, dims):
    """Partial trace keeping subsystems `keep` (output in ascending order)."""
    n = len(dims)
    keep = sorted(keep)
    t = rho.reshape(list(dims) * 2)
    trace_out = [i for i in range(n) if i not in keep]
    # contract traced indices pairwise
    letters = 'abcdefghijklmnopqrstuvwxyz'
    lin = list(letters[:n])
    lout = list(letters[n:2 * n])
    for i in trace_out:
        lout[i] = lin[i]
    res = ''.join(lin[i] for i in keep) + ''.join(lout[i] for i in keep)
    t = np.einsum(''.join(lin) + ''.join(lout) + '->' + res, t)
    dk = int(np.prod([dims[i] for i in keep])) if keep else 1
    return t.reshape(dk, dk)


def random_unitary(d, rng):
    z = (rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d))) / np.sqrt(2)
    q, r = np.linalg.qr(z)
    ph = np.diag(r) / np.abs(np.diag(r))
    return q * ph


def random_state(d, rng):
    v = rng.normal(size=d) + 1j * rng.normal(size=d)
    return v / np.linalg.norm(v)


def random_kraus(d, k, rng):
    """Random CPTP channel on dimension d with k Kraus ops (Stinespring)."""
    U = random_unitary(d * k, rng)
    V = U[:, :d]  # isometry d -> d*k
    return [V[i * d:(i + 1) * d, :] for i in range(k)]


def apply_kraus(rho, kraus, targets, dims):
    out = np.zeros_like(rho)
    for K in kraus:
        Kf = op_on(K, targets, dims)
        out += Kf @ rho @ Kf.conj().T
    return out


def trace_distance(a, b):
    ev = np.linalg.eigvalsh((a - b + (a - b).conj().T) / 2)
    return 0.5 * np.sum(np.abs(ev))


def entropy(p):
    p = np.asarray(p, dtype=float).ravel()
    p = p[p > 1e-15]
    return float(-np.sum(p * np.log2(p)))


def vn_entropy(rho):
    return entropy(np.linalg.eigvalsh((rho + rho.conj().T) / 2))


def mutual_info(pxy):
    pxy = np.asarray(pxy, dtype=float)
    pxy = pxy / pxy.sum()
    return entropy(pxy.sum(1)) + entropy(pxy.sum(0)) - entropy(pxy)


def fidelity_pure(psi, rho):
    return float(np.real(psi.conj() @ rho @ psi))


def bell(i=0):
    """Bell states: 0=Phi+,1=Phi-,2=Psi+,3=Psi-"""
    s = 1 / np.sqrt(2)
    return [np.array([s, 0, 0, s]), np.array([s, 0, 0, -s]),
            np.array([0, s, s, 0]), np.array([0, s, -s, 0])][i].astype(complex)


def swap_op(d=2):
    S = np.zeros((d * d, d * d), dtype=complex)
    for i in range(d):
        for j in range(d):
            S[j * d + i, i * d + j] = 1
    return S


def cnot():
    return np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex)


def blahut_arimoto(W, iters=2000, tol=1e-12):
    """Classical capacity (bits) of a DMC with rows W[x] = p(y|x)."""
    W = np.asarray(W, dtype=float)
    nx = W.shape[0]
    p = np.ones(nx) / nx
    for _ in range(iters):
        q = p @ W
        with np.errstate(divide='ignore', invalid='ignore'):
            D = np.where(W > 0, W * np.log(W / q), 0).sum(1)
        newp = p * np.exp(D)
        newp /= newp.sum()
        if np.max(np.abs(newp - p)) < tol:
            p = newp
            break
        p = newp
    q = p @ W
    with np.errstate(divide='ignore', invalid='ignore'):
        D = np.where(W > 0, W * np.log2(W / q), 0).sum(1)
    return float(p @ D)
