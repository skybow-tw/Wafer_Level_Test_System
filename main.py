"""Wafer Map GUI entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from main_window import run_app, run_instrument_app
from instruments.panels.registry import FUNCTION_TEST_SPI_DAC_DISPLAY_NAME

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOG_DATEFMT = "%H:%M:%S"

# CLI flag -> instrument control window title
_INSTRUMENT_ONLY_FLAGS: tuple[tuple[str, str], ...] = (
    ("lcr", "LCR Meter"),
    ("bmt3000", "BMT3000"),
    ("bmt5000", "BMT5000"),
    ("dsa", "DSA"),
    ("roic", FUNCTION_TEST_SPI_DAC_DISPLAY_NAME),
)



def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for the wafer-level GUI entry point.

    Args:
        argv: Argument list without the program name (typically ``sys.argv[1:]``).

    Returns:
        Parsed namespace with flags such as ``info``, ``file``, ``lcr``,
        ``bmt3000``, ``bmt5000``, and ``dsa``.
    """
    parser = argparse.ArgumentParser(description="Wafer Level Inspection")
    parser.add_argument(
        "-info",
        action="store_true",
        help="輸出 INFO 層級 log（預設輸出到螢幕）",
    )
    parser.add_argument(
        "-file",
        action="store_true",
        help="將 log 寫入目前工作目錄的 log_日期時間 檔案（需搭配 -info）",
    )
    instrument_group = parser.add_mutually_exclusive_group()
    instrument_group.add_argument(
        "--lcr",
        action="store_true",
        help="僅開啟 LCR Meter 儀器控制視窗（略過導引與主畫面）",
    )
    instrument_group.add_argument(
        "--bmt3000",
        action="store_true",
        help="僅開啟 BMT3000 儀器控制視窗（略過導引與主畫面）",
    )
    instrument_group.add_argument(
        "--bmt5000",
        action="store_true",
        help="僅開啟 BMT5000 儀器控制視窗（略過導引與主畫面）",
    )
    instrument_group.add_argument(
        "--dsa",
        action="store_true",
        help="僅開啟 DSA 儀器控制視窗（略過導引與主畫面）",
    )
    instrument_group.add_argument(
        "-ROIC", "--roic",
        action="store_true",
        help="Open the Bolometer ASIC Function Test window directly.",
    )
    return parser.parse_args(argv)


def _selected_instrument_only(args: argparse.Namespace) -> str | None:
    """Return the instrument window title if an instrument-only flag is set.

    Args:
        args: Parsed CLI arguments from ``_parse_args``.

    Returns:
        Instrument display name (for example ``"BMT5000"``) when one of
        ``--lcr``, ``--bmt3000``, ``--bmt5000``, or ``--dsa`` is set;
        otherwise ``None``.
    """
    for flag, instrument_name in _INSTRUMENT_ONLY_FLAGS:
        if getattr(args, flag):
            return instrument_name
    return None


def _configure_logging(*, info: bool, to_file: bool) -> None:
    """Configure root logger for INFO output to console or a timestamped file.

    Does nothing when ``info`` is False.

    Args:
        info: If True, enable INFO-level logging on the root logger.
        to_file: If True, write logs to ``log_YYYYMMDD_HHMMSS.log`` in the
            current working directory; otherwise write to stderr/stdout via
            a stream handler.
    """
    if not info:
        return

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if to_file:
        log_name = f"log_{datetime.now():%Y%m%d_%H%M%S}.log"
        log_path = Path.cwd() / log_name
        handler: logging.Handler = logging.FileHandler(log_path, encoding="utf-8")
        print(f"INFO log 寫入: {log_path}", file=sys.stderr)
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(formatter)
    root.addHandler(handler)


def _app_work_dir() -> Path:
    """Directory for logs, settings, and datalog next to the app (or this file)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.file and not args.info:
        print("警告: -file 需搭配 -info 使用，已自動啟用 INFO log。", file=sys.stderr)
    _configure_logging(info=args.info or args.file, to_file=args.file)
    work_dir = _app_work_dir()
    instrument_name = _selected_instrument_only(args)
    if instrument_name is not None:
        return run_instrument_app(instrument_name, work_dir=work_dir)
    return run_app(work_dir=work_dir)


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except SystemExit:
        raise
    except Exception:
        if getattr(sys, "frozen", False):
            import traceback

            crash_path = Path(sys.executable).resolve().parent / "startup_error.log"
            crash_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
