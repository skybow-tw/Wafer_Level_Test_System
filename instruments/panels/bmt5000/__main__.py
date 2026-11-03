"""Run the BMT5000 panel standalone: python -m instruments.panels.bmt5000"""

from __future__ import annotations

from instruments.panels.bmt5000.window import Bmt5000Window
from instruments.panels.runtime import run_standalone_panel_app


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: Bmt5000Window(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
