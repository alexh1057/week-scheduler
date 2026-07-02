"""Scaffolds the workbook for the "Insert Python" (Microsoft's cloud-sandboxed
Python in Excel) variant of the 2D frame analysis tool -- the alternative to
build_template.py/frame.py's xlwings flow for machines where installing the
xlwings Excel add-in isn't possible (e.g. locked-down corporate laptops).

Pure openpyxl, so it's testable headlessly. Unlike the xlwings template,
this one cannot be made to run out of the box: there is no documented way
for openpyxl (or anything short of a live, licensed Excel session) to author
the proprietary cell metadata Excel's Python-in-Excel feature needs for a
"=PY(...)" formula to actually execute -- that metadata lives in Excel's
undocumented Rich Value infrastructure and is tied to a live binding with
Microsoft's cloud execution sandbox, not just formula text. So the six input
sheets are real, usable Excel Tables (named to match the xl("...") calls the
pasted code uses), and the two Engine cells (B2/B4) are left empty for a
one-time manual "Insert Python" + paste -- but to make that paste itself as
close to zero-effort as possible, the exact ready-to-paste code (source +
the trailing run() call, all in one string) is staged in cells D2/D4 of the
Engine sheet, generated from engine_solver.py/engine_plotter.py at build
time. So setup is: click the staging cell, Ctrl+C, click B2/B4, Insert
Python, Ctrl+V, Ctrl+Enter -- no other files need to be open.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from ..sections import SECTION_HEADERS, SECTIONS

SUPPORT_TYPES = ["Fixed", "Pinned", "Roller X", "Roller Y"]
LOAD_FRAMES = ["local", "global"]
BOOL_CHOICES = ["TRUE", "FALSE"]

# Rows the section-name dropdown scans on the Sections sheet: the built-in
# catalog plus headroom for user-added sections.
SECTION_DROPDOWN_ROWS = 100

_PYEXCEL_DIR = Path(__file__).resolve().parent.parent / "pyexcel"
_SOLVER_RUN_LINE = (
    '_r=run(xl("Nodes"),xl("Members"),xl("Supports"),xl("NodalLoads"),'
    'xl("PointLoads"),xl("UDLs"),xl("Sections"));_r'
)
_PLOTTER_RUN_LINE = '_r=run(xl("Engine!B2"));_r'


def _solver_paste_text() -> str:
    """engine_solver.py's source with the run() call appended -- exactly
    what the user should paste into Engine!B2, as a single string."""
    source = (_PYEXCEL_DIR / "engine_solver.py").read_text().rstrip("\n")
    return f"{source}\n{_SOLVER_RUN_LINE}"


def _plotter_paste_text() -> str:
    """engine_plotter.py's source with the run() call appended -- exactly
    what the user should paste into Engine!B4, as a single string."""
    source = (_PYEXCEL_DIR / "engine_plotter.py").read_text().rstrip("\n")
    return f"{source}\n{_PLOTTER_RUN_LINE}"


def _add_table(ws: Worksheet, name: str, headers: list[str], rows: list[list] | None, blank_rows: int = 0) -> None:
    """Write headers + rows, wrap them in a named Excel Table (so xl("name")
    works), and freeze the header row. Excel Tables need at least one data
    row to be valid, so callers with no sample data pass blank_rows=1."""
    ws.append(headers)
    for row in rows or []:
        ws.append(row)
    for _ in range(blank_rows):
        ws.append([None] * len(headers))
    ws.freeze_panes = "A2"

    n_rows = 1 + len(rows or []) + blank_rows
    last_col = ws.cell(row=1, column=len(headers)).column_letter
    table = Table(displayName=name, ref=f"A1:{last_col}{n_rows}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
    ws.add_table(table)
    for col, width in zip(range(1, len(headers) + 1), [max(12, len(h) + 4) for h in headers]):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width


def _add_list_validation(ws: Worksheet, col_letter: str, choices: list[str], n_rows: int = 200) -> None:
    dv = DataValidation(type="list", formula1=f'"{",".join(choices)}"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}2:{col_letter}{n_rows + 1}")


def _build_nodes(wb: Workbook) -> None:
    ws = wb.create_sheet("Nodes")
    _add_table(ws, "Nodes", ["id", "x", "y"], [["1", 0.0, 0.0], ["2", 6.0, 0.0]])


def _build_members(wb: Workbook) -> None:
    ws = wb.create_sheet("Members")
    _add_table(ws, "Members", ["id", "node_i", "node_j", "section", "E", "A", "I", "hinge_i", "hinge_j"],
               [["m1", "1", "2", None, 200e9, 0.01, 8e-5, "FALSE", "FALSE"]])
    dv = DataValidation(type="list", formula1="=SectionNames", allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("D2:D201")
    _add_list_validation(ws, "H", BOOL_CHOICES)
    _add_list_validation(ws, "I", BOOL_CHOICES)


def _build_sections(wb: Workbook) -> None:
    ws = wb.create_sheet("Sections")
    _add_table(ws, "Sections", SECTION_HEADERS, [list(row) for row in SECTIONS])
    ws["F1"] = (
        "UK UB/UC sections, major-axis I, steel E=210e9 (SI units: Pa, m2, m4). "
        "Indicative values -- verify against current section tables for design "
        "use. Add your own rows; the Members dropdown picks them up."
    )
    ws.column_dimensions["F"].width = 110


def _build_supports(wb: Workbook) -> None:
    ws = wb.create_sheet("Supports")
    _add_table(ws, "Supports", ["node_id", "type"], [["1", "Pinned"], ["2", "Roller Y"]])
    _add_list_validation(ws, "B", SUPPORT_TYPES)


def _build_nodal_loads(wb: Workbook) -> None:
    ws = wb.create_sheet("NodalLoads")
    _add_table(ws, "NodalLoads", ["node_id", "fx", "fy", "m"], [], blank_rows=1)


def _build_point_loads(wb: Workbook) -> None:
    ws = wb.create_sheet("PointLoads")
    _add_table(ws, "PointLoads", ["member_id", "position", "fx", "fy", "m", "frame"],
               [["m1", 3.0, 0.0, -10000.0, 0.0, "local"]])
    _add_list_validation(ws, "F", LOAD_FRAMES)


def _build_udls(wb: Workbook) -> None:
    ws = wb.create_sheet("UDLs")
    _add_table(ws, "UDLs", ["member_id", "wx", "wy", "frame", "start", "end"], [], blank_rows=1)
    _add_list_validation(ws, "D", LOAD_FRAMES)


def _build_engine(wb: Workbook) -> None:
    ws = wb.create_sheet("Engine")
    ws.column_dimensions["A"].width = 90
    ws.column_dimensions["D"].width = 40
    ws["A1"] = "Cell B2 (solver): click cell D2, Ctrl+C to copy it, then click B2, Formulas -> Insert Python, Ctrl+V, Ctrl+Enter."
    ws["A3"] = "Cell B4 (plotter): click cell D4, Ctrl+C to copy it, then click B4, Formulas -> Insert Python, Ctrl+V, Ctrl+Enter."
    ws["A1"].font = Font(bold=True)
    ws["A3"].font = Font(bold=True)
    ws["C1"] = "Ready-to-paste solver code (click D2 once, then Ctrl+C -- copies the whole cell, no need to select text):"
    ws["C3"] = "Ready-to-paste plotter code (click D4 once, then Ctrl+C):"
    ws["D2"] = _solver_paste_text()
    ws["D4"] = _plotter_paste_text()


def _build_reactions(wb: Workbook) -> None:
    ws = wb.create_sheet("Reactions")
    ws.column_dimensions["A"].width = 90
    ws["A1"] = 'One-time setup: click A1, Insert Python, type: xl("Engine!B2")["reactions"]  -- then set this cell\'s output to Excel Value (see Instructions).'
    ws["A1"].font = Font(bold=True)


def _build_displacements(wb: Workbook) -> None:
    ws = wb.create_sheet("Displacements")
    ws.column_dimensions["A"].width = 90
    ws["A1"] = 'One-time setup: click A1, Insert Python, type: xl("Engine!B2")["displacements"]  -- then set this cell\'s output to Excel Value.'
    ws["A1"].font = Font(bold=True)


def _build_summary(wb: Workbook) -> None:
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 90
    ws["A1"] = 'One-time setup: click A1, Insert Python, type: xl("Engine!B2")["summary"]  -- then set this cell\'s output to Excel Value. Gives per-member max |N|, |V|, |M|, |deflection|.'
    ws["A1"].font = Font(bold=True)


def _build_diagrams(wb: Workbook) -> None:
    ws = wb.create_sheet("Diagrams")
    ws.column_dimensions["A"].width = 90
    ws["A1"] = 'One-time setup, geometry diagram: click B2, Insert Python, type: xl("Engine!B4")["geometry_fig"]'
    ws["A2"] = 'Deformed shape: click B20, Insert Python, type: xl("Engine!B4")["deformed_fig"]'
    ws["A3"] = 'Per-member N/V/M: put a member id (e.g. m1) in B39, then in B40, Insert Python: xl("Engine!B4")["member_fig"](xl("B39"))'
    ws["A1"].font = ws["A2"].font = ws["A3"].font = Font(bold=True)


def _build_instructions(wb: Workbook) -> None:
    ws = wb.create_sheet("Instructions", 0)
    ws.column_dimensions["A"].width = 100
    lines = [
        "2D Frame Analysis (Python in Excel edition) -- Instructions",
        "",
        "This is the no-install alternative to frame.py/frame_model.xlsx's xlwings "
        "flow, for machines where installing the xlwings Excel add-in isn't possible "
        "(e.g. a locked-down corporate laptop). It uses Excel's built-in 'Insert "
        "Python' feature instead -- no Python install, no add-in, no admin rights.",
        "",
        "Requirements",
        "  - A Microsoft 365 plan with Python in Excel enabled (Personal/Family, "
        "Business Standard/Premium, or Enterprise/Education E3/E5 -- NOT free or "
        "perpetual-license Office). Not available on Excel for iPad/iPhone/Android.",
        "  - Excel for Windows, Mac, or the web, Current Channel.",
        "",
        "One-time setup (do this once, then save -- the code is stored in the "
        "workbook from then on). Nothing outside this workbook needs to be open --"
        " the exact code to paste is already staged in cells D2/D4 of the Engine tab.",
        "  1. Fill in your structure on the Nodes/Members/Supports/NodalLoads/"
        "PointLoads/UDLs tabs (sample data is a simply supported beam -- replace it).",
        "  ---- Solver cell (Engine!B2) ----",
        "  2. Go to the Engine tab. Click cell D2 once (a single click selects the "
        "whole cell -- you don't need to select the text inside it), then Ctrl+C.",
        "  3. Click cell B2. Formulas tab -> Insert Python.",
        "  4. Ctrl+V to paste, then Ctrl+Enter to run it. Leave this cell's Python "
        "output as a Python object (not Excel Value) -- the plotter cell reads the "
        "object itself.",
        "  ---- Plotter cell (Engine!B4) ----",
        "  5. Click cell D4 once, then Ctrl+C.",
        "  6. Click cell B4. Formulas tab -> Insert Python.",
        "  7. Ctrl+V to paste, then Ctrl+Enter to run it. Leave this cell's output "
        "as a Python object too.",
        "  ---- Output cells ----",
        "  8. Reactions tab, cell A1: Insert Python, type:",
        '        xl("Engine!B2")["reactions"]',
        "      then switch that cell's output to Excel Value so it spills as a table.",
        "  9. Displacements tab, cell A1: same, with [\"displacements\"] instead.",
        "  10. Summary tab, cell A1: same, with [\"summary\"] -- per-member max "
        "|N|, |V|, |M|, |deflection|.",
        "  11. Diagrams tab: B2 -> xl(\"Engine!B4\")[\"geometry_fig\"], "
        "B20 -> xl(\"Engine!B4\")[\"deformed_fig\"]. For a member's N/V/M diagram, "
        "put its id in B39 and in B40 use xl(\"Engine!B4\")[\"member_fig\"](xl(\"B39\")). "
        "Figures display as images automatically.",
        "  12. Save the workbook. If you like, delete the staged code in D2/D4 "
        "afterwards -- B2/B4 no longer need them once they've run once.",
        "",
        "Day to day after setup",
        "  Edit the input tabs and press Ctrl+Alt+F9 (recalculate) -- everything "
        "downstream of the Engine cell updates automatically. No re-pasting needed.",
        "",
        "Sharing this workbook",
        "  The Python code is saved inside the cells as part of the .xlsx, so "
        "emailing/sharing the file after the one-time setup does carry it over. Two "
        "real caveats: (a) whoever opens it also needs a qualifying Microsoft 365 "
        "plan, per Requirements above; (b) a workbook that arrives by email/download "
        "gets opened in Protected View first, same as a macro-enabled file -- Python "
        "formulas won't run until they click 'Enable Editing'.",
        "",
        "Caveat",
        "  engine_solver.py and engine_plotter.py are validated against the same "
        "closed-form test cases as the rest of this project (see "
        "tests/test_pyexcel_split_engine.py); the code staged in D2/D4 is generated "
        "from those same files at build time, so it's always in sync. The cross-cell "
        "steps above -- referencing another cell's returned Python object via "
        "xl(\"Engine!B2\"), and a matplotlib Figure rendering as an image when "
        "returned that way -- follow Microsoft's documented Python-in-Excel pattern "
        "but could not be exercised in real Excel here (no Excel in this "
        "environment). There is also no documented way to author a working "
        "Insert-Python cell without a live Excel session -- that's why D2/D4 are "
        "staged text to copy-paste rather than B2/B4 already working on open.",
        "",
        "Input sheets (same column meanings as the xlwings version)",
        "  Nodes        -- id, x, y",
        "  Members      -- id, node_i, node_j, section, E, A, I, hinge_i/hinge_j. "
        "EITHER pick a section from the dropdown and leave E/A/I blank (properties "
        "come from the Sections sheet), OR leave section blank and type E "
        "(modulus), A (area), I (moment of inertia) yourself. hinge_i/hinge_j "
        "TRUE releases that end's moment connection, e.g. for truss bars.",
        "  Sections     -- name, E, A, I: the catalog behind the Members dropdown. "
        "Ships with common UK UB/UC steel sections (SI units, indicative values -- "
        "verify for design use). Add rows for your own sections.",
        "  Supports     -- node_id, type (Fixed / Pinned / Roller X / Roller Y)",
        "  NodalLoads   -- node_id, fx, fy, m (force/moment applied directly at a node)",
        "  PointLoads   -- member_id, position (distance from node_i), fx, fy, m, "
        "frame (local: along the member axis; global: along the X/Y axes)",
        "  UDLs         -- member_id, wx, wy (force per length), frame, "
        "start/end (distance from node_i; leave blank for the full member)",
        "",
        "Units are not enforced -- use one consistent set throughout "
        "(e.g. N, m, Pa) across every sheet.",
    ]
    for row, text in enumerate(lines, start=1):
        ws.cell(row=row, column=1, value=text)
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    for row, text in enumerate(lines, start=1):
        if text in ("Requirements", "One-time setup (do this once, then save -- the code is stored in the "
                     "workbook from then on)", "Day to day after setup", "Sharing this workbook", "Caveat",
                     "Input sheets (same column meanings as the xlwings version)"):
            ws.cell(row=row, column=1).font = Font(bold=True)


def build_pyexcel_template(path: str) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    _build_instructions(wb)
    _build_nodes(wb)
    _build_members(wb)
    _build_sections(wb)
    _build_supports(wb)
    _build_nodal_loads(wb)
    _build_point_loads(wb)
    _build_udls(wb)
    _build_engine(wb)
    _build_reactions(wb)
    _build_displacements(wb)
    _build_summary(wb)
    _build_diagrams(wb)
    wb.defined_names.add(
        DefinedName("SectionNames", attr_text=f"Sections!$A$2:$A${SECTION_DROPDOWN_ROWS + 1}")
    )
    wb.save(path)


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "frame_model_pyexcel.xlsx"
    build_pyexcel_template(out_path)
    print(f"Wrote {out_path}")
