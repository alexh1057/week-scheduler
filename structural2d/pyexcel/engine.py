"""Self-contained 2D frame analysis engine for Excel's "Insert Python" / PY()
feature (Microsoft's cloud-sandboxed Python in Excel -- a different thing
from xlwings/COM automation).

That sandbox cannot import local packages or read files, only the
preinstalled set (numpy/pandas/matplotlib/etc.) -- so this single file
deliberately re-implements model.py + solver.py + diagrams.py + plotting.py
flattened, with no relative imports, so its source can be pasted verbatim
into one Insert Python cell. See the Instructions sheet in
frame_model_pyexcel.xlsx (built by structural2d/excel/build_pyexcel_template.py)
or the README for exactly which cell gets this file and which cells get the
few one-line formulas that read from it.

Everything below `run()` is plain, dependency-light Python, so it's
importable and tested headlessly in tests/test_pyexcel_engine.py using
pandas DataFrames standing in for Excel Tables. The only thing that can't
be exercised outside Excel itself is the real `xl(...)` calls and whether
a matplotlib Figure returned by one PY() cell still renders correctly when
referenced from another cell -- both noted as unverified in the README.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Circle, Polygon

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    x: float
    y: float


@dataclass
class Support:
    node_id: str
    ux: bool = False
    uy: bool = False
    rz: bool = False

    @classmethod
    def fixed(cls, node_id: str) -> "Support":
        return cls(node_id, True, True, True)

    @classmethod
    def pinned(cls, node_id: str) -> "Support":
        return cls(node_id, True, True, False)

    @classmethod
    def roller(cls, node_id: str, direction: str = "y") -> "Support":
        return cls(node_id, direction == "x", direction == "y", False)


@dataclass
class Member:
    id: str
    node_i: str
    node_j: str
    E: float
    A: float
    I: float
    hinge_i: bool = False
    hinge_j: bool = False


@dataclass
class NodalLoad:
    node_id: str
    fx: float = 0.0
    fy: float = 0.0
    m: float = 0.0


@dataclass
class MemberPointLoad:
    member_id: str
    position: float
    fx: float = 0.0
    fy: float = 0.0
    m: float = 0.0
    frame: str = "local"


@dataclass
class MemberUDL:
    member_id: str
    wx: float = 0.0
    wy: float = 0.0
    frame: str = "local"
    start: float | None = None
    end: float | None = None


@dataclass
class FrameModel:
    nodes: dict[str, Node] = field(default_factory=dict)
    members: dict[str, Member] = field(default_factory=dict)
    supports: dict[str, Support] = field(default_factory=dict)
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    point_loads: list[MemberPointLoad] = field(default_factory=list)
    udls: list[MemberUDL] = field(default_factory=list)

    def add_node(self, id: str, x: float, y: float) -> Node:
        node = Node(id, x, y)
        self.nodes[id] = node
        return node

    def add_member(self, id, node_i, node_j, E, A, I, hinge_i=False, hinge_j=False) -> Member:
        member = Member(id, node_i, node_j, E, A, I, hinge_i, hinge_j)
        self.members[id] = member
        return member

    def add_support(self, support: Support) -> None:
        self.supports[support.node_id] = support

    def add_nodal_load(self, load: NodalLoad) -> None:
        self.nodal_loads.append(load)

    def add_point_load(self, load: MemberPointLoad) -> None:
        self.point_loads.append(load)

    def add_udl(self, load: MemberUDL) -> None:
        self.udls.append(load)

    def node_order(self) -> list[str]:
        return list(self.nodes.keys())

    def member_length(self, member_id: str) -> float:
        m = self.members[member_id]
        ni, nj = self.nodes[m.node_i], self.nodes[m.node_j]
        return math.hypot(nj.x - ni.x, nj.y - ni.y)

    def member_angle(self, member_id: str) -> float:
        m = self.members[member_id]
        ni, nj = self.nodes[m.node_i], self.nodes[m.node_j]
        return math.atan2(nj.y - ni.y, nj.x - ni.x)

    def member_point_loads(self, member_id: str) -> list[MemberPointLoad]:
        return [p for p in self.point_loads if p.member_id == member_id]

    def member_udls(self, member_id: str) -> list[MemberUDL]:
        return [u for u in self.udls if u.member_id == member_id]


# ---------------------------------------------------------------------------
# Solver (direct stiffness method)
# ---------------------------------------------------------------------------

_DOF_PER_NODE = 3


class AnalysisError(RuntimeError):
    pass


@dataclass
class MemberState:
    member_id: str
    length: float
    angle: float
    t_matrix: np.ndarray
    d_local: np.ndarray
    end_forces: np.ndarray
    end_rotations: tuple[float, float]


@dataclass
class FrameResults:
    displacements: dict[str, tuple[float, float, float]]
    reactions: dict[str, tuple[float, float, float]]
    members: dict[str, MemberState] = field(default_factory=dict)


def local_stiffness(E: float, A: float, I: float, L: float) -> np.ndarray:
    EA_L = E * A / L
    EI_L3 = E * I / L**3
    EI_L2 = E * I / L**2
    EI_L = E * I / L
    k = np.zeros((6, 6))
    k[0, 0] = k[3, 3] = EA_L
    k[0, 3] = k[3, 0] = -EA_L
    k[1, 1] = k[4, 4] = 12 * EI_L3
    k[1, 4] = k[4, 1] = -12 * EI_L3
    k[1, 2] = k[2, 1] = 6 * EI_L2
    k[1, 5] = k[5, 1] = 6 * EI_L2
    k[2, 4] = k[4, 2] = -6 * EI_L2
    k[4, 5] = k[5, 4] = -6 * EI_L2
    k[2, 2] = k[5, 5] = 4 * EI_L
    k[2, 5] = k[5, 2] = 2 * EI_L
    return k


def transformation(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    r = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    t = np.zeros((6, 6))
    t[:3, :3] = r
    t[3:, 3:] = r
    return t


def _hermite(xi: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    h1 = 1 - 3 * xi**2 + 2 * xi**3
    h2 = xi - 2 * xi**2 + xi**3
    h3 = 3 * xi**2 - 2 * xi**3
    h4 = -(xi**2) + xi**3
    return h1, h2, h3, h4


def _hermite_prime(xi: np.ndarray, L: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    h1p = (-6 * xi + 6 * xi**2) / L
    h2p = 1 - 4 * xi + 3 * xi**2
    h3p = (6 * xi - 6 * xi**2) / L
    h4p = -2 * xi + 3 * xi**2
    return h1p, h2p, h3p, h4p


def _simpson(f, a: float, b: float, n: int = 200) -> float:
    if b <= a:
        return 0.0
    if n % 2:
        n += 1
    xs = np.linspace(a, b, n + 1)
    ys = np.array([f(x) for x in xs])
    h = (b - a) / n
    return h / 3 * (ys[0] + ys[-1] + 4 * np.sum(ys[1:-1:2]) + 2 * np.sum(ys[2:-1:2]))


def member_load_vector(model: FrameModel, member_id: str) -> np.ndarray:
    member = model.members[member_id]
    L = model.member_length(member_id)
    angle = model.member_angle(member_id)
    f = np.zeros(6)

    def to_local(fx: float, fy: float, frame: str) -> tuple[float, float]:
        if frame == "global":
            c, s = np.cos(angle), np.sin(angle)
            return c * fx + s * fy, -s * fx + c * fy
        return fx, fy

    for p in model.member_point_loads(member_id):
        px, py = to_local(p.fx, p.fy, p.frame)
        a = p.position
        xi = a / L
        h1, h2, h3, h4 = _hermite(np.array(xi))
        h1p, h2p, h3p, h4p = _hermite_prime(np.array(xi), L)
        f[0] += px * (1 - xi)
        f[3] += px * xi
        f[1] += py * float(h1)
        f[2] += py * L * float(h2)
        f[4] += py * float(h3)
        f[5] += py * L * float(h4)
        f[1] += p.m * float(h1p)
        f[2] += p.m * float(h2p)
        f[4] += p.m * float(h3p)
        f[5] += p.m * float(h4p)

    for u in model.member_udls(member_id):
        s = 0.0 if u.start is None else u.start
        e = L if u.end is None else u.end
        wx, wy = to_local(u.wx, u.wy, u.frame)

        f[0] += _simpson(lambda x: wx * (1 - x / L), s, e)
        f[3] += _simpson(lambda x: wx * (x / L), s, e)

        def h1f(x):
            return float(_hermite(np.array(x / L))[0])

        def h2f(x):
            return float(_hermite(np.array(x / L))[1])

        def h3f(x):
            return float(_hermite(np.array(x / L))[2])

        def h4f(x):
            return float(_hermite(np.array(x / L))[3])

        f[1] += _simpson(lambda x: wy * h1f(x), s, e)
        f[2] += _simpson(lambda x: wy * L * h2f(x), s, e)
        f[4] += _simpson(lambda x: wy * h3f(x), s, e)
        f[5] += _simpson(lambda x: wy * L * h4f(x), s, e)

    return f


def condense(k_local: np.ndarray, f_eq: np.ndarray, hinge_i: bool, hinge_j: bool) -> tuple[np.ndarray, np.ndarray]:
    if not hinge_i and not hinge_j:
        return k_local, f_eq

    released = []
    if hinge_i:
        released.append(2)
    if hinge_j:
        released.append(5)
    retained = [i for i in range(6) if i not in released]

    k_rr = k_local[np.ix_(retained, retained)]
    k_rc = k_local[np.ix_(retained, released)]
    k_cr = k_local[np.ix_(released, retained)]
    k_cc = k_local[np.ix_(released, released)]
    f_r = f_eq[retained]
    f_c = f_eq[released]

    k_cc_inv = np.linalg.inv(k_cc)
    k_eff = k_rr - k_rc @ k_cc_inv @ k_cr
    f_eff = f_r - k_rc @ k_cc_inv @ f_c

    k_full = np.zeros((6, 6))
    k_full[np.ix_(retained, retained)] = k_eff
    f_full = np.zeros(6)
    f_full[retained] = f_eff
    return k_full, f_full


def _hinge_rotation_back_substitution(k_local, f_eq, hinge_i, hinge_j, d_retained, retained) -> dict[int, float]:
    released = []
    if hinge_i:
        released.append(2)
    if hinge_j:
        released.append(5)
    if not released:
        return {}
    k_cr = k_local[np.ix_(released, retained)]
    k_cc = k_local[np.ix_(released, released)]
    f_c = f_eq[released]
    theta_c = np.linalg.solve(k_cc, f_c - k_cr @ d_retained)
    return dict(zip(released, theta_c))


def dof_indices(node_ids: list[str], node_id: str) -> list[int]:
    i = node_ids.index(node_id)
    return [i * _DOF_PER_NODE, i * _DOF_PER_NODE + 1, i * _DOF_PER_NODE + 2]


def solve(model: FrameModel) -> FrameResults:
    node_ids = model.node_order()
    n_dof = len(node_ids) * _DOF_PER_NODE
    K = np.zeros((n_dof, n_dof))
    F = np.zeros(n_dof)

    for load in model.nodal_loads:
        idx = dof_indices(node_ids, load.node_id)
        F[idx[0]] += load.fx
        F[idx[1]] += load.fy
        F[idx[2]] += load.m

    member_data: dict[str, dict] = {}
    for mid, member in model.members.items():
        L = model.member_length(mid)
        angle = model.member_angle(mid)
        k_local = local_stiffness(member.E, member.A, member.I, L)
        f_eq_local = member_load_vector(model, mid)
        k_full, f_full = condense(k_local, f_eq_local, member.hinge_i, member.hinge_j)
        T = transformation(angle)

        k_global = T.T @ k_full @ T
        f_global = T.T @ f_full

        idx = dof_indices(node_ids, member.node_i) + dof_indices(node_ids, member.node_j)
        for a in range(6):
            F[idx[a]] += f_global[a]
            for b in range(6):
                K[idx[a], idx[b]] += k_global[a, b]

        member_data[mid] = dict(L=L, angle=angle, k_local=k_local, f_eq_local=f_eq_local, k_full=k_full, f_full=f_full, T=T, idx=idx)

    restrained = np.zeros(n_dof, dtype=bool)
    prescribed = np.zeros(n_dof)
    for node_id, support in model.supports.items():
        idx = dof_indices(node_ids, node_id)
        for flag, dof in zip((support.ux, support.uy, support.rz), idx):
            if flag:
                restrained[dof] = True

    has_stiffness = ~np.isclose(K, 0.0).all(axis=1)
    inactive = ~has_stiffness & ~restrained
    if np.any(inactive & (np.abs(F) > 1e-9)):
        raise AnalysisError(
            "A load is applied at a DOF with no stiffness (e.g. a moment at a "
            "joint where every connected member is hinged there). The model "
            "is unstable at that DOF."
        )

    free = ~restrained & ~inactive
    K_ff = K[np.ix_(free, free)]
    K_fs = K[np.ix_(free, restrained)]
    F_f = F[free] - K_fs @ prescribed[restrained]

    if K_ff.size and np.linalg.cond(K_ff) > 1e13:
        raise AnalysisError(
            "Global stiffness matrix is singular or near-singular -- the "
            "structure is unstable or under-restrained (check supports and "
            "member hinges for missing restraints, e.g. a mechanism able to "
            "rotate or translate as a rigid body)."
        )

    try:
        U_f = np.linalg.solve(K_ff, F_f)
    except np.linalg.LinAlgError as exc:
        raise AnalysisError(
            "Global stiffness matrix is singular -- the structure is "
            "unstable or under-restrained (check supports and member hinges)."
        ) from exc

    U = np.zeros(n_dof)
    U[free] = U_f
    U[restrained] = prescribed[restrained]
    U[inactive] = 0.0

    K_sf = K[np.ix_(restrained, free)]
    K_ss = K[np.ix_(restrained, restrained)]
    K_si = K[np.ix_(restrained, inactive)]
    R = K_sf @ U_f + K_ss @ prescribed[restrained] + K_si @ U[inactive] - F[restrained]

    displacements = {node_id: tuple(U[dof_indices(node_ids, node_id)]) for node_id in node_ids}
    reaction_full = np.zeros(n_dof)
    reaction_full[restrained] = R
    reactions = {
        node_id: tuple(reaction_full[dof_indices(node_ids, node_id)])
        for node_id in node_ids
        if node_id in model.supports
    }

    members: dict[str, MemberState] = {}
    for mid, member in model.members.items():
        data = member_data[mid]
        idx = data["idx"]
        T = data["T"]
        d_global = U[idx]
        d_local = T @ d_global
        end_forces = data["k_full"] @ d_local - data["f_full"]

        retained = [i for i in range(6) if i not in (([2] if member.hinge_i else []) + ([5] if member.hinge_j else []))]
        theta_map = _hinge_rotation_back_substitution(
            data["k_local"], data["f_eq_local"], member.hinge_i, member.hinge_j, d_local[retained], retained
        )
        theta1 = theta_map.get(2, d_local[2])
        theta2 = theta_map.get(5, d_local[5])

        members[mid] = MemberState(
            member_id=mid, length=data["L"], angle=data["angle"], t_matrix=T,
            d_local=d_local, end_forces=end_forces, end_rotations=(float(theta1), float(theta2)),
        )

    return FrameResults(displacements=displacements, reactions=reactions, members=members)


# ---------------------------------------------------------------------------
# Diagrams (N/V/M + deflection sampling along a member)
# ---------------------------------------------------------------------------

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


def global_deformed_coords(model: FrameModel, results: FrameResults, member_id: str, scale: float = 1.0, n: int = 30):
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


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

_LOAD_FRACTION = 0.12
_SUPPORT_FRACTION = 0.06


def _model_extent(model: FrameModel) -> float:
    xs = [n.x for n in model.nodes.values()]
    ys = [n.y for n in model.nodes.values()]
    if not xs:
        return 1.0
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return span if span > 1e-9 else 1.0


def _to_global_vec(fx: float, fy: float, frame: str, angle: float) -> tuple[float, float]:
    if frame == "global":
        return fx, fy
    c, s = math.cos(angle), math.sin(angle)
    return c * fx - s * fy, s * fx + c * fy


def _draw_support(ax, x: float, y: float, ux: bool, uy: bool, rz: bool, size: float) -> None:
    if not (ux or uy or rz):
        return
    if uy or not ux:
        tri = Polygon([(x, y), (x - size / 2, y - size), (x + size / 2, y - size)], closed=True, facecolor="0.6", edgecolor="black", zorder=3)
        ax.add_patch(tri)
        base_y = y - size
        if rz:
            hatch_y = base_y - size * 0.15
            ax.plot([x - size * 0.7, x + size * 0.7], [hatch_y, hatch_y], color="black", lw=1, zorder=3)
            for hx in np.linspace(x - size * 0.6, x + size * 0.6, 5):
                ax.plot([hx, hx - size * 0.15], [hatch_y, hatch_y - size * 0.2], color="black", lw=0.8, zorder=3)
        elif ux != uy:
            for cx in np.linspace(x - size * 0.3, x + size * 0.3, 2):
                ax.add_patch(Circle((cx, base_y - size * 0.12), size * 0.12, facecolor="0.6", edgecolor="black", zorder=3))
    else:
        tri = Polygon([(x, y), (x - size, y - size / 2), (x - size, y + size / 2)], closed=True, facecolor="0.6", edgecolor="black", zorder=3)
        ax.add_patch(tri)


def _draw_force_arrow(ax, x: float, y: float, gx: float, gy: float, length: float, label: str) -> None:
    mag = math.hypot(gx, gy)
    if mag < 1e-12:
        return
    ux, uy = gx / mag, gy / mag
    ax.annotate("", xy=(x, y), xytext=(x - ux * length, y - uy * length), arrowprops=dict(arrowstyle="-|>", color="crimson", lw=1.5), zorder=4)
    ax.text(x - ux * length * 1.15, y - uy * length * 1.15, label, color="crimson", fontsize=7, ha="center", va="center", zorder=4)


def _draw_moment_arrow(ax, x: float, y: float, m: float, size: float, label: str) -> None:
    if abs(m) < 1e-12:
        return
    theta1, theta2 = (20, 290) if m > 0 else (290, 20)
    arc = Arc((x, y), size, size, angle=0, theta1=theta1, theta2=theta2, color="darkorange", lw=1.5, zorder=4)
    ax.add_patch(arc)
    end_angle = math.radians(theta2 if m > 0 else theta1)
    ax.annotate(
        "", xy=(x + size / 2 * math.cos(end_angle), y + size / 2 * math.sin(end_angle)),
        xytext=(x + size / 2 * math.cos(end_angle - 0.3), y + size / 2 * math.sin(end_angle - 0.3)),
        arrowprops=dict(arrowstyle="-|>", color="darkorange", lw=1.5), zorder=4,
    )
    ax.text(x + size, y + size, label, color="darkorange", fontsize=7, ha="center", va="center", zorder=4)


def _draw_loads(ax, model: FrameModel, extent: float) -> None:
    arrow_len = extent * _LOAD_FRACTION

    for load in model.nodal_loads:
        node = model.nodes[load.node_id]
        _draw_force_arrow(ax, node.x, node.y, load.fx, load.fy, arrow_len, f"{math.hypot(load.fx, load.fy):.3g}")
        _draw_moment_arrow(ax, node.x, node.y, load.m, arrow_len * 0.5, f"{load.m:.3g}")

    for p in model.point_loads:
        member = model.members[p.member_id]
        angle = model.member_angle(p.member_id)
        ni = model.nodes[member.node_i]
        x = ni.x + math.cos(angle) * p.position
        y = ni.y + math.sin(angle) * p.position
        gx, gy = _to_global_vec(p.fx, p.fy, p.frame, angle)
        _draw_force_arrow(ax, x, y, gx, gy, arrow_len, f"{math.hypot(gx, gy):.3g}")
        _draw_moment_arrow(ax, x, y, p.m, arrow_len * 0.5, f"{p.m:.3g}")

    for u in model.udls:
        member = model.members[u.member_id]
        L = model.member_length(u.member_id)
        angle = model.member_angle(u.member_id)
        ni = model.nodes[member.node_i]
        lo = 0.0 if u.start is None else u.start
        hi = L if u.end is None else u.end
        gx, gy = _to_global_vec(u.wx, u.wy, u.frame, angle)
        mag = math.hypot(gx, gy)
        if mag < 1e-12:
            continue
        ux_dir, uy_dir = gx / mag, gy / mag
        n_arrows = max(int((hi - lo) / max(L, 1e-9) * 8), 3)
        positions = np.linspace(lo, hi, n_arrows)
        small_len = arrow_len * 0.6
        tip_xs, tip_ys = [], []
        for pos in positions:
            x = ni.x + math.cos(angle) * pos
            y = ni.y + math.sin(angle) * pos
            ax.annotate("", xy=(x, y), xytext=(x - ux_dir * small_len, y - uy_dir * small_len), arrowprops=dict(arrowstyle="-|>", color="steelblue", lw=1.0), zorder=4)
            tip_xs.append(x - ux_dir * small_len)
            tip_ys.append(y - uy_dir * small_len)
        ax.plot(tip_xs, tip_ys, color="steelblue", lw=1.0, zorder=4)
        mid = len(positions) // 2
        ax.text(tip_xs[mid], tip_ys[mid], f"w={mag:.3g}", color="steelblue", fontsize=7, ha="center", va="bottom", zorder=4)


def plot_geometry(model: FrameModel, results: FrameResults | None = None, deformed_scale: float | None = None, show_loads: bool = True, show_labels: bool = True) -> Figure:
    extent = _model_extent(model)
    fig, ax = plt.subplots(figsize=(7, 6))

    for mid, member in model.members.items():
        ni, nj = model.nodes[member.node_i], model.nodes[member.node_j]
        ax.plot([ni.x, nj.x], [ni.y, nj.y], color="black", lw=2, zorder=2)
        if show_labels:
            ax.text((ni.x + nj.x) / 2, (ni.y + nj.y) / 2, mid, fontsize=8, color="dimgray", ha="center", va="bottom", zorder=2)

    for node_id, node in model.nodes.items():
        ax.plot(node.x, node.y, "o", color="black", markersize=4, zorder=3)
        if show_labels:
            ax.text(node.x, node.y, f" {node_id}", fontsize=8, ha="left", va="bottom", zorder=3)

    size = extent * _SUPPORT_FRACTION
    for node_id, support in model.supports.items():
        node = model.nodes[node_id]
        _draw_support(ax, node.x, node.y, support.ux, support.uy, support.rz, size)

    if show_loads:
        _draw_loads(ax, model, extent)

    if results is not None:
        if deformed_scale is None:
            deformed_scale = _autoscale_deformation(model, results, extent)
        for mid in model.members:
            xg, yg = global_deformed_coords(model, results, mid, scale=deformed_scale, n=30)
            ax.plot(xg, yg, color="royalblue", lw=2, zorder=2.5)
        ax.set_title(f"Deformed shape (scale x{deformed_scale:.3g})")
    else:
        ax.set_title("Geometry, supports, and loads")

    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, linestyle=":", alpha=0.5)
    margin = extent * 0.2
    xs = [n.x for n in model.nodes.values()]
    ys = [n.y for n in model.nodes.values()]
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
    fig.tight_layout()
    return fig


def _autoscale_deformation(model: FrameModel, results: FrameResults, extent: float, target_fraction: float = 0.1) -> float:
    max_defl = 0.0
    for mid in model.members:
        sample = sample_member(model, results, mid, n=30)
        max_defl = max(max_defl, float(np.max(np.abs(sample["deflection"]))), float(np.max(np.abs(sample["axial_deflection"]))))
    if max_defl < 1e-12:
        return 1.0
    return target_fraction * extent / max_defl


def plot_member_diagram(model: FrameModel, results: FrameResults, member_id: str, n: int = 100) -> Figure:
    sample = sample_member(model, results, member_id, n=n)
    member = model.members[member_id]
    xs = sample["x"]

    fig, axes = plt.subplots(3, 1, figsize=(7, 7), sharex=True)
    for ax, key, label, color in zip(axes, ("N", "V", "M"), ("N (axial)", "V (shear)", "M (moment)"), ("seagreen", "steelblue", "crimson")):
        y = sample[key]
        ax.fill_between(xs, y, 0.0, color=color, alpha=0.25)
        ax.plot(xs, y, color=color, lw=1.5)
        ax.axhline(0.0, color="black", lw=0.8)
        ax.set_ylabel(label)
        ax.grid(True, linestyle=":", alpha=0.5)

    axes[-1].set_xlabel("Position along member (from node_i)")
    fig.suptitle(f"Member {member_id} ({member.node_i} -> {member.node_j})")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Excel-table adapter + entry point
# ---------------------------------------------------------------------------


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return False
    return str(v).strip().upper() in ("TRUE", "1", "YES")


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == ""


def _support_from_type(node_id: str, type_name) -> Support:
    key = str(type_name).strip().lower()
    if key == "fixed":
        return Support.fixed(node_id)
    if key == "pinned":
        return Support.pinned(node_id)
    if key == "roller x":
        return Support.roller(node_id, "x")
    if key == "roller y":
        return Support.roller(node_id, "y")
    raise ValueError(f"Unknown support type {type_name!r} for node {node_id!r}")


def model_from_tables(
    nodes_df: pd.DataFrame,
    members_df: pd.DataFrame,
    supports_df: pd.DataFrame,
    nodal_loads_df: pd.DataFrame,
    point_loads_df: pd.DataFrame,
    udls_df: pd.DataFrame,
) -> FrameModel:
    """Build a FrameModel from the six input tables, in the column order
    used by every sheet in this project (id/x/y, id/node_i/node_j/E/A/I/
    hinge_i/hinge_j, node_id/type, node_id/fx/fy/m,
    member_id/position/fx/fy/m/frame, member_id/wx/wy/frame/start/end)."""
    model = FrameModel()

    for row in nodes_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        model.add_node(str(row[0]), float(row[1]), float(row[2]))

    for row in members_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        hinge_i = _to_bool(row[6]) if len(row) > 6 else False
        hinge_j = _to_bool(row[7]) if len(row) > 7 else False
        model.add_member(str(row[0]), str(row[1]), str(row[2]), float(row[3]), float(row[4]), float(row[5]), hinge_i, hinge_j)

    for row in supports_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        model.add_support(_support_from_type(str(row[0]), row[1]))

    for row in nodal_loads_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        fx = float(row[1]) if len(row) > 1 and not _is_blank(row[1]) else 0.0
        fy = float(row[2]) if len(row) > 2 and not _is_blank(row[2]) else 0.0
        m = float(row[3]) if len(row) > 3 and not _is_blank(row[3]) else 0.0
        model.add_nodal_load(NodalLoad(str(row[0]), fx, fy, m))

    for row in point_loads_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        fx = float(row[2]) if len(row) > 2 and not _is_blank(row[2]) else 0.0
        fy = float(row[3]) if len(row) > 3 and not _is_blank(row[3]) else 0.0
        m = float(row[4]) if len(row) > 4 and not _is_blank(row[4]) else 0.0
        frame = str(row[5]).strip().lower() if len(row) > 5 and not _is_blank(row[5]) else "local"
        model.add_point_load(MemberPointLoad(str(row[0]), float(row[1]), fx, fy, m, frame))

    for row in udls_df.itertuples(index=False):
        if _is_blank(row[0]):
            continue
        wx = float(row[1]) if len(row) > 1 and not _is_blank(row[1]) else 0.0
        wy = float(row[2]) if len(row) > 2 and not _is_blank(row[2]) else 0.0
        frame = str(row[3]).strip().lower() if len(row) > 3 and not _is_blank(row[3]) else "local"
        start = float(row[4]) if len(row) > 4 and not _is_blank(row[4]) else None
        end = float(row[5]) if len(row) > 5 and not _is_blank(row[5]) else None
        model.add_udl(MemberUDL(str(row[0]), wx, wy, frame, start, end))

    return model


def run(
    nodes_df: pd.DataFrame,
    members_df: pd.DataFrame,
    supports_df: pd.DataFrame,
    nodal_loads_df: pd.DataFrame,
    point_loads_df: pd.DataFrame,
    udls_df: pd.DataFrame,
    n: int = 100,
) -> dict:
    """Build, solve, and package everything the Reactions/Displacements/
    Diagrams cells need. This is the only function the Excel-side Engine
    cell calls; everything above is implementation detail."""
    model = model_from_tables(nodes_df, members_df, supports_df, nodal_loads_df, point_loads_df, udls_df)
    results = solve(model)

    reactions = pd.DataFrame(
        [[node_id, *results.reactions[node_id]] for node_id in model.supports],
        columns=["node_id", "Rx", "Ry", "Rm"],
    )
    displacements = pd.DataFrame(
        [[node_id, *results.displacements[node_id]] for node_id in model.node_order()],
        columns=["node_id", "Ux", "Uy", "Rz"],
    )

    def member_fig(member_id: str) -> Figure:
        return plot_member_diagram(model, results, str(member_id), n=n)

    return dict(
        model=model,
        results=results,
        reactions=reactions,
        displacements=displacements,
        geometry_fig=plot_geometry(model),
        deformed_fig=plot_geometry(model, results=results, show_loads=False),
        member_fig=member_fig,
    )
