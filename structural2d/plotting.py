"""matplotlib rendering of model geometry/loads, deformed shape, and
per-member N/V/M diagrams -- the figures this module returns are embedded
into the Excel workbook by workbook_io.py.

All supports are drawn relative to the global axes (a Support restrains
global ux/uy/rz, not member-local directions), member point loads/UDLs are
converted from their local or global load frame into global XY for
arrow placement, and load arrow lengths are a fixed fraction of the model's
bounding-box size -- they show direction, not magnitude-to-scale; magnitude
is given by the adjacent text label.
"""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon

from .diagrams import global_deformed_coords, sample_member
from .model import FrameModel
from .solver import FrameResults

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
        # vertical orientation: ground below the node (covers pinned/fixed/
        # vertical-roller, and is the sane default when only rz is set).
        tri = Polygon(
            [(x, y), (x - size / 2, y - size), (x + size / 2, y - size)],
            closed=True, facecolor="0.6", edgecolor="black", zorder=3,
        )
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
        # horizontal orientation: only ux restrained (roller against a wall).
        tri = Polygon(
            [(x, y), (x - size, y - size / 2), (x - size, y + size / 2)],
            closed=True, facecolor="0.6", edgecolor="black", zorder=3,
        )
        ax.add_patch(tri)


def _draw_force_arrow(ax, x: float, y: float, gx: float, gy: float, length: float, label: str) -> None:
    mag = math.hypot(gx, gy)
    if mag < 1e-12:
        return
    ux, uy = gx / mag, gy / mag
    ax.annotate(
        "", xy=(x, y), xytext=(x - ux * length, y - uy * length),
        arrowprops=dict(arrowstyle="-|>", color="crimson", lw=1.5), zorder=4,
    )
    ax.text(x - ux * length * 1.15, y - uy * length * 1.15, label, color="crimson",
            fontsize=7, ha="center", va="center", zorder=4)


def _draw_moment_arrow(ax, x: float, y: float, m: float, size: float, label: str) -> None:
    if abs(m) < 1e-12:
        return
    theta1, theta2 = (20, 290) if m > 0 else (290, 20)
    arc = matplotlib.patches.Arc((x, y), size, size, angle=0, theta1=theta1, theta2=theta2, color="darkorange", lw=1.5, zorder=4)
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
            ax.annotate(
                "", xy=(x, y), xytext=(x - ux_dir * small_len, y - uy_dir * small_len),
                arrowprops=dict(arrowstyle="-|>", color="steelblue", lw=1.0), zorder=4,
            )
            tip_xs.append(x - ux_dir * small_len)
            tip_ys.append(y - uy_dir * small_len)
        ax.plot(tip_xs, tip_ys, color="steelblue", lw=1.0, zorder=4)
        mid = len(positions) // 2
        ax.text(tip_xs[mid], tip_ys[mid], f"w={mag:.3g}", color="steelblue", fontsize=7, ha="center", va="bottom", zorder=4)


def plot_geometry(
    model: FrameModel,
    results: FrameResults | None = None,
    deformed_scale: float | None = None,
    show_loads: bool = True,
    show_labels: bool = True,
) -> Figure:
    """Undeformed geometry/support/load diagram, optionally overlaid with the deformed shape."""
    extent = _model_extent(model)
    fig, ax = plt.subplots(figsize=(7, 6))

    for mid, member in model.members.items():
        ni, nj = model.nodes[member.node_i], model.nodes[member.node_j]
        ax.plot([ni.x, nj.x], [ni.y, nj.y], color="black", lw=2, zorder=2)
        if show_labels:
            ax.text((ni.x + nj.x) / 2, (ni.y + nj.y) / 2, mid, fontsize=8, color="dimgray",
                    ha="center", va="bottom", zorder=2)

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
    """Stacked N/V/M diagrams along the local axis of a single member."""
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


def build_all_figures(model: FrameModel, results: FrameResults, n: int = 100) -> dict[str, Figure]:
    """Geometry, deformed shape, and per-member N/V/M figures, keyed for sheet/picture naming."""
    figures: dict[str, Figure] = {
        "geometry": plot_geometry(model),
        "deformed": plot_geometry(model, results=results, show_loads=False),
    }
    for mid in model.members:
        figures[f"member_{mid}"] = plot_member_diagram(model, results, mid, n=n)
    return figures
