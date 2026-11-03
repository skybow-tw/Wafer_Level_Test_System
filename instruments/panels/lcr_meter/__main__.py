"""Run the LCR Meter panel standalone: python -m instruments.panels.lcr_meter"""

from __future__ import annotations

from instruments.panels.lcr_meter.window import LcrMeterWindow
from instruments.panels.runtime import run_standalone_panel_app


def main() -> int:
    return run_standalone_panel_app(
        lambda work_dir: LcrMeterWindow(work_dir=work_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
