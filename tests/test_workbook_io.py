import math

from openpyxl import load_workbook

from structural2d.excel.build_template import build_template
from structural2d.excel.workbook_io import read_model_openpyxl, write_results_openpyxl
from structural2d.solver import solve


def test_template_round_trip(tmp_path):
    """build_template's own sample data (simply supported beam, midspan
    point load) should read back, solve, and write results identically to
    the closed-form solution, and the Diagrams sheet should get images."""
    path = tmp_path / "frame_model.xlsx"
    build_template(str(path))

    wb = load_workbook(str(path))
    model = read_model_openpyxl(wb)

    assert set(model.nodes) == {"1", "2"}
    assert model.members["m1"].node_i == "1"
    assert model.members["m1"].node_j == "2"
    assert model.supports["1"].ux and model.supports["1"].uy and not model.supports["1"].rz
    assert not model.supports["2"].ux and model.supports["2"].uy
    assert len(model.point_loads) == 1

    results = solve(model)
    P, L = 10_000.0, 6.0
    rx1, ry1, _ = results.reactions["1"]
    rx2, ry2, _ = results.reactions["2"]
    assert math.isclose(ry1, P / 2, rel_tol=1e-9)
    assert math.isclose(ry2, P / 2, rel_tol=1e-9)

    write_results_openpyxl(wb, model, results)
    wb.save(str(path))

    wb2 = load_workbook(str(path))
    reaction_rows = list(wb2["Reactions"].iter_rows(values_only=True))
    assert reaction_rows[0] == ("node_id", "Rx", "Ry", "Rm")
    assert reaction_rows[1][0] == "1"
    assert math.isclose(reaction_rows[1][2], P / 2, rel_tol=1e-9)

    displacement_rows = list(wb2["Displacements"].iter_rows(values_only=True))
    assert displacement_rows[0] == ("node_id", "Ux", "Uy", "Rz")

    assert len(wb2["Diagrams"]._images) == 3


def test_rerunning_write_results_does_not_duplicate_images(tmp_path):
    """write_results_openpyxl clears the Diagrams sheet first, so calling
    it twice (as happens every time the user re-runs the analysis) must
    not accumulate images or stale table rows."""
    path = tmp_path / "frame_model.xlsx"
    build_template(str(path))
    wb = load_workbook(str(path))
    model = read_model_openpyxl(wb)
    results = solve(model)

    write_results_openpyxl(wb, model, results)
    write_results_openpyxl(wb, model, results)

    assert len(wb["Diagrams"]._images) == 3
    reaction_rows = [r for r in wb["Reactions"].iter_rows(values_only=True) if r[0] is not None]
    assert len(reaction_rows) == 3  # header + 2 nodes, no leftover duplicates
