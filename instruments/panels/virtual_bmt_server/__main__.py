"""Run the virtual BMT TCP server: python -m instruments.panels.virtual_bmt_server"""

from __future__ import annotations

from instruments.panels.runtime import run_standalone_panel_app
from instruments.panels.virtual_bmt_server.window import VirtualBmtServerWindow


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: VirtualBmtServerWindow(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
