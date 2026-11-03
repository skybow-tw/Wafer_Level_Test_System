"""Shared helpers for instrument panel windows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QPushButton, QWidget


def resolve_work_dir(window: QWidget, work_dir: Path | None) -> Path:
    if work_dir is not None:
        return work_dir
    parent = window.parent()
    if parent is not None:
        parent_work_dir = getattr(parent, "_work_dir", None)
        if isinstance(parent_work_dir, Path):
            return parent_work_dir
    return Path.cwd()


def mark_start_button(button: QPushButton) -> None:
    button.setProperty("btnRole", "start")
    repolish_widget(button)


def mark_primary_button(button: QPushButton) -> None:
    button.setProperty("btnRole", "primary")
    repolish_widget(button)


def mark_close_button(button: QPushButton) -> None:
    button.setProperty("btnRole", "close")
    repolish_widget(button)


def repolish_widget(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
