"""Run the NI 8452 panel standalone: python -m instruments.panels.ni8452"""

from __future__ import annotations

from instruments.panels.ni8452.window import Ni8452Window
from instruments.panels.runtime import run_standalone_panel_app


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: Ni8452Window(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
