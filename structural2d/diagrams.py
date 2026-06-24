"""Internal force (N/V/M) and deflected-shape sampling along individual members.

Sign convention: x runs from node_i (x=0) to node_j (x=L) along the local
axis. N(x), V(x), M(x) are the internal stress resultants obtained by
cutting the member at x and taking equilibrium of the [0, x] free body
(end force at node_i + any applied loads within [0, x)). Positive N is
tension, positive V/M follow the standard beam convention consistent
with the stiffness formulation in solver.py (verified against textbook
simply-supported-beam and cantilever cases in tests/test_solver.py).

Deflected shape is recovered by direct double integration of the (already
validated) moment diagram -- EI*v'' = M(x), starting from the exact node-i
end rotation/displacement -- rather than a single cubic Hermite
interpolation of the nodal DOFs. A single cubic per member is only exact
when there is no load between the two ends; integrating the real M(x)
instead handles interior point loads and UDLs correctly too.
"""
from __future__ import annotations

import numpy as np

from .model import FrameModel
from .solver import FrameResults

_EPS_REL = 1e-9


def _local_point_loads(model: FrameModel, member_id: str, angle: float):
    pts = []
    for p in model.member_point_loads(member_id):
        if p.frame == "global":
            c, s = np.cos(angle), np.sin(angle)
            fx, fy = c * p.fx + s * p.fy, -s * p.fx + c * p.fy
        else:
            fx, fy = p.fx, p.fy
        pts.append((p.position, fx, fy, p.m))
    return pts


def _local_udls(model: FrameModel, member_id: str, angle: float, L: float):
    out = []
    for u in model.member_udls(member_id):
        lo = 0.0 if u.start is None else u.start
        hi = L if u.end is None else u.end
        if u.frame == "global":
            c, s = np.cos(angle), np.sin(angle)
            wx, wy = c * u.wx + s * u.wy, -s * u.wx + c * u.wy
        else:
            wx, wy = u.wx, u.wy
        out.append((lo, hi, wx, wy))
    return out


def _cumtrapz(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    dx = np.diff(x)
    avg = (y[:-1] + y[1:]) / 2.0
    return np.concatenate([[0.0], np.cumsum(avg * dx)])


def sample_member(model: FrameModel, results: FrameResults, member_id: str, n: int = 100) -> dict:
    """Sample N, V, M, and local deflection at `n`+ points along a member."""
    member = model.members[member_id]
    state = results.members[member_id]
    L = state.length
    angle = state.angle
    Q = state.end_forces

    points = _local_point_loads(model, member_id, angle)
    udls = _local_udls(model, member_id, angle, L)

    eps = max(L * _EPS_REL, 1e-12)
    breakpoints = {0.0, L}
    for pos, *_ in points:
        breakpoints.add(pos)
        if 0.0 < pos < L:
            breakpoints.add(pos - eps)
            breakpoints.add(pos + eps)
    for lo, hi, *_ in udls:
        breakpoints.update({lo, hi})

    grid = sorted(breakpoints | set(np.linspace(0.0, L, n).tolist()))
    xs = np.array(grid)

    N = np.full_like(xs, Q[0])
    V = np.full_like(xs, Q[1])
    M = -Q[2] + Q[1] * xs

    for pos, fx, fy, m in points:
        after = xs > pos + eps / 2
        N[after] += fx
        V[after] += fy
        M[after] += fy * (xs[after] - pos) - m

    for lo, hi, wx, wy in udls:
        b = np.clip(xs, lo, hi)
        overlap = b - lo
        N += wx * overlap
        V += wy * overlap
        M += wy * (xs * (b - lo) - (b**2 - lo**2) / 2.0)

    theta1, _theta2 = state.end_rotations
    v1 = state.d_local[1]
    slope = theta1 + _cumtrapz(M / (member.E * member.I), xs)
    deflection = v1 + _cumtrapz(slope, xs)

    u1 = state.d_local[0]
    axial_deflection = u1 + _cumtrapz(N / (member.E * member.A), xs)

    return dict(x=xs, N=N, V=V, M=M, deflection=deflection, axial_deflection=axial_deflection)


def global_deformed_coords(
    model: FrameModel, results: FrameResults, member_id: str, scale: float = 1.0, n: int = 30
) -> tuple[np.ndarray, np.ndarray]:
    """Global XY coordinates of the deformed member centerline (for plotting)."""
    member = model.members[member_id]
    ni = model.nodes[member.node_i]
    state = results.members[member_id]
    sample = sample_member(model, results, member_id, n=n)
    c, s = np.cos(state.angle), np.sin(state.angle)

    x_local = sample["x"] + scale * sample["axial_deflection"]
    y_local = scale * sample["deflection"]

    x_global = ni.x + c * x_local - s * y_local
    y_global = ni.y + s * x_local + c * y_local
    return x_global, y_global
