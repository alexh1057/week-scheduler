# 2D Structural Analysis in Excel

A 2D frame analysis engine (direct stiffness method) driven from an Excel
workbook via [xlwings](https://www.xlwings.org/). Trusses and beams are just
special cases of the general frame model (use member end hinges for truss
bars). Results -- reactions, displacements, and N/V/M/deflection diagrams --
are written back into the workbook.

## Package layout

- `structural2d/model.py` -- the data model: `FrameModel` (nodes, members,
  supports, loads).
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

## Setup

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

## Running an analysis

1. Open `frame_model.xlsx` in Excel.
2. Edit the input sheets (see below) to describe your structure.
3. On the xlwings ribbon tab, click **Run main**. This calls `main()` in
   `frame_model.py`, which reads the model, solves it, and writes the
   Reactions/Displacements tables and the Diagrams sheet back into the
   workbook in place.

Re-running after editing inputs is safe -- the output sheets are cleared
before each write, so results and diagram images don't accumulate.

Units are not enforced -- pick one consistent set (e.g. N, m, Pa) and use it
across every sheet.

## Input sheets

| Sheet | Columns | Notes |
|---|---|---|
| `Nodes` | `id, x, y` | |
| `Members` | `id, node_i, node_j, E, A, I, hinge_i, hinge_j` | `E` modulus, `A` area, `I` moment of inertia. `hinge_i`/`hinge_j` (`TRUE`/`FALSE`) release that end's moment connection -- set both `TRUE` for a truss bar. |
| `Supports` | `node_id, type` | `type` is one of `Fixed`, `Pinned`, `Roller X`, `Roller Y`. |
| `NodalLoads` | `node_id, fx, fy, m` | Force/moment applied directly at a node. |
| `PointLoads` | `member_id, position, fx, fy, m, frame` | `position` is measured from `node_i`. `frame` is `local` (along the member axis) or `global` (along X/Y). |
| `UDLs` | `member_id, wx, wy, frame, start, end` | Force-per-length. `start`/`end` (measured from `node_i`) may be left blank to cover the full member. |

## Output sheets

| Sheet | Contents |
|---|---|
| `Reactions` | `node_id, Rx, Ry, Rm` for each supported node. |
| `Displacements` | `node_id, Ux, Uy, Rz` for every node. |
| `Diagrams` | Embedded matplotlib images: geometry/load diagram, deformed shape, and one N/V/M diagram per member. |

## Tests

```
python -m pytest tests/
```

`tests/test_solver.py` checks the engine against textbook closed-form
solutions (simply supported beams, cantilevers, portal frames, trusses).
`tests/test_workbook_io.py` round-trips the openpyxl template builder and
read/write adapters end-to-end (build → read → solve → write → reload).
