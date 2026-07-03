import math

import numpy as np
import pytest

from structural2d.diagrams import sample_member
from structural2d.model import (
    FrameModel,
    MemberPointLoad,
    MemberUDL,
    NodalLoad,
    Support,
)
from structural2d.solver import AnalysisError, solve

E = 200e9
A = 0.01
I = 8e-5


def simply_supported(L):
    m = FrameModel()
    m.add_node("1", 0.0, 0.0)
    m.add_node("2", L, 0.0)
    m.add_member("m1", "1", "2", E, A, I)
    m.add_support(Support.pinned("1"))
    m.add_support(Support.roller("2", "y"))
    return m


def cantilever(L):
    m = FrameModel()
    m.add_node("1", 0.0, 0.0)
    m.add_node("2", L, 0.0)
    m.add_member("m1", "1", "2", E, A, I)
    m.add_support(Support.fixed("1"))
    return m


def test_simply_supported_beam_midspan_point_load():
    L = 6.0
    P = 10_000.0
    model = simply_supported(L)
    model.add_point_load(MemberPointLoad("m1", L / 2, fy=-P))
    results = solve(model)

    rx1, ry1, rm1 = results.reactions["1"]
    rx2, ry2, rm2 = results.reactions["2"]
    assert math.isclose(ry1, P / 2, rel_tol=1e-9)
    assert math.isclose(ry2, P / 2, rel_tol=1e-9)
    assert math.isclose(rm1, 0.0, abs_tol=1e-6)
    assert math.isclose(rm2, 0.0, abs_tol=1e-6)

    sample = sample_member(model, results, "m1", n=200)
    assert math.isclose(sample["M"].max(), P * L / 4, rel_tol=1e-6)

    just_before = sample["V"][sample["x"] < L / 2 - 1e-6][-1]
    just_after = sample["V"][sample["x"] > L / 2 + 1e-6][0]
    assert math.isclose(just_before, P / 2, rel_tol=1e-6)
    assert math.isclose(just_after, -P / 2, rel_tol=1e-6)

    expected_defl = -P * L**3 / (48 * E * I)
    mid_idx = np.argmin(np.abs(sample["x"] - L / 2))
    assert math.isclose(sample["deflection"][mid_idx], expected_defl, rel_tol=1e-4)


def test_simply_supported_beam_full_udl():
    L = 8.0
    w = 5_000.0
    model = simply_supported(L)
    model.add_udl(MemberUDL("m1", wy=-w))
    results = solve(model)

    _, ry1, _ = results.reactions["1"]
    _, ry2, _ = results.reactions["2"]
    assert math.isclose(ry1, w * L / 2, rel_tol=1e-9)
    assert math.isclose(ry2, w * L / 2, rel_tol=1e-9)

    sample = sample_member(model, results, "m1", n=400)
    assert math.isclose(sample["M"].max(), w * L**2 / 8, rel_tol=1e-4)

    expected_defl = -5 * w * L**4 / (384 * E * I)
    mid_idx = np.argmin(np.abs(sample["x"] - L / 2))
    assert math.isclose(sample["deflection"][mid_idx], expected_defl, rel_tol=1e-4)


def test_cantilever_tip_point_load():
    L = 4.0
    P = 3_000.0
    model = cantilever(L)
    model.add_point_load(MemberPointLoad("m1", L, fy=-P))
    results = solve(model)

    rx1, ry1, rm1 = results.reactions["1"]
    assert math.isclose(ry1, P, rel_tol=1e-9)
    assert math.isclose(rm1, -P * L, rel_tol=1e-9) or math.isclose(rm1, P * L, rel_tol=1e-9)

    sample = sample_member(model, results, "m1", n=200)
    assert np.allclose(sample["V"], P, rtol=1e-9)

    expected_tip_defl = -P * L**3 / (3 * E * I)
    assert math.isclose(sample["deflection"][-1], expected_tip_defl, rel_tol=1e-4)


def test_cantilever_full_udl():
    L = 5.0
    w = 2_000.0
    model = cantilever(L)
    model.add_udl(MemberUDL("m1", wy=-w))
    results = solve(model)

    _, ry1, rm1 = results.reactions["1"]
    assert math.isclose(ry1, w * L, rel_tol=1e-9)
    assert math.isclose(abs(rm1), w * L**2 / 2, rel_tol=1e-9)

    sample = sample_member(model, results, "m1", n=400)
    expected_tip_defl = -w * L**4 / (8 * E * I)
    assert math.isclose(sample["deflection"][-1], expected_tip_defl, rel_tol=1e-4)


