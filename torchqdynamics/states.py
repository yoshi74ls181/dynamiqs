from __future__ import annotations

from math import prod

import torch
from torch import Tensor

from .operators import displace
from .tensor_types import complex_tensor
from .utils import ket_to_dm

__all__ = ['fock', 'fock_dm', 'coherent', 'coherent_dm']


@complex_tensor
def fock(
    dims: int | tuple[int, ...],
    states: int | tuple[int, ...],
    *,
    dtype=None,
    device=None,
) -> Tensor:
    """State vector of a Fock state, or of a tensor product of Fock states.

    Example:
        >>> tq.fock(3, 1)
        tensor([[0.+0.j],
                [1.+0.j],
                [0.+0.j]], dtype=torch.complex128)
        >>> tq.fock((3, 2), (1, 0))
        tensor([[0.+0.j],
                [0.+0.j],
                [1.+0.j],
                [0.+0.j],
                [0.+0.j],
                [0.+0.j]], dtype=torch.complex128)
    """
    # convert integer inputs to tuples by default, and check dimensions match
    dims = (dims,) if isinstance(dims, int) else dims
    states = (states,) if isinstance(states, int) else states
    if len(dims) != len(states):
        raise ValueError(
            f'Arguments `dims` ({len(dims)}) and `states` ({len(states)}) do not have'
            ' the same number of elements.'
        )

    # compute the required basis state
    n = 0
    for dim, state in zip(dims, states):
        n = dim * n + state
    ket = torch.zeros(prod(dims), 1, dtype=dtype, device=device)
    ket[n] = 1.0
    return ket


@complex_tensor
def fock_dm(
    dims: int | tuple[int, ...],
    states: int | tuple[int, ...],
    *,
    dtype=None,
    device=None,
) -> Tensor:
    """Density matrix of a Fock state, or of a tensor product of Fock states.

    Example:
        >>> tq.fock_dm(3, 1)
        tensor([[0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 1.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 0.+0.j]], dtype=torch.complex128)
        >>> tq.fock_dm((3, 2), (1, 0))
        tensor([[0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 1.+0.j, 0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j],
                [0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j, 0.+0.j]],
                dtype=torch.complex128)
    """
    return ket_to_dm(fock(dims, states, dtype=dtype, device=device))


@complex_tensor
def coherent(dim: int, alpha: complex | Tensor, *, dtype=None, device=None) -> Tensor:
    """State vector of a coherent state.

    Example:
        >>> tq.coherent(5, 0.2)
        tensor([[0.980+0.j],
                [0.196+0.j],
                [0.028+0.j],
                [0.003+0.j],
                [0.000+0.j]], dtype=torch.complex128)
    """
    return displace(dim, alpha, dtype=dtype, device=device) @ fock(dim, 0)


@complex_tensor
def coherent_dm(
    dim: int, alpha: complex | Tensor, *, dtype=None, device=None
) -> Tensor:
    """Density matrix of a coherent state.

    Example:
        >>> tq.coherent(5, 0.2)
        tensor([[0.961+0.j, 0.192+0.j, 0.027+0.j, 0.003+0.j, 0.000+0.j],
                [0.192+0.j, 0.038+0.j, 0.005+0.j, 0.001+0.j, 0.000+0.j],
                [0.027+0.j, 0.005+0.j, 0.001+0.j, 0.000+0.j, 0.000+0.j],
                [0.003+0.j, 0.001+0.j, 0.000+0.j, 0.000+0.j, 0.000+0.j],
                [0.000+0.j, 0.000+0.j, 0.000+0.j, 0.000+0.j, 0.000+0.j]],
                dtype=torch.complex128)
    """
    return ket_to_dm(coherent(dim, alpha, dtype=dtype, device=device))
