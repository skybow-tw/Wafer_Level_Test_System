"""Extract inspection targets from loaded wafer map data."""

from __future__ import annotations

from dataclasses import dataclass

from excel_loader import WaferMapData

INSPECTION_BIN_VALUE = 10


@dataclass(frozen=True)
class DieCoordinate:
    x: int
    y: int


@dataclass(frozen=True)
class InspectionTargetList:
    targets: tuple[DieCoordinate, ...]

    @property
    def count(self) -> int:
        return len(self.targets)


def extract_inspection_targets(
    data: WaferMapData,
    bin_value: int = INSPECTION_BIN_VALUE,
) -> InspectionTargetList:
    """Return dies with the given bin value, ordered row by row (Y then X)."""
    targets = [
        DieCoordinate(x=x, y=y)
        for (x, y), value in data.grid.items()
        if value == bin_value
    ]
    targets.sort(key=lambda coord: (coord.y, coord.x))
    return InspectionTargetList(targets=tuple(targets))
