"""Entry point for the LCR Meter executable (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if not getattr(sys, "frozen", False):
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    from instruments.panels.lcr_meter.window import LcrMeterWindow
    from instruments.panels.runtime import run_standalone_panel_app

    return run_standalone_panel_app(
        lambda work_dir: LcrMeterWindow(work_dir=work_dir),
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        if getattr(sys, "frozen", False):
            import traceback

            crash_path = Path(sys.executable).resolve().parent / "startup_error.log"
            crash_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
