"""Direct stiffness method for 2D frames.

Local DOF order per node is (axial u, transverse v, rotation theta), so a
member's local 6-vector is [u1, v1, t1, u2, v2, t2]. Global DOF order per
node is (X, Y, theta), 3 per node.

Member loads (point loads / UDLs) are converted to work-equivalent
("consistent") nodal load vectors via the element shape functions, then
assembled into the global load vector. Recovered member-end forces are

    Q_local = k_local @ d_local - f_eq_local

which is the standard matrix-structural-analysis superposition of the
displacement-induced response and the fixed-end load. See model.py for
the load/geometry definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import FrameModel, MemberPointLoad, MemberUDL

_DOF_PER_NODE = 3


class AnalysisError(RuntimeError):
    pass


@dataclass
class MemberState:
    """Everything the diagrams/plotting layer needs to reconstruct a member's response."""

    member_id: str
    length: float
    angle: float
    t_matrix: np.ndarray  # 6x6 global->local transform
    d_local: np.ndarray  # 6-vector, actual local end displacements (note: released-end rotation entry is not physical, see end_rotations)
    end_forces: np.ndarray  # 6-vector [N1, V1, M1, N2, V2, M2], local axes
    end_rotations: tuple[float, float]  # true local end rotations (theta1, theta2), accounting for hinge condensation


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
    """Work-equivalent nodal load vector (local axes) for all loads on a member."""
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
        # concentrated moment: virtual work = m * theta(a) = m * dv/dx(a)
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
    """Static condensation of released rotational DOFs (member end hinges)."""
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


def _hinge_rotation_back_substitution(
    k_local: np.ndarray,
    f_eq: np.ndarray,
    hinge_i: bool,
    hinge_j: bool,
    d_retained: np.ndarray,
    retained: list[int],
) -> dict[int, float]:
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

        member_data[mid] = dict(
            L=L, angle=angle, k_local=k_local, f_eq_local=f_eq_local,
            k_full=k_full, f_full=f_full, T=T, idx=idx,
        )

    restrained = np.zeros(n_dof, dtype=bool)
    prescribed = np.zeros(n_dof)
    for node_id, support in model.supports.items():
        idx = dof_indices(node_ids, node_id)
        for flag, dof in zip((support.ux, support.uy, support.rz), idx):
            if flag:
                restrained[dof] = True

    # A rotational DOF at a node where every connected member is hinged at
    # that end (or a node with no members at all) gets a zero row/col in K
    # -- e.g. every joint in a pure truss. It carries no stiffness and no
    # meaningful physical rotation, so it must be dropped from the solve
    # rather than left to make K_ff singular.
    has_stiffness = ~np.isclose(K, 0.0).all(axis=1)
    inactive = ~has_stiffness & ~restrained
    if np.any(inactive & (np.abs(F) > 1e-9)):
        raise AnalysisError(
            "A load is applied at a DOF with no stiffness (e.g. a moment "
            "at a joint where every connected member is hinged there). "
            "The model is unstable at that DOF."
        )

    free = ~restrained & ~inactive
    K_ff = K[np.ix_(free, free)]
    K_fs = K[np.ix_(free, restrained)]
    F_f = F[free] - K_fs @ prescribed[restrained]

    if K_ff.size and np.linalg.cond(K_ff) > 1e13:
        raise AnalysisError(
            "Global stiffness matrix is singular or near-singular -- the "
            "structure is unstable or under-restrained (check supports "
            "and member hinges for missing restraints, e.g. a mechanism "
            "able to rotate or translate as a rigid body)."
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

    displacements = {
        node_id: tuple(U[dof_indices(node_ids, node_id)]) for node_id in node_ids
    }
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

        retained = [i for i in range(6) if i not in (
            ([2] if member.hinge_i else []) + ([5] if member.hinge_j else [])
        )]
        theta_map = _hinge_rotation_back_substitution(
            data["k_local"], data["f_eq_local"], member.hinge_i, member.hinge_j,
            d_local[retained], retained,
        )
        theta1 = theta_map.get(2, d_local[2])
        theta2 = theta_map.get(5, d_local[5])

        members[mid] = MemberState(
            member_id=mid,
            length=data["L"],
            angle=data["angle"],
            t_matrix=T,
            d_local=d_local,
            end_forces=end_forces,
            end_rotations=(float(theta1), float(theta2)),
        )

    return FrameResults(displacements=displacements, reactions=reactions, members=members)
