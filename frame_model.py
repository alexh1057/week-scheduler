"""xlwings entry point paired with frame_model.xlsx (same base filename, same
folder -- the convention xlwings's "Run main" ribbon button looks for).

With the xlwings Excel add-in installed, open frame_model.xlsx and click
"Run main" on the xlwings ribbon tab: it reads the model from the input
sheets, solves it, and writes the Reactions/Displacements tables plus the
geometry/deformed-shape/N-V-M diagrams back into the workbook in place.

This module requires the `xlwings` package and a running Excel instance,
neither of which is available in this sandbox -- it has been written
against the documented xlwings API but could not be executed/tested here.
"""
from __future__ import annotations

import xlwings as xw

from structural2d.excel.workbook_io import read_model_xlwings, write_results_xlwings
from structural2d.solver import solve


def main():
    book = xw.Book.caller()
    model = read_model_xlwings(book)
    results = solve(model)
    write_results_xlwings(book, model, results)


if __name__ == "__main__":
    xw.Book("frame_model.xlsx").set_mock_caller()
    main()