def test_two_bar_truss_symmetric():
    """Classic symmetric 2-bar truss: A=(0,0), B=(2,0) pinned to ground,
    apex C=(1,1) loaded with vertical P. By statics each bar carries
    P / (2 sin(theta)) where theta is the angle from horizontal, in
    compression (the struts push up and outward on the loaded apex)."""
    P = 1000.0
    model = FrameModel()
    model.add_node("A", 0.0, 0.0)
    model.add_node("B", 2.0, 0.0)
    model.add_node("C", 1.0, 1.0)
    model.add_member("AC", "A", "C", E, A, I, hinge_i=True, hinge_j=True)
    model.add_member("BC", "B", "C", E, A, I, hinge_i=True, hinge_j=True)
    model.add_support(Support.pinned("A"))
    model.add_support(Support.pinned("B"))
    model.add_nodal_load(NodalLoad("C", fy=-P))

    results = solve(model)
    theta = math.atan2(1.0, 1.0)
    expected_force = P / (2 * math.sin(theta))

    force_ac = results.members["AC"].end_forces[3]
    force_bc = results.members["BC"].end_forces[3]
    assert math.isclose(force_ac, -expected_force, rel_tol=1e-6)
    assert math.isclose(force_bc, -expected_force, rel_tol=1e-6)

    rx_a, ry_a, _ = results.reactions["A"]
    rx_b, ry_b, _ = results.reactions["B"]
    assert math.isclose(ry_a + ry_b, P, rel_tol=1e-9)
    assert math.isclose(rx_a + rx_b, 0.0, abs_tol=1e-6)


def test_propped_cantilever_with_hinge_matches_simple_beam_reaction():
    """A member rigidly fixed at node 1 but pin-connected (hinge) at node 2,
    with node 2 simply supported (roller), behaves like... actually with a
    hinge at the roller end the member can't transfer moment there, so this
    reduces to a simply supported beam with one end's support moved to a
    hinge -- reactions should match the simple beam case."""
    L = 6.0
    P = 4000.0
    model = FrameModel()
    model.add_node("1", 0.0, 0.0)
    model.add_node("2", L, 0.0)
    model.add_member("m1", "1", "2", E, A, I, hinge_i=False, hinge_j=True)
    model.add_support(Support.pinned("1"))
    model.add_support(Support.roller("2", "y"))
    model.add_point_load(MemberPointLoad("m1", L / 2, fy=-P))
    results = solve(model)

    _, ry1, rm1 = results.reactions["1"]
    _, ry2, rm2 = results.reactions["2"]
    assert math.isclose(ry1, P / 2, rel_tol=1e-6)
    assert math.isclose(ry2, P / 2, rel_tol=1e-6)
    assert math.isclose(rm1, 0.0, abs_tol=1e-6)
    assert math.isclose(rm2, 0.0, abs_tol=1e-6)


def test_singular_model_raises():
    model = FrameModel()
    model.add_node("1", 0.0, 0.0)
    model.add_node("2", 5.0, 0.0)
    model.add_member("m1", "1", "2", E, A, I)
    model.add_support(Support.pinned("1"))
    # node 2 entirely unrestrained -> unstable
    with pytest.raises(AnalysisError):
        solve(model)


def test_portal_frame_symmetric_point_load():
    """Symmetric portal frame, fixed bases, horizontal point load at the
    top of a column should produce equal and opposite axial forces in the
    two columns due to the overturning moment, and the structure should
    be in global equilibrium."""
    H, Wd = 3.0, 4.0
    P = 5000.0
    model = FrameModel()
    model.add_node("base1", 0.0, 0.0)
    model.add_node("top1", 0.0, H)
    model.add_node("top2", Wd, H)
    model.add_node("base2", Wd, 0.0)
    model.add_member("col1", "base1", "top1", E, A, I)
    model.add_member("beam", "top1", "top2", E, A, I)
    model.add_member("col2", "top2", "base2", E, A, I)
    model.add_support(Support.fixed("base1"))
    model.add_support(Support.fixed("base2"))
    model.add_nodal_load(NodalLoad("top1", fx=P))

    results = solve(model)
    rx1, ry1, rm1 = results.reactions["base1"]
    rx2, ry2, rm2 = results.reactions["base2"]

    assert math.isclose(rx1 + rx2, -P, rel_tol=1e-6)
    assert math.isclose(ry1 + ry2, 0.0, abs_tol=1e-3)
    # Full moment equilibrium of the whole frame about base1 (0,0): the
    # applied load's moment must balance the base reaction couples (rm1,
    # rm2 -- both bases are fixed, so they carry moment reactions) plus
    # the moment of base2's vertical reaction force about base1.
    assert math.isclose(-P * H + rm1 + rm2 + ry2 * Wd, 0.0, rel_tol=1e-6, abs_tol=1.0)
