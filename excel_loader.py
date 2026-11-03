"""Load and save wafer map grid data from Excel files."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException


@dataclass
class WaferMapData:
    x_labels: list[str]
    y_labels: list[str]
    grid: dict[tuple[int, int], int]
    x_index: int | None = None
    y_index: int | None = None

    @property
    def width(self) -> int:
        return len(self.x_labels)

    @property
    def height(self) -> int:
        return len(self.y_labels)

    @property
    def die_count(self) -> int:
        return sum(1 for v in self.grid.values() if v != 11)


def load_wafer_map_xlsx(path: str | Path) -> WaferMapData:
    """Parse wafer map Excel.

    Row 1 col C = X index step, row 2 col C = Y index step (die spacing).
    Row 3 = X headers, column A from row 4 = Y labels.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    x_index = _to_int(ws.cell(1, 3).value)
    y_index = _to_int(ws.cell(2, 3).value)

    header_row = next(ws.iter_rows(min_row=3, max_row=3, values_only=True))
    x_labels = [str(v) for v in header_row[1:] if v is not None]

    y_labels: list[str] = []
    grid: dict[tuple[int, int], int] = {}

    for row_idx, row in enumerate(ws.iter_rows(min_row=4, values_only=True)):
        if not row or row[0] is None:
            continue
        y_labels.append(str(row[0]))
        for col_idx, value in enumerate(row[1 : 1 + len(x_labels)]):
            if value is None:
                continue
            grid[(col_idx, row_idx)] = int(value)

    return WaferMapData(
        x_labels=x_labels,
        y_labels=y_labels,
        grid=grid,
        x_index=x_index,
        y_index=y_index,
    )


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_workbook_compat(path: str | Path, *, data_only: bool = False):
    """Load an Excel workbook; supports .xlsx content saved with a .xls extension."""
    file_path = Path(path)
    try:
        return openpyxl.load_workbook(file_path, data_only=data_only)
    except InvalidFileException:
        return openpyxl.load_workbook(
            BytesIO(file_path.read_bytes()),
            data_only=data_only,
        )


def save_wafer_map_report(
    source_path: str | Path,
    data: WaferMapData,
    output_path: str | Path,
) -> Path:
    """Copy the loaded wafer map workbook and write updated grid values."""
    source = Path(source_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)

    wb = load_workbook_compat(output)
    ws = wb.active
    for (col_idx, row_idx), value in data.grid.items():
        ws.cell(row=row_idx + 4, column=col_idx + 2, value=value)
    wb.save(output)
    return output
