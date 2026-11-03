"""Run the DSA panel standalone: python -m instruments.panels.dsa"""

from __future__ import annotations

from instruments.panels.dsa.window import DsaWindow
from instruments.panels.runtime import run_standalone_panel_app


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: DsaWindow(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
