# 2D Structural Analysis in Excel

A 2D frame analysis engine (direct stiffness method) usable from Excel two
different ways:

- **[xlwings](https://www.xlwings.org/)** (`frame_model.xlsx` / `frame_model.py`)
  -- live COM automation. Needs a local Python install and the xlwings Excel
  add-in. Desktop Excel only (Windows/Mac), not iPad/web. See
  [Option A](#option-a-xlwings-live-excel-automation) below.
- **Python in Excel** (`frame_model_pyexcel.xlsx`) -- Microsoft's built-in,
  cloud-sandboxed `=PY()` formula feature. No install, no admin rights, no
  add-in -- the right choice on a locked-down corporate machine. Requires a
  qualifying Microsoft 365 plan and a one-time manual paste (see caveats).
  See [Option B](#option-b-python-in-excel-no-install) below.

Trusses and beams are just special cases of the general frame model (use
member end hinges for truss bars). Both options produce the same results --
reactions, displacements, and N/V/M/deflection diagrams.

## Package layout

- `structural2d/model.py` -- the data model: `FrameModel` (nodes, members,
  supports, loads).
- `structural2d/sections.py` -- the standard-section catalog (UK UB/UC steel
  sections) behind the Members sheet's section dropdown in both workbooks.
  Values are indicative -- verify against current section tables (SCI Blue
  Book) before design use.
- `structural2d/solver.py` -- the direct stiffness solver (`solve(model) ->
  FrameResults`).
- `structural2d/diagrams.py` -- closed-form N/V/M and deflection sampling
  along a member.
- `structural2d/plotting.py` -- matplotlib figures: geometry/loads, deformed
  shape, per-member N/V/M diagrams (`build_all_figures`).
- `structural2d/excel/build_template.py` -- scaffolds the input/output
  workbook (pure openpyxl, no Excel needed).
- `structural2d/excel/workbook_io.py` -- reads a `FrameModel` from the
  workbook's input sheets and writes results back. Has two adapters: an
  openpyxl one (headless, used by the test suite) and an xlwings one (live
  Excel automation, used by `frame_model.py`).
- `frame_model.py` -- the xlwings entry point. Lives at the repo root and
  must keep that exact base filename (`frame_model`) to pair with
  `frame_model.xlsx` -- this is the convention xlwings's "Run main" ribbon
  button uses to find the script for a given workbook.
- `frame_model.xlsx` -- the workbook itself, pre-populated with a sample
  simply-supported-beam model. Regenerate it any time with:

  ```
  python -m structural2d.excel.build_template frame_model.xlsx
  ```

- `structural2d/pyexcel/engine_solver.py` -- solver half for Python in Excel:
  direct stiffness math, no matplotlib. Paste into Engine!B2. Kept under
  Excel's hard 8,192-character per-cell limit (including the appended run()
  line), which is why the code is written so densely.
- `structural2d/pyexcel/engine_plotter.py` -- plotter half: matplotlib figures
  only, takes the solver cell's output. Paste into Engine!B4 (< 8,192 chars).
- `structural2d/excel/build_pyexcel_template.py` -- scaffolds
  `frame_model_pyexcel.xlsx`: real, named Excel Tables for the six input
  sheets, plus instructional placeholders on the output sheets (openpyxl
  cannot author working `=PY()` cells -- see Option B).
- `frame_model_pyexcel.xlsx` -- the Python-in-Excel workbook. Regenerate any
  time with:

  ```
  python -m structural2d.excel.build_pyexcel_template frame_model_pyexcel.xlsx
  ```

## Option A: xlwings (live Excel automation)

### Setup

```
pip install numpy matplotlib openpyxl xlwings
```

Then, in Excel, install the
[xlwings add-in](https://docs.xlwings.org/en/stable/addin.html) (the
`xlwings` Python package ships an Excel add-in; run `xlwings addin install`
or follow the linked docs for your platform).

> **Note on this repository's dev environment:** the code in this repo was
> written and tested in a headless Linux sandbox with no Excel installed.
> Everything that doesn't require Excel -- the solver, the diagrams, the
> openpyxl template builder, and the openpyxl-based read/write round trip --
> is covered by the automated tests and has been verified to work. The
> xlwings-specific code path (`read_model_xlwings`, `write_results_xlwings`,
> and `frame_model.py`'s `main()`) is written against the documented xlwings
> API but could not be executed here, since it requires a running Excel
> instance. It should be exercised against a real workbook before being
> relied on.

This path needs a local Python install, admin rights to register the COM
add-in, and desktop Excel (Windows/Mac -- not iPad, not Excel on the web). On
a locked-down corporate machine, all three of those can be blocked by IT
policy; if so, use Option B instead.

### Running an analysis

1. Open `frame_model.xlsx` in Excel.
2. Edit the input sheets (see below) to describe your structure.
3. On the xlwings ribbon tab, click **Run main**. This calls `main()` in
   `frame_model.py`, which reads the model, solves it, and writes the
   Reactions/Displacements tables and the Diagrams sheet back into the
   workbook in place.

Re-running after editing inputs is safe -- the output sheets are cleared
before each write, so results and diagram images don't accumulate.

## Option B: Python in Excel (no install)

[Python in Excel](https://support.microsoft.com/en-us/office/get-started-with-python-in-excel-a33fbcbe-065b-41d3-82cf-23d05397f53d)
is Microsoft's own `=PY()` formula feature: Python runs in a Microsoft-hosted
cloud sandbox, not on your machine, so there's nothing to install and no
admin rights needed. This is the option for a locked-down corporate laptop
where xlwings can't be installed.

**Requirements**
- A qualifying Microsoft 365 plan: Personal/Family, Business Standard/
  Premium, or Enterprise/Education E3/E5 on Current Channel. **Not**
  available on free or perpetual-license ("buy once") Office, and not on
  Excel for iPad/iPhone/Android.
- Excel for Windows, Mac, or the web.

**Why the workbook can't "just work" out of the box:** openpyxl can write
real Excel Tables (so `xl("Nodes")` etc. resolve correctly), but there is no
documented way to author the internal metadata a real `=PY()` formula cell
needs to execute -- that metadata lives in Excel's undocumented Rich Value
infrastructure and is tied to a live binding with Microsoft's cloud execution
sandbox, not just formula text. It's only created by Excel itself when you
use Insert Python interactively -- no file-format trick can fake it without
risking a corrupted workbook. So `frame_model_pyexcel.xlsx` ships with
working input tables, and the Engine tab's `B2`/`B4` cells are left empty for
a one-time Insert Python. To make that one-time step as close to zero-effort
as possible, the *exact* code to paste (source + the trailing `run()` call,
already combined) is pre-staged in cells `D2`/`D4` of the same sheet -- so
there's no need to have any project file open at all; everything is already
inside the workbook. This is a one-time cost: once done and saved, the
`.xlsx` carries the code with it.

**One-time setup**

> The engine is split across two cells to stay within Excel's 8,192-character
> per-cell limit. Cell `B2` holds the solver (math only); cell `B4` holds the
> plotter (matplotlib). The ready-to-paste text for each is staged in `D2`
> and `D4`.

1. Open `frame_model_pyexcel.xlsx`. Fill in your structure on the Nodes /
   Members / Supports / NodalLoads / PointLoads / UDLs tabs (replace the
   sample simply-supported-beam data).

**Solver cell (Engine!B2)**

2. Go to the `Engine` tab. Click cell `D2` once (a single click selects the
   whole cell -- no need to select the text inside it), then Ctrl+C.
3. Click cell `B2`. Formulas tab -> Insert Python.
4. Ctrl+V to paste, then Ctrl+Enter to run it. Leave this cell's output as a
   Python object (not "Excel Value") -- the plotter cell reads the object
   directly.

**Plotter cell (Engine!B4)**

5. Click cell `D4` once, then Ctrl+C.
6. Click cell `B4`. Formulas tab -> Insert Python.
7. Ctrl+V to paste, then Ctrl+Enter to run it. Leave this cell's output as a
   Python object too.

**Output cells**

8. `Reactions` tab, cell `A1`: Insert Python, type `xl("Engine!B2")["reactions"]`,
   then switch that cell's output to Excel Value so it spills as a table.
9. `Displacements` tab, cell `A1`: same, with `["displacements"]`.
10. `Summary` tab, cell `A1`: same, with `["summary"]` -- per-member max
    |N|, |V|, |M|, |deflection|.
11. `Diagrams` tab: `B2` -> `xl("Engine!B4")["geometry_fig"]`,
    `B20` -> `xl("Engine!B4")["deformed_fig"]`. For a member's N/V/M diagram,
    put its id in `B39` and in `B40` use
    `xl("Engine!B4")["member_fig"](xl("B39"))`. Figures display as images
    automatically.
12. Save. If you like, you can now delete the staged text in `D2`/`D4` --
    `B2`/`B4` no longer need it once they've run once.

**Day to day after setup:** edit the input tabs and press Ctrl+Alt+F9
(recalculate) -- everything downstream updates automatically. No re-pasting.

**Sharing this workbook:** the Python code is saved inside the cells as part
of the `.xlsx`, so emailing/sharing it after setup does carry the code over.
Two real caveats: (a) whoever opens it also needs a qualifying Microsoft 365
plan, per Requirements above; (b) a workbook that arrives by email/download
opens in Protected View first, same as a macro-enabled file -- Python
formulas won't run until the recipient clicks "Enable Editing."

> **Caveat:** `engine_solver.py` and `engine_plotter.py` are validated against
> the same closed-form test cases as the rest of this project (see
> `tests/test_pyexcel_split_engine.py`), entirely headlessly with pandas
> DataFrames standing in for `xl(...)` results -- including a test that
> executes the *exact* staged text from `D2`/`D4` (not just the source
> files) to make sure what actually gets pasted works. The cross-cell steps
> above -- referencing another cell's returned Python object via
> `xl("Engine!B2")`, and a matplotlib Figure rendering as an image when
> returned that way -- follow Microsoft's documented Python-in-Excel pattern
> but could not be exercised in real Excel, since there's no Excel available
> in this environment. Exercise them once against a real workbook before
> relying on this for anything important.

Units are not enforced in either option -- pick one consistent set (e.g. N,
m, Pa) and use it across every sheet.

## Input sheets

| Sheet | Columns | Notes |
|---|---|---|
| `Nodes` | `id, x, y` | |
| `Members` | `id, node_i, node_j, section, E, A, I, hinge_i, hinge_j` | EITHER pick a `section` from the dropdown and leave `E`/`A`/`I` blank (properties come from the Sections sheet), OR leave `section` blank and type `E` (modulus), `A` (area), `I` (moment of inertia) yourself. Typed values win over the section pick. `hinge_i`/`hinge_j` (`TRUE`/`FALSE`) release that end's moment connection -- set both `TRUE` for a truss bar. |
| `Sections` | `name, E, A, I` | The catalog behind the Members dropdown. Ships with common UK UB/UC steel sections (SI units, E=210 GPa, major-axis I; indicative values -- verify for design use). Add rows for your own sections. |
| `Supports` | `node_id, type` | `type` is one of `Fixed`, `Pinned`, `Roller X`, `Roller Y`. |
| `NodalLoads` | `node_id, fx, fy, m` | Force/moment applied directly at a node. |
| `PointLoads` | `member_id, position, fx, fy, m, frame` | `position` is measured from `node_i`. `frame` is `local` (along the member axis) or `global` (along X/Y). |
| `UDLs` | `member_id, wx, wy, frame, start, end` | Force-per-length. `start`/`end` (measured from `node_i`) may be left blank to cover the full member. |

Typos are caught early with readable messages: unknown node/member/section
references, load positions outside a member, and missing supports all raise
a plain-English error instead of a bare `KeyError`.

## Output sheets

| Sheet | Contents |
|---|---|
| `Reactions` | `node_id, Rx, Ry, Rm` for each supported node. |
| `Displacements` | `node_id, Ux, Uy, Rz` for every node. |
| `Summary` | Per-member envelope: max \|N\|, \|V\|, \|M\|, and \|local deflection\|. |
| `Diagrams` | Embedded matplotlib images: geometry/load diagram, deformed shape, and one N/V/M diagram per member. |

## Tests

```
python -m pytest tests/
```

`tests/test_solver.py` checks the engine against textbook closed-form
solutions (simply supported beams, cantilevers, portal frames, trusses).
`tests/test_workbook_io.py` round-trips the openpyxl template builder and
read/write adapters end-to-end (build → read → solve → write → reload),
including the section-dropdown lookup and the Summary sheet.
`tests/test_pyexcel_split_engine.py` checks the two-cell split
(`engine_solver.py` + `engine_plotter.py`) using pandas DataFrames in
place of `xl(...)` results -- the one thing it can't cover is real Excel
itself (see the caveat under Option B).
