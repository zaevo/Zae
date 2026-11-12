"""Deutsch CTC (D-CTC) fixed-point engine."""
import numpy as np
from .qsim import ptrace


def ctc_map(rho_cr, U, dcr, dc):
    """Superoperator L: tau -> Tr_CR[U (rho_cr ⊗ tau) U^dag] as a (dc^2 x dc^2) matrix."""
    L = np.zeros((dc * dc, dc * dc), dtype=complex)
    for a in range(dc):
        for b in range(dc):
            E = np.zeros((dc, dc), dtype=complex); E[a, b] = 1
            out = U @ np.kron(rho_cr, E) @ U.conj().T
            L[:, a * dc + b] = ptrace(out, [1], [dcr, dc]).reshape(-1)
    return L


def fixed_points(rho_cr, U, dcr, dc, tol=1e-9):
    L = ctc_map(rho_cr, U, dcr, dc)
    w, V = np.linalg.eig(L)
    idx = np.where(np.abs(w - 1) < tol)[0]
    return L, len(idx)


def deutsch_fixed_point(rho_cr, U, dcr, dc, N=4000):
    """Deutsch's maximum-entropy prescription, implemented as the projection of the
    maximally mixed state onto the fixed space (Cesaro mean of L^k (I/d))."""
    L = ctc_map(rho_cr, U, dcr, dc)
    # Cesaro limit via spectral projector onto eigenvalue 1
    w, V = np.linalg.eig(L)
    Vi = np.linalg.inv(V)
    mask = np.abs(w - 1) < 1e-9
    P = (V[:, mask] @ Vi[mask, :])
    tau = (P @ (np.eye(dc).reshape(-1) / dc)).reshape(dc, dc)
    tau = (tau + tau.conj().T) / 2
    return tau / np.real(np.trace(tau)), int(mask.sum())


def dctc_output(rho_cr, U, dcr, dc):
    tau, ndeg = deutsch_fixed_point(rho_cr, U, dcr, dc)
    out = U @ np.kron(rho_cr, tau) @ U.conj().T
    return ptrace(out, [0], [dcr, dc]), tau, ndeg
