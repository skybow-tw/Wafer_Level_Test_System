"""Shared manual-save parameters used by the main window and instrument panels."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from datalog import (
    DEFAULT_SAVE_EXTENSION,
    build_save_filename,
    resolve_save_dir,
    resolve_save_path,
)


@dataclass(frozen=True)
class SaveParams:
    folder_name: str = ""
    prefix: str = ""
    x: int = 1
    y: int = 1
    suffix: str = ""

    def output_dir(self, work_dir: Path) -> Path:
        return resolve_save_dir(work_dir, self.folder_name)

    def filename(
        self,
        *,
        x: int | None = None,
        y: int | None = None,
        tag: str = "",
        extension: str = DEFAULT_SAVE_EXTENSION,
    ) -> str:
        return build_save_filename(
            prefix=self.prefix,
            x=self.x if x is None else x,
            y=self.y if y is None else y,
            suffix=self.suffix,
            tag=tag,
            extension=extension,
        )

    def output_path(
        self,
        work_dir: Path,
        *,
        x: int | None = None,
        y: int | None = None,
        tag: str = "",
        extension: str = DEFAULT_SAVE_EXTENSION,
    ) -> Path:
        return resolve_save_path(
            work_dir,
            folder_name=self.folder_name,
            prefix=self.prefix,
            x=self.x if x is None else x,
            y=self.y if y is None else y,
            suffix=self.suffix,
            tag=tag,
            extension=extension,
        )


_current = SaveParams()


def get_save_params() -> SaveParams:
    return _current


def set_save_params(params: SaveParams) -> None:
    global _current
    _current = params


def update_save_params(**changes: object) -> SaveParams:
    params = replace(_current, **changes)
    set_save_params(params)
    return params
