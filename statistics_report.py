"""Create and append instrument-specific per-die statistics workbooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl import Workbook

from excel_loader import load_workbook_compat

STATISTICS_REPORT_FILENAME = "00_統計資料.xlsx"

VIRTUAL_LCR_DEFAULT_CO = 0.0
VIRTUAL_LCR_DEFAULT_VP = -1.0
VIRTUAL_LCR_DEFAULT_DELTA_C = 0.0


@dataclass(frozen=True)
class LcrDieSummary:
    co: float | None
    vp: float | None
    delta_c: float | None


def virtual_lcr_default_summary() -> LcrDieSummary:
    return LcrDieSummary(
        co=VIRTUAL_LCR_DEFAULT_CO,
        vp=VIRTUAL_LCR_DEFAULT_VP,
        delta_c=VIRTUAL_LCR_DEFAULT_DELTA_C,
    )


def _report_path(session_dir: Path) -> Path:
    return session_dir / STATISTICS_REPORT_FILENAME


def init_lcr_statistics_report(session_dir: Path) -> Path:
    """Create the LCR variant of the per-die statistics workbook."""
    return init_statistics_report(session_dir, ("X", "Y", "Co", "Vp", "deltaC"))


def init_statistics_report(session_dir: Path, headers: tuple[str, ...]) -> Path:
    """Create a fresh workbook whose first two columns are die coordinates."""
    path = _report_path(session_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Statistics"
    ws.append(list(headers))
    wb.save(path)
    return path


def append_lcr_statistics_row(
    session_dir: Path,
    die_x: int,
    die_y: int,
    summary: LcrDieSummary,
) -> Path:
    """Append one die row to the statistics report."""
    path = append_statistics_row(
        session_dir, die_x, die_y, (summary.co, summary.vp, summary.delta_c)
    )
    wb = load_workbook_compat(path)
    ws = wb.active
    if summary.vp is not None:
        ws.cell(row=ws.max_row, column=4).number_format = "0.00"
    wb.save(path)
    return path


def append_statistics_row(
    session_dir: Path,
    die_x: int,
    die_y: int,
    values: tuple[float | int | None, ...],
) -> Path:
    """Append a coordinate-prefixed row to an already initialized report."""
    path = _report_path(session_dir)
    if not path.exists():
        raise FileNotFoundError("Statistics report has not been initialized.")
    wb = load_workbook_compat(path)
    ws = wb.active
    ws.append([die_x, die_y, *values])
    wb.save(path)
    return path
