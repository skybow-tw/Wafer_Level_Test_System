"""Simulated chuck motor for offline development and testing."""

from __future__ import annotations


import logging


from prober_motor.base import ChuckMotorBase, ChuckPosition


logger = logging.getLogger(__name__)


class SimulatedChuckMotor(ChuckMotorBase):

    def __init__(self) -> None:

        super().__init__()

        self._x = 0.0

        self._y = 0.0

        self._z = 0.0

        self._z_state = "load"

    @property
    def prober_name(self) -> str:

        return "模擬馬達"

    def move_chuck_xy(self, x: float, y: float) -> None:

        self._x = x

        self._y = y

        logger.info("[%s] move_chuck_xy(%.3f, %.3f)", self.prober_name, x, y)

    def move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:

        self._x += num_x_index * self._chuck_index_x_um

        self._y += num_y_index * self._chuck_index_y_um

        self._now_die_index_x += num_x_index

        self._now_die_index_y += num_y_index

        logger.info(
            "[%s] move_chuck_index_relative(%d, %d) -> coord=(%d, %d)",
            self.prober_name,
            num_x_index,
            num_y_index,
            self._now_die_index_x,
            self._now_die_index_y,
        )

    def move_chuck_index_jump(self, x: int, y: int) -> None:

        if x < 0 or y < 0:

            raise ValueError("wafer map index must be non-negative")

        dx = x - self._now_die_index_x

        dy = y - self._now_die_index_y

        if dx == 0 and dy == 0:

            return

        self.move_chuck_index_relative(dx, dy)

        logger.info(
            "[%s] move_chuck_index_jump(%d, %d) -> coord=(%d, %d)",
            self.prober_name,
            x,
            y,
            self._now_die_index_x,
            self._now_die_index_y,
        )

    def move_chuck_seperation(self) -> None:

        self._z_state = "separation"

        logger.info("[%s] move_chuck_seperation()", self.prober_name)

    def move_chuck_contact(self) -> None:

        self._z_state = "contact"

        logger.info("[%s] move_chuck_contact()", self.prober_name)

    def move_chuck_load(self) -> None:

        self._z_state = "load"

        logger.info("[%s] move_chuck_load()", self.prober_name)

    def read_chuck_position(self, *, use_cache: bool = False) -> ChuckPosition:

        return ChuckPosition(
            x=self._x,
            y=self._y,
            now_die_index_x=self._now_die_index_x,
            now_die_index_y=self._now_die_index_y,
            z=self._z,
            z_state=self._z_state,
        )

    def get_chuck_z(self) -> float:

        return self._z

    def set_chuck_index(self, chuck_index_x_um: int, chuck_index_y_um: int) -> None:

        self._chuck_index_x_um = chuck_index_x_um

        self._chuck_index_y_um = chuck_index_y_um

        logger.info(
            "[%s] set_chuck_index(chuck_index_x_um=%d, chuck_index_y_um=%d)",
            self.prober_name,
            chuck_index_x_um,
            chuck_index_y_um,
        )

    def set_chuck_home(self, home_die_index_x: int, home_die_index_y: int) -> None:

        super().set_chuck_home(home_die_index_x, home_die_index_y)

    def move_chuck_home(self) -> None:

        pass

    def set_chuck_contact(self) -> None:

        logger.info("[%s] set_chuck_contact() z=%s", self.prober_name, self._z_state)

    def read_chuck_contact_pos(self) -> float:
        """Return and record contact height in um (micron meter)."""
        # Contact height in um (micron meter).
        self._contact_height_um = 0.0
        logger.info(
            "[%s] read_chuck_contact_pos() -> %.3f um",
            self.prober_name,
            self._contact_height_um,
        )
        return self._contact_height_um

    def move_chuck_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        logger.info(
            "[%s] move_chuck_velocity(%s, %s, %s, %.1f)",
            self.prober_name,
            vx,
            vy,
            vz,
            speed,
        )

    def move_chuck_z_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        logger.info(
            "[%s] move_chuck_z_velocity(%s, %s, %s, %.1f)",
            self.prober_name,
            vx,
            vy,
            vz,
            speed,
        )

    def stop_chuck_movement(self) -> None:

        logger.info("[%s] stop_chuck_movement()", self.prober_name)
