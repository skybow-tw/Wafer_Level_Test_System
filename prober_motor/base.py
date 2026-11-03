"""Abstract base class for prober chuck motor control (HAL)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_DEFAULT_XY_MOVE_TIMEOUT_SEC = 120.0
_DEFAULT_Z_MOVE_TIMEOUT_SEC = 60.0
_MOTOR_POLL_INTERVAL_SEC = 0.1


class MoveDirection(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class ChuckPosition:
    x: float
    y: float
    now_die_index_x: int
    now_die_index_y: int
    z: float = 0.0
    z_state: str = "load"


class ChuckMotorBase(ABC):
    """Hardware abstraction layer for prober chuck XY/Z motion."""

    def __init__(self) -> None:
        self._now_die_index_x = 0
        self._now_die_index_y = 0
        self._home_die_index_x = 0
        self._home_die_index_y = 0
        self._home_abs_coord_x = 0.0
        self._home_abs_coord_y = 0.0
        self._chuck_index_x_um = 1
        self._chuck_index_y_um = 1
        # Contact height in um (micron meter); set by read_chuck_contact_pos().
        self._contact_height_um: float | None = None

    @property
    @abstractmethod
    def prober_name(self) -> str:
        """Human-readable prober identifier."""

    @abstractmethod
    def move_chuck_xy(self, x: float, y: float) -> None:
        """Move chuck to absolute XY coordinates (mm or machine units)."""

    @abstractmethod
    def move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:
        """Move chuck by relative die index steps (may be negative)."""

    @abstractmethod
    def move_chuck_index_jump(self, x: int, y: int) -> None:
        """Move chuck to absolute wafer map die index (non-negative)."""

    @abstractmethod
    def move_chuck_seperation(self) -> None:
        """Raise chuck to separation (probe off wafer) position."""

    @abstractmethod
    def move_chuck_contact(self) -> None:
        """Lower chuck to contact (probe on wafer) position."""

    @abstractmethod
    def move_chuck_load(self) -> None:
        """Move chuck to load/unload wafer position."""

    @abstractmethod
    def read_chuck_position(self, *, use_cache: bool = False) -> ChuckPosition:
        """Read current chuck XY/Z position.

        When ``use_cache`` is True, return the last known position without
        querying hardware.
        """

    @abstractmethod
    def get_chuck_z(self) -> float:
        """Read current chuck Z absolute coordinate in millimetres."""

    @abstractmethod
    def set_chuck_index(self, chuck_index_x_um: int, chuck_index_y_um: int) -> None:
        """Configure per-die physical index spacing in X and Y directions (um)."""

    @abstractmethod
    def set_chuck_home(self, home_die_index_x: int, home_die_index_y: int) -> None:
        """Record wafer-map die index defined as home.

        Subclasses must override; call ``super().set_chuck_home(home_die_index_x, home_die_index_y)`` to
        update base state. Physical chuck coordinates (``home_abs_coord_x`` /
        ``home_abs_coord_y``) are set by subclass hardware logic.
        """
        self._home_die_index_x = home_die_index_x
        self._home_die_index_y = home_die_index_y
        # Current chuck location is defined as this home die.
        self._now_die_index_x = home_die_index_x
        self._now_die_index_y = home_die_index_y
        logger.info(
            "[%s] set_chuck_home(die=(%d, %d))",
            self.prober_name,
            home_die_index_x,
            home_die_index_y,
        )

    @abstractmethod
    def move_chuck_home(self) -> None:
        """Move chuck to the recorded home position."""

    @abstractmethod
    def set_chuck_contact(self) -> None:
        """Record current chuck Z position as contact (probe-on-wafer reference)."""

    @abstractmethod
    def read_chuck_contact_pos(self) -> float:
        """Read chuck contact height from hardware and record it.

        Returns contact height in um (micron meter).
        """

    @property
    def contact_height_um(self) -> float | None:
        """Last recorded contact height in um (micron meter), or None if unread."""
        return self._contact_height_um

    @abstractmethod
    def move_chuck_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:
        """Move chuck at velocity; axis tokens are ``+``, ``-``, or ``0``; speed is percent."""

    @abstractmethod
    def move_chuck_z_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:
        """Move chuck Z axis; SUSS uses ``MoveChuck``, TP80 uses ``move_chuck_safe_z Relative``."""

    @abstractmethod
    def stop_chuck_movement(self) -> None:
        """Stop active chuck velocity motion."""

    def move_to_die_index(self, now_die_index_x: int, now_die_index_y: int) -> None:
        """Move chuck to die grid index on wafer map."""
        self.move_chuck_index_jump(now_die_index_x, now_die_index_y)
        logger.info(
            "[%s] move_to_die_index(%d, %d)",
            self.prober_name,
            now_die_index_x,
            now_die_index_y,
        )

    def expected_xy_um_for_die(self, die_x: int, die_y: int) -> tuple[float, float]:
        """Return expected chuck XY (µm) for a wafer-map die index."""
        d_x = die_x - self.home_die_index_x
        d_y = die_y - self.home_die_index_y
        x_um = d_x * self._chuck_index_x_um + self._home_abs_coord_x
        y_um = d_y * self._chuck_index_y_um + self._home_abs_coord_y
        return x_um, y_um

    def is_at_die_index(self, die_x: int, die_y: int) -> bool:
        """Return whether chuck is at the given wafer-map die index."""
        pos = self.read_chuck_position()
        return pos.now_die_index_x == die_x and pos.now_die_index_y == die_y

    def is_z_at(self, z_state: str) -> bool:
        """Return whether chuck Z is at the given state (load/separation/contact)."""
        return self.read_chuck_position().z_state == z_state

    @property
    def xy_move_ends_at_contact(self) -> bool:
        """Whether ``move_to_die_and_wait`` leaves Z at contact (safe XY move).

        When True, the measurement workflow can skip explicit raise-Z-before-XY
        and lower-Z-to-contact steps after arriving at a die.
        """
        return False

    def move_to_die_and_wait(
        self,
        die_x: int,
        die_y: int,
        timeout_sec: float = _DEFAULT_XY_MOVE_TIMEOUT_SEC,
    ) -> None:
        """Move to die index and block until arrival is confirmed."""
        self.move_chuck_index_jump(die_x, die_y)
        self._wait_until_at_die(die_x, die_y, timeout_sec)

    def move_chuck_contact_and_wait(
        self,
        timeout_sec: float = _DEFAULT_Z_MOVE_TIMEOUT_SEC,
    ) -> None:
        """Lower chuck to contact and block until Z reaches contact."""
        self.move_chuck_contact()
        # Z state is updated by move_chuck_contact(); no hardware query to poll.

    def move_chuck_seperation_and_wait(
        self,
        timeout_sec: float = _DEFAULT_Z_MOVE_TIMEOUT_SEC,
    ) -> None:
        """Raise chuck to separation and block until Z reaches separation."""
        self.move_chuck_seperation()
        # Z state is updated by move_chuck_seperation(); no hardware query to poll.

    def _wait_until_at_die(
        self, die_x: int, die_y: int, timeout_sec: float
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.is_at_die_index(die_x, die_y):
                return
            time.sleep(_MOTOR_POLL_INTERVAL_SEC)
        raise TimeoutError(
            f"等待移動至 die ({die_x}, {die_y}) 逾時 ({timeout_sec:g} 秒)"
        )

    @property
    def now_die_index_x(self) -> int:
        return self._now_die_index_x

    @property
    def now_die_index_y(self) -> int:
        return self._now_die_index_y

    @property
    def home_die_index_x(self) -> int:
        """Wafer-map die index (X) defined as home."""
        return self._home_die_index_x

    @property
    def home_die_index_y(self) -> int:
        """Wafer-map die index (Y) defined as home."""
        return self._home_die_index_y

    @property
    def home_abs_coord_x(self) -> float:
        """Absolute chuck X coordinate (µm) at home."""
        return self._home_abs_coord_x

    @property
    def home_abs_coord_y(self) -> float:
        """Absolute chuck Y coordinate (µm) at home."""
        return self._home_abs_coord_y

    @property
    def Chuck_index_x_um(self) -> int:
        return self._chuck_index_x_um

    @property
    def Chuck_index_y_um(self) -> int:
        return self._chuck_index_y_um
