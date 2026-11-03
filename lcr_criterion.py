"""LCR die judgment criteria for virtual and real instruments."""

from __future__ import annotations

GOOD_DIE_BIN = 0
BAD_DIE_BIN = 1


def judge_virtual_lcr_die(
    x_values: list[float],
    y_values: list[float],
) -> int:
    """Return wafer-map bin for a virtual LCR measurement.

    Placeholder: always Good until a formula is defined.
    """
    del x_values, y_values
    return GOOD_DIE_BIN


def judge_real_lcr_die(
    x_values: list[float],
    y_values: list[float],
) -> int:
    """Return wafer-map bin for a real LCR meter measurement.

    Placeholder: always Good until a formula is defined.
    """
    del x_values, y_values
    return GOOD_DIE_BIN
