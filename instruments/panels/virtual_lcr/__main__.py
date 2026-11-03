"""Run the virtual LCR panel standalone: python -m instruments.panels.virtual_lcr"""

from __future__ import annotations

from pathlib import Path

from instruments.panels.runtime import run_standalone_panel_app
from instruments.panels.virtual_lcr.window import VirtualLcrWindow


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: VirtualLcrWindow(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
