from __future__ import annotations

from math import sqrt

import torch
from torch import Tensor

from ..solvers.ode.fixed_solver import AdjointFixedSolver
from ..solvers.solver import depends_on_H
from ..utils.solver_utils import inv_sqrtm, kraus_map
from ..utils.utils import trace
from .me_solver import MESolver


class MERouchon(MESolver, AdjointFixedSolver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.n = self.H.size(-1)
        self.I = torch.eye(self.n, device=self.H.device, dtype=self.H.dtype)  # (n, n)
        self.dt = self.options.dt

        self.M1s = sqrt(self.dt) * self.jump_ops  # (1, len(jump_ops), n, n)
        self.M1s_adj = self.M1s.adjoint()  # (1, len(jump_ops), n, n)


class MERouchon1(MERouchon):
    @depends_on_H
    def Hdag_nh(self, t: float) -> Tensor:
        # -> (b_H, 1, n, n)
        return self.H_nh(t).adjoint()

    @depends_on_H
    def M0(self, t: float, dt: float) -> Tensor:
        # build time-dependent Kraus operators
        # -> (b_H, 1, n, n)
        return self.I - 1j * dt * self.H_nh(t)

    @depends_on_H
    def M0_adj(self, t: float, dt: float) -> Tensor:
        # -> (b_H, 1, n, n)
        return self.I + 1j * dt * self.Hdag_nh(t)

    def forward(self, t: float, dt: float, rho: Tensor) -> Tensor:
        r"""Compute $\rho(t+dt)$ using a Rouchon method of order 1.

        Args:
            t: Time.
            rho: Density matrix of shape `(b_H, b_rho, n, n)`.

        Returns:
            Density matrix at next time step, as tensor of shape `(b_H, b_rho, n, n)`.
        """
        # rho: (b_H, b_rho, n, n) -> (b_H, b_rho, n, n)

        # compute rho(t+dt)
        rho = kraus_map(rho, self.M0(t, dt)) + kraus_map(rho, self.M1s)
        # rho: (b_H, b_rho, n, n)

        # normalize by the trace
        return rho / trace(rho)[..., None, None].real

    def backward_augmented(self, t: float, dt: float, rho: Tensor, phi: Tensor):
        r"""Compute $\rho(t-dt)$ and $\phi(t-dt)$ using a Rouchon method of order 1."""
        # compute rho(t-dt)
        rho = kraus_map(rho, self.M0(t, -dt)) - kraus_map(rho, self.M1s)
        rho = rho / trace(rho)[..., None, None].real

        # compute phi(t-dt)
        phi = kraus_map(phi, self.M0_adj(t, dt)) + kraus_map(phi, self.M1s_adj)

        return rho, phi


class MERouchon1_5(MERouchon):
    def forward(self, t: float, dt: float, rho: Tensor) -> Tensor:
        r"""Compute $\rho(t+dt)$ using a Rouchon method of order 1.5.

        Note:
            No need for trace renormalization since the scheme is trace-preserving
            by construction.

        Args:
            t: Time.
            rho: Density matrix of shape `(b_H, b_rho, n, n)`.

        Returns:
            Density matrix at next time step, as tensor of shape `(b_H, b_rho, n, n)`.
        """
        # rho: (b_H, b_rho, n, n) -> (b_H, b_rho, n, n)

        # non-hermitian Hamiltonian at time t
        H_nh = self.H - 0.5j * self.sum_no_jump  # (b_H, 1, n, n)

        # build time-dependent Kraus operators
        M0 = self.I - 1j * dt * H_nh  # (b_H, 1, n, n)
        Ms = sqrt(dt) * self.jump_ops  # (1, len(jump_ops), n, n)

        # build normalization matrix
        S = M0.adjoint() @ M0 + dt * self.sum_no_jump  # (b_H, 1, n, n)
        # TODO Fix `inv_sqrtm` (size not compatible and linalg.solve RuntimeError)
        S_inv_sqrtm = inv_sqrtm(S)  # (b_H, 1, n, n)

        # compute rho(t+dt)
        rho = kraus_map(rho, S_inv_sqrtm)  # (b_H, b_rho, n, n)
        rho = kraus_map(rho, M0) + kraus_map(rho, Ms)  # (b_H, b_rho, n, n)

        return rho

    def backward_augmented(self, t: float, dt: float, rho: Tensor, phi: Tensor):
        raise NotImplementedError


class MERouchon2(MERouchon):
    def forward(self, t: float, dt: float, rho: Tensor) -> Tensor:
        r"""Compute $\rho(t+dt)$ using a Rouchon method of order 2.

        Note:
            For fast time-varying Hamiltonians, this method is not order 2 because the
            second-order time derivative term is neglected. This term could be added in
            the zero-th order Kraus operator if needed, as `M0 += -0.5j * dt**2 *
            \dot{H}`.

        Args:
            t: Time.
            rho: Density matrix of shape `(b_H, b_rho, n, n)`.

        Returns:
            Density matrix at next time step, as tensor of shape `(b_H, b_rho, n, n)`.
        """
        # rho: (b_H, b_rho, n, n) -> (b_H, b_rho, n, n)

        # non-hermitian Hamiltonian at time t
        H_nh = self.H(t) - 0.5j * self.sum_no_jump  # (b_H, 1, n, n)

        # build time-dependent Kraus operators
        M0 = self.I - 1j * dt * H_nh - 0.5 * self.dt**2 * H_nh @ H_nh
        # M0: (b_H, 1, n, n)
        M1s = 0.5 * sqrt(dt) * (self.jump_ops @ M0 + M0 @ self.jump_ops)
        # M1s: (b_H, len(jump_ops), n, n)

        # compute rho(t+dt)
        tmp = kraus_map(rho, M1s)  # (b_H, b_rho, n, n)
        rho = kraus_map(rho, M0) + tmp + 0.5 * kraus_map(tmp, M1s)  # (b_H, b_rho, n, n)

        # normalize by the trace
        rho = rho / trace(rho)[..., None, None].real  # (b_H, b_rho, n, n)

        return rho

    def backward_augmented(self, t: float, dt: float, rho: Tensor, phi: Tensor):
        r"""Compute $\rho(t-dt)$ and $\phi(t-dt)$ using a Rouchon method of order 2."""
        # non-hermitian Hamiltonian at time t
        H_nh = self.H(t) - 0.5j * self.sum_no_jump
        Hdag_nh = H_nh.adjoint()

        # compute rho(t-dt)
        M0 = self.I + 1j * dt * H_nh - 0.5 * dt**2 * H_nh @ H_nh
        M1s = 0.5 * sqrt(dt) * (self.jump_ops @ M0 + M0 @ self.jump_ops)
        tmp = kraus_map(rho, M1s)
        rho = kraus_map(rho, M0) - tmp + 0.5 * kraus_map(tmp, M1s)
        rho = rho / trace(rho)[..., None, None].real

        # compute phi(t-dt)
        M0_adj = self.I + 1j * dt * Hdag_nh - 0.5 * dt**2 * Hdag_nh @ Hdag_nh
        M1s_adj = (
            0.5
            * sqrt(dt)
            * (self.jump_ops.adjoint() @ M0_adj + M0_adj @ self.jump_ops.adjoint())
        )
        tmp = kraus_map(phi, M1s_adj)
        phi = kraus_map(phi, M0_adj) + tmp + 0.5 * kraus_map(tmp, M1s_adj)

        return rho, phi