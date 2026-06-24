"""Scaffolds the input/output workbook for the 2D frame analysis tool.

Pure openpyxl (no Excel/xlwings needed), so it's testable headlessly. The
generated workbook is later opened in Excel and read/written live by
workbook_io.py through the xlwings "Run main" button (see frame.py).
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

_HEADER_FILL = PatternFill(start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid")
_HEADER_FONT = Font(bold=True)

SUPPORT_TYPES = ["Fixed", "Pinned", "Roller X", "Roller Y"]
LOAD_FRAMES = ["local", "global"]
BOOL_CHOICES = ["TRUE", "FALSE"]


def _write_header(ws: Worksheet, headers: list[str]) -> None:
    for col, name in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"


def _autosize(ws: Worksheet, widths: list[int]) -> None:
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width


def _add_list_validation(ws: Worksheet, col_letter: str, choices: list[str], n_rows: int = 200) -> None:
    dv = DataValidation(type="list", formula1=f'"{",".join(choices)}"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}2:{col_letter}{n_rows + 1}")


def _build_nodes(wb: Workbook) -> None:
    ws = wb.create_sheet("Nodes")
    _write_header(ws, ["id", "x", "y"])
    ws.append(["1", 0.0, 0.0])
    ws.append(["2", 6.0, 0.0])
    _autosize(ws, [10, 12, 12])


def _build_members(wb: Workbook) -> None:
    ws = wb.create_sheet("Members")
    _write_header(ws, ["id", "node_i", "node_j", "E", "A", "I", "hinge_i", "hinge_j"])
    ws.append(["m1", "1", "2", 200e9, 0.01, 8e-5, "FALSE", "FALSE"])
    _autosize(ws, [10, 10, 10, 14, 12, 12, 10, 10])
    _add_list_validation(ws, "G", BOOL_CHOICES)
    _add_list_validation(ws, "H", BOOL_CHOICES)


def _build_supports(wb: Workbook) -> None:
    ws = wb.create_sheet("Supports")
    _write_header(ws, ["node_id", "type"])
    ws.append(["1", "Pinned"])
    ws.append(["2", "Roller Y"])
    _autosize(ws, [10, 14])
    _add_list_validation(ws, "B", SUPPORT_TYPES)


def _build_nodal_loads(wb: Workbook) -> None:
    ws = wb.create_sheet("NodalLoads")
    _write_header(ws, ["node_id", "fx", "fy", "m"])
    _autosize(ws, [10, 12, 12, 12])


def _build_point_loads(wb: Workbook) -> None:
    ws = wb.create_sheet("PointLoads")
    _write_header(ws, ["member_id", "position", "fx", "fy", "m", "frame"])
    ws.append(["m1", 3.0, 0.0, -10000.0, 0.0, "local"])
    _autosize(ws, [10, 12, 12, 12, 12, 10])
    _add_list_validation(ws, "F", LOAD_FRAMES)


def _build_udls(wb: Workbook) -> None:
    ws = wb.create_sheet("UDLs")
    _write_header(ws, ["member_id", "wx", "wy", "frame", "start", "end"])
    _autosize(ws, [10, 12, 12, 10, 12, 12])
    _add_list_validation(ws, "D", LOAD_FRAMES)


def _build_reactions(wb: Workbook) -> None:
    ws = wb.create_sheet("Reactions")
    _write_header(ws, ["node_id", "Rx", "Ry", "Rm"])
    _autosize(ws, [10, 14, 14, 14])


def _build_displacements(wb: Workbook) -> None:
    ws = wb.create_sheet("Displacements")
    _write_header(ws, ["node_id", "Ux", "Uy", "Rz"])
    _autosize(ws, [10, 14, 14, 14])


def _build_diagrams(wb: Workbook) -> None:
    wb.create_sheet("Diagrams")


def _build_instructions(wb: Workbook) -> None:
    ws = wb.create_sheet("Instructions", 0)
    ws.column_dimensions["A"].width = 100
    lines = [
        "2D Frame Analysis -- Instructions",
        "",
        "Units are not enforced -- use one consistent set throughout "
        "(e.g. N, m, Pa) across every sheet.",
        "",
        "Input sheets",
        "  Nodes        -- id, x, y",
        "  Members      -- id, node_i, node_j, E (modulus), A (area), I "
        "(moment of inertia), hinge_i/hinge_j (TRUE releases that end's "
        "moment connection, e.g. for truss bars)",
        "  Supports     -- node_id, type (Fixed / Pinned / Roller X / Roller Y)",
        "  NodalLoads   -- node_id, fx, fy, m (force/moment applied directly at a node)",
        "  PointLoads   -- member_id, position (distance from node_i), fx, fy, m, "
        "frame (local: along the member axis: global: along the X/Y axes)",
        "  UDLs         -- member_id, wx, wy (force per length), frame, "
        "start/end (distance from node_i; leave blank for the full member)",
        "",
        "Output sheets (filled in automatically when you run the analysis)",
        "  Reactions, Displacements -- numeric results per node",
        "  Diagrams                 -- geometry/load diagram, deformed shape, "
        "and per-member N/V/M diagrams",
        "",
        "Running the analysis",
        "  This workbook is paired with frame.py via xlwings. With the "
        "xlwings Excel add-in installed, click the xlwings ribbon tab's "
        "'Run main' button (or run `python frame.py` after editing it to "
        "call main() against this workbook) to solve the model and refresh "
        "the output sheets in place.",
        "",
        "The sample data already in the input sheets is a simply supported "
        "beam with a midspan point load -- replace it with your own model.",
    ]
    for row, text in enumerate(lines, start=1):
        ws.cell(row=row, column=1, value=text)
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    for row in (5, 14, 18):
        ws.cell(row=row, column=1).font = Font(bold=True)


def build_template(path: str) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    _build_instructions(wb)
    _build_nodes(wb)
    _build_members(wb)
    _build_supports(wb)
    _build_nodal_loads(wb)
    _build_point_loads(wb)
    _build_udls(wb)
    _build_reactions(wb)
    _build_displacements(wb)
    _build_diagrams(wb)
    wb.save(path)


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "frame_model.xlsx"
    build_template(out_path)
    print(f"Wrote {out_path}")
