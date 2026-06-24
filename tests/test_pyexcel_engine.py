"""Headless validation of structural2d/pyexcel/engine.py -- the module whose
*source* gets pasted into a single Insert Python cell in Excel. There's no
xl() and no live Excel here, so these tests stand pandas DataFrames in for
the Excel Tables xl("Nodes") etc. would return, and check the same
closed-form numbers used in tests/test_solver.py and test_workbook_io.py.
"""
import math

import pandas as pd

from structural2d.pyexcel.engine import run


def _simply_supported_beam_tables():
    """Simply supported beam, midspan point load -- same sample data as
    structural2d/excel/build_template.py's default workbook."""
    nodes = pd.DataFrame([["1", 0.0, 0.0], ["2", 6.0, 0.0]], columns=["id", "x", "y"])
    members = pd.DataFrame(
        [["m1", "1", "2", 200e9, 0.01, 8e-5, "FALSE", "FALSE"]],
        columns=["id", "node_i", "node_j", "E", "A", "I", "hinge_i", "hinge_j"],
    )
    supports = pd.DataFrame([["1", "Pinned"], ["2", "Roller Y"]], columns=["node_id", "type"])
    nodal_loads = pd.DataFrame(columns=["node_id", "fx", "fy", "m"])
    point_loads = pd.DataFrame(
        [["m1", 3.0, 0.0, -10000.0, 0.0, "local"]],
        columns=["member_id", "position", "fx", "fy", "m", "frame"],
    )
    udls = pd.DataFrame(columns=["member_id", "wx", "wy", "frame", "start", "end"])
    return nodes, members, supports, nodal_loads, point_loads, udls


def test_simply_supported_beam_matches_closed_form():
    nodes, members, supports, nodal_loads, point_loads, udls = _simply_supported_beam_tables()
    result = run(nodes, members, supports, nodal_loads, point_loads, udls)

    P, L = 10_000.0, 6.0

    reactions = result["reactions"].set_index("node_id")
    assert math.isclose(reactions.loc["1", "Ry"], P / 2, rel_tol=1e-9)
    assert math.isclose(reactions.loc["2", "Ry"], P / 2, rel_tol=1e-9)

    displacements = result["displacements"].set_index("node_id")
    # exact closed-form end rotation for a simply supported beam under a
    # midspan point load: theta = -P*L^2/(16*E*I)
    E, I = 200e9, 8e-5
    theta_expected = -P * L**2 / (16 * E * I)
    assert math.isclose(displacements.loc["1", "Rz"], theta_expected, rel_tol=1e-4)

    assert result["geometry_fig"] is not None
    assert result["deformed_fig"] is not None
    fig = result["member_fig"]("m1")
    assert fig is not None


def test_blank_optional_columns_default_sensibly():
    """Excel Tables hand back NaN for blank optional cells (hinge flags,
    frame, udl start/end) -- the adapter must treat those as the documented
    defaults rather than raising."""
    nodes, members, supports, nodal_loads, point_loads, udls = _simply_supported_beam_tables()
    members = pd.DataFrame(
        [["m1", "1", "2", 200e9, 0.01, 8e-5, None, None]],
        columns=["id", "node_i", "node_j", "E", "A", "I", "hinge_i", "hinge_j"],
    )
    point_loads = pd.DataFrame(
        [["m1", 3.0, 0.0, -10000.0, 0.0, None]],
        columns=["member_id", "position", "fx", "fy", "m", "frame"],
    )
    result = run(nodes, members, supports, nodal_loads, point_loads, udls)
    reactions = result["reactions"].set_index("node_id")
    assert math.isclose(reactions.loc["1", "Ry"], 5000.0, rel_tol=1e-9)


def test_blank_placeholder_row_in_optional_table_is_skipped():
    """A leftover blank row in an Excel Table (e.g. the one row Excel adds
    by default when you create a Table from a header-only range) must not
    be parsed as a load on a nonexistent node/member."""
    nodes, members, supports, _, point_loads, _ = _simply_supported_beam_tables()
    nodal_loads = pd.DataFrame([[None, None, None, None]], columns=["node_id", "fx", "fy", "m"])
    udls = pd.DataFrame([[None, None, None, None, None, None]], columns=["member_id", "wx", "wy", "frame", "start", "end"])
    result = run(nodes, members, supports, nodal_loads, point_loads, udls)
    reactions = result["reactions"].set_index("node_id")
    assert math.isclose(reactions.loc["1", "Ry"], 5000.0, rel_tol=1e-9)
