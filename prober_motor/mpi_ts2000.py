"""MPI TS2000 prober chuck motor driver stub."""

from __future__ import annotations


from prober_motor.base import ChuckMotorBase, ChuckPosition


class MpiTs2000ChuckMotor(ChuckMotorBase):
    """MPI TS2000 prober HAL — method stubs to be implemented."""

    @property
    def prober_name(self) -> str:

        return "Prober_MPI-TS2000"

    def move_chuck_xy(self, x: float, y: float) -> None:

        pass

    def move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:

        pass

    def move_chuck_index_jump(self, x: int, y: int) -> None:

        pass

    def move_chuck_seperation(self) -> None:

        pass

    def move_chuck_contact(self) -> None:

        pass

    def move_chuck_load(self) -> None:

        pass

    def read_chuck_position(self, *, use_cache: bool = False) -> ChuckPosition:

        raise NotImplementedError

    def get_chuck_z(self) -> float:

        raise NotImplementedError

    def set_chuck_index(self, chuck_index_x_um: int, chuck_index_y_um: int) -> None:

        pass

    def set_chuck_home(self, home_die_index_x: int, home_die_index_y: int) -> None:

        super().set_chuck_home(home_die_index_x, home_die_index_y)

    def move_chuck_home(self) -> None:

        pass

    def set_chuck_contact(self) -> None:

        pass

    def read_chuck_contact_pos(self) -> float:
        """Read contact height; unit is um (micron meter)."""
        raise NotImplementedError

    def move_chuck_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        pass

    def move_chuck_z_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        pass

    def stop_chuck_movement(self) -> None:

        pass
