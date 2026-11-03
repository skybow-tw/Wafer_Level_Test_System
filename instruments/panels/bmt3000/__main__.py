"""Run the BMT3000 panel standalone: python -m instruments.panels.bmt3000"""

from __future__ import annotations

from instruments.panels.bmt3000.window import Bmt3000Window
from instruments.panels.runtime import run_standalone_panel_app


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: Bmt3000Window(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
