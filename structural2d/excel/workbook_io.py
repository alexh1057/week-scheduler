"""Reads a FrameModel from the workbook's input sheets and writes analysis
results (tables + matplotlib diagrams) back to the output sheets.

The row-parsing and result-table logic is backend-agnostic (it works on
plain lists of row values), so it's exercised headlessly in tests against
an openpyxl Workbook. Live use from Excel goes through the xlwings
adapters at the bottom of this file (frame.py calls those), which read/
write an open xw.Book in place -- that path can't be exercised in this
sandbox (no Excel installed) and has not been run, only written.
"""
from __future__ import annotations

import io
from typing import Any

from ..model import FrameModel, MemberPointLoad, MemberUDL, NodalLoad, Support
from ..solver import FrameResults

INPUT_SHEETS = ["Nodes", "Members", "Supports", "NodalLoads", "PointLoads", "UDLs"]


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().upper() in ("TRUE", "1", "YES")


def _data_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Drop the header row and any trailing fully-blank rows."""
    out = []
    for row in rows[1:]:
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        out.append(list(row))
    return out


def _support_from_type(node_id: str, type_name: str) -> Support:
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


def model_from_sheet_rows(sheets: dict[str, list[list[Any]]]) -> FrameModel:
    """Build a FrameModel from {sheet_name: rows_including_header}."""
    model = FrameModel()

    for row in _data_rows(sheets.get("Nodes", [[]])):
        node_id, x, y = row[0], row[1], row[2]
        model.add_node(str(node_id), float(x), float(y))

    for row in _data_rows(sheets.get("Members", [[]])):
        member_id, node_i, node_j, E, A, I = row[0], row[1], row[2], row[3], row[4], row[5]
        hinge_i = _to_bool(row[6]) if len(row) > 6 else False
        hinge_j = _to_bool(row[7]) if len(row) > 7 else False
        model.add_member(str(member_id), str(node_i), str(node_j), float(E), float(A), float(I), hinge_i, hinge_j)

    for row in _data_rows(sheets.get("Supports", [[]])):
        node_id, type_name = row[0], row[1]
        model.add_support(_support_from_type(str(node_id), type_name))

    for row in _data_rows(sheets.get("NodalLoads", [[]])):
        node_id = str(row[0])
        fx = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
        fy = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
        m = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
        model.add_nodal_load(NodalLoad(node_id, fx, fy, m))

    for row in _data_rows(sheets.get("PointLoads", [[]])):
        member_id, position = str(row[0]), float(row[1])
        fx = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
        fy = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
        m = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0
        frame = str(row[5]).strip().lower() if len(row) > 5 and row[5] else "local"
        model.add_point_load(MemberPointLoad(member_id, position, fx, fy, m, frame))

    for row in _data_rows(sheets.get("UDLs", [[]])):
        member_id = str(row[0])
        wx = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
        wy = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
        frame = str(row[3]).strip().lower() if len(row) > 3 and row[3] else "local"
        start = float(row[4]) if len(row) > 4 and row[4] not in (None, "") else None
        end = float(row[5]) if len(row) > 5 and row[5] not in (None, "") else None
        model.add_udl(MemberUDL(member_id, wx, wy, frame, start, end))

    return model


def reaction_rows(model: FrameModel, results: FrameResults) -> list[list[Any]]:
    return [[node_id, *results.reactions[node_id]] for node_id in model.supports]


def displacement_rows(model: FrameModel, results: FrameResults) -> list[list[Any]]:
    return [[node_id, *results.displacements[node_id]] for node_id in model.node_order()]


# ---------------------------------------------------------------------------
# openpyxl adapter (headless-testable)
# ---------------------------------------------------------------------------


def read_model_openpyxl(wb) -> FrameModel:
    sheets = {}
    for name in INPUT_SHEETS:
        ws = wb[name]
        sheets[name] = [list(row) for row in ws.iter_rows(values_only=True)]
    return model_from_sheet_rows(sheets)


def write_results_openpyxl(wb, model: FrameModel, results: FrameResults, n: int = 100) -> None:
    from openpyxl.drawing.image import Image as XLImage

    from ..plotting import build_all_figures

    _write_table(wb["Reactions"], ["node_id", "Rx", "Ry", "Rm"], reaction_rows(model, results))
    _write_table(wb["Displacements"], ["node_id", "Ux", "Uy", "Rz"], displacement_rows(model, results))

    ws = wb["Diagrams"]
    for row in list(ws.rows):
        for cell in row:
            cell.value = None
    ws._images = []

    row_cursor = 1
    for fig in build_all_figures(model, results, n=n).values():
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110)
        buf.seek(0)
        img = XLImage(buf)
        ws.add_image(img, f"A{row_cursor}")
        row_cursor += int(img.height / 20) + 2


def _write_table(ws, headers: list[str], rows: list[list[Any]]) -> None:
    for row in list(ws.rows):
        for cell in row:
            cell.value = None
    for col, name in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=name)
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)


# ---------------------------------------------------------------------------
# xlwings adapter (live Excel automation -- not runnable/tested in this
# sandbox, no Excel/xlwings installed here; written to the documented API).
# ---------------------------------------------------------------------------


def read_model_xlwings(book) -> FrameModel:
    sheets = {}
    for name in INPUT_SHEETS:
        sheets[name] = book.sheets[name].used_range.value or []
        if sheets[name] and not isinstance(sheets[name][0], list):
            sheets[name] = [sheets[name]]
    return model_from_sheet_rows(sheets)


def write_results_xlwings(book, model: FrameModel, results: FrameResults, n: int = 100) -> None:
    from ..plotting import build_all_figures

    reactions_sheet = book.sheets["Reactions"]
    reactions_sheet.clear_contents()
    reactions_sheet.range("A1").value = [["node_id", "Rx", "Ry", "Rm"]] + reaction_rows(model, results)

    displacements_sheet = book.sheets["Displacements"]
    displacements_sheet.clear_contents()
    displacements_sheet.range("A1").value = [["node_id", "Ux", "Uy", "Rz"]] + displacement_rows(model, results)

    diagrams_sheet = book.sheets["Diagrams"]
    for picture in list(diagrams_sheet.pictures):
        picture.delete()

    top = 10
    for name, fig in build_all_figures(model, results, n=n).items():
        pic = diagrams_sheet.pictures.add(fig, name=name, update=True, left=10, top=top)
        top += pic.height + 15
