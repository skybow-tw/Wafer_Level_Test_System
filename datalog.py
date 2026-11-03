"""Datalog directory creation and save-file naming under the work directory."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DATALOG_ROOT_NAME = "00_Datalog"
DEFAULT_SAVE_EXTENSION = ".csv"

_INVALID_NAME_CHARS = '<>:"/\\|?*'

_SaveDirListener = Callable[[Path], None]
_save_dir_created_this_session = False
_last_created_save_dir: Path | None = None
_save_dir_listeners: list[_SaveDirListener] = []


def default_date_folder_name(now: datetime | None = None) -> str:
    """Return YYYYMMDD used as the default datalog folder name."""
    return (now or datetime.now()).strftime("%Y%m%d")


def datalog_root(work_dir: Path) -> Path:
    return work_dir / DATALOG_ROOT_NAME


def sanitize_path_component(value: str) -> str:
    """Strip whitespace/newlines and replace characters illegal in path names."""
    text = value.replace("\n", "").replace("\r", "").strip()
    for char in _INVALID_NAME_CHARS:
        text = text.replace(char, "_")
    return text.strip(" .")


def save_dir_created_this_session() -> bool:
    """True after this process has created a custom or date save folder."""
    return _save_dir_created_this_session


def last_created_save_dir() -> Path | None:
    return _last_created_save_dir


def register_save_dir_listener(callback: _SaveDirListener) -> None:
    if callback not in _save_dir_listeners:
        _save_dir_listeners.append(callback)


def unregister_save_dir_listener(callback: _SaveDirListener) -> None:
    if callback in _save_dir_listeners:
        _save_dir_listeners.remove(callback)


def _record_created_save_dir(path: Path) -> None:
    global _save_dir_created_this_session, _last_created_save_dir
    _save_dir_created_this_session = True
    _last_created_save_dir = path
    for callback in list(_save_dir_listeners):
        callback(path)


def ensure_default_date_dir(work_dir: Path) -> Path:
    """Create ``00_Datalog/<YYYYMMDD>`` when no custom folder name is used."""
    path = datalog_root(work_dir) / default_date_folder_name()
    path.mkdir(parents=True, exist_ok=True)
    _record_created_save_dir(path)
    return path


def resolve_save_dir(work_dir: Path, folder_name: str) -> Path:
    """Create ``00_Datalog/<folder_name>``, or the date folder when name is blank."""
    name = sanitize_path_component(folder_name)
    if name:
        path = datalog_root(work_dir) / name
        path.mkdir(parents=True, exist_ok=True)
        _record_created_save_dir(path)
        return path
    return ensure_default_date_dir(work_dir)


def create_session_dir(work_dir: Path, folder_name: str) -> Path:
    """Create ``00_Datalog/<folder_name>`` if it does not already exist."""
    return resolve_save_dir(work_dir, folder_name)


def build_save_filename(
    *,
    prefix: str = "",
    x: int = 1,
    y: int = 1,
    suffix: str = "",
    tag: str = "",
    extension: str = DEFAULT_SAVE_EXTENSION,
) -> str:
    """Build ``prefix_X1Y1_suffix_tag.csv``; blank prefix/suffix/tag are omitted."""
    parts: list[str] = []
    prefix_part = sanitize_path_component(prefix)
    suffix_part = sanitize_path_component(suffix)
    tag_part = sanitize_path_component(tag)
    if prefix_part:
        parts.append(prefix_part)
    parts.append(f"X{x}Y{y}")
    if suffix_part:
        parts.append(suffix_part)
    if tag_part:
        parts.append(tag_part)
    stem = "_".join(parts)
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{stem}{ext}"


def resolve_save_path(
    work_dir: Path,
    *,
    folder_name: str = "",
    prefix: str = "",
    x: int = 1,
    y: int = 1,
    suffix: str = "",
    tag: str = "",
    extension: str = DEFAULT_SAVE_EXTENSION,
) -> Path:
    directory = resolve_save_dir(work_dir, folder_name)
    return directory / build_save_filename(
        prefix=prefix,
        x=x,
        y=y,
        suffix=suffix,
        tag=tag,
        extension=extension,
    )
