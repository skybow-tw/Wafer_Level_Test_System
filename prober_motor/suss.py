"""SUSS prober chuck motor driver stub."""

from __future__ import annotations


import logging

import re

import time


from prober_motor.base import ChuckMotorBase, ChuckPosition

from prober_motor.tcp_client import CRLF_SUFFIX, ProberTcpClient


logger = logging.getLogger(__name__)


_READ_POSITION_CMD = "ReadChuckPosition Y Z"
_READ_CONTACT_HEIGHTS_CMD = "ReadChuckHeights Y"
_XY_POSITION_TOLERANCE_UM = 50.0
_Z_SETTLE_SEC = 0.5


class SussChuckMotor(ChuckMotorBase):
    """SUSS prober HAL — method stubs to be implemented."""

    def __init__(self) -> None:

        super().__init__()

        self._x = 0.0

        self._y = 0.0

        self._z = 0.0

        self._z_state = "load"

        self._tcp_client: ProberTcpClient | None = None

    @property
    def prober_name(self) -> str:

        return "Prober_SUSS"

    def set_tcp_client(self, client: ProberTcpClient | None) -> None:

        self._tcp_client = client
        if client is not None:
            client.command_suffix = CRLF_SUFFIX

    def _send_tcp(self, command: str) -> None:

        if self._tcp_client is None or not self._tcp_client.is_connected:

            raise RuntimeError("請先連接 Prober Server (Connect)")

        self._tcp_client.send(command)

    def _send_tcp_and_receive(self, command: str) -> str:

        if self._tcp_client is None or not self._tcp_client.is_connected:

            raise RuntimeError("請先連接 Prober Server (Connect)")

        return self._tcp_client.send_and_receive(command)

    @staticmethod
    def _parse_position_response(response: str) -> tuple[float, float, float] | None:

        parts = response.strip().split()

        if len(parts) >= 3:

            try:

                return float(parts[0]), float(parts[1]), float(parts[2])

            except ValueError:

                pass

        numbers = [float(match) for match in re.findall(r"[-+]?\d*\.?\d+", response)]

        if len(numbers) >= 3:

            return numbers[0], numbers[1], numbers[2]

        return None

    def _apply_position_response(self, response: str) -> None:

        parsed = self._parse_position_response(response)

        if parsed is None:

            logger.warning(
                "[%s] Unable to parse %s response: %r",
                self.prober_name,
                _READ_POSITION_CMD,
                response,
            )

            return

        x_um, y_um, z_um = parsed

        self._x = x_um

        self._y = y_um

        self._z = z_um

    def move_chuck_xy(self, x: float, y: float) -> None:

        command = f"MoveChuck {x},{y}"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._x = x

        self._y = y

    def move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:

        if num_x_index == 0 and num_y_index == 0:

            return

        command = f"MoveChuckIndex {num_x_index} {num_y_index} R 100.0"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._x += num_x_index * self._chuck_index_x_um

        self._y += num_y_index * self._chuck_index_y_um

        self._now_die_index_x += num_x_index

        self._now_die_index_y += num_y_index

    def move_chuck_index_jump(self, x: int, y: int) -> None:

        if x < 0 or y < 0:

            raise ValueError("wafer map index must be non-negative")

        if x == self._now_die_index_x and y == self._now_die_index_y:

            return

        dX = x - self.home_die_index_x

        dY = y - self.home_die_index_y

        command = f"MoveChuckIndex {dX} {dY} H 100.0"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        dx = x - self._now_die_index_x

        dy = y - self._now_die_index_y

        self._x += dx * self._chuck_index_x_um

        self._y += dy * self._chuck_index_y_um

        self._now_die_index_x = x

        self._now_die_index_y = y

    def move_chuck_seperation(self) -> None:

        command = "MoveChuckSeperation"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._z_state = "separation"

    def move_chuck_contact(self) -> None:

        command = "MoveChuckContact"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._z_state = "contact"

    def move_chuck_seperation_and_wait(
        self, timeout_sec: float = 60.0
    ) -> None:
        command = "MoveChuckSeperation"
        logger.info("[%s] HW command: %s", self.prober_name, command)
        self._send_tcp(command)
        time.sleep(_Z_SETTLE_SEC)
        self._z_state = "separation"
        logger.info("[%s] Z -> separation (command sent)", self.prober_name)

    def move_chuck_contact_and_wait(self, timeout_sec: float = 60.0) -> None:
        command = "MoveChuckContact"
        logger.info("[%s] HW command: %s", self.prober_name, command)
        self._send_tcp(command)
        time.sleep(_Z_SETTLE_SEC)
        self._z_state = "contact"
        logger.info("[%s] Z -> contact (command sent)", self.prober_name)

    def is_at_die_index(self, die_x: int, die_y: int) -> bool:
        expected_x_um, expected_y_um = self.expected_xy_um_for_die(die_x, die_y)
        pos = self.read_chuck_position()
        tolerance = _XY_POSITION_TOLERANCE_UM
        return (
            abs(pos.x - expected_x_um) <= tolerance
            and abs(pos.y - expected_y_um) <= tolerance
        )

    def move_to_die_and_wait(
        self,
        die_x: int,
        die_y: int,
        timeout_sec: float = 120.0,
    ) -> None:
        if self.is_at_die_index(die_x, die_y):
            self._now_die_index_x = die_x
            self._now_die_index_y = die_y
            return

        self.move_chuck_index_jump(die_x, die_y)
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.is_at_die_index(die_x, die_y):
                return
            time.sleep(0.1)

        raise TimeoutError(
            f"等待移動至 die ({die_x}, {die_y}) 逾時 ({timeout_sec:g} 秒)"
        )

    def move_chuck_load(self) -> None:

        command = "MoveChuckLoad"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._z_state = "load"

    def read_chuck_position(self, *, use_cache: bool = False) -> ChuckPosition:

        if (
            not use_cache
            and self._tcp_client is not None
            and self._tcp_client.is_connected
        ):

            logger.info("[%s] HW command: %s", self.prober_name, _READ_POSITION_CMD)

            try:

                response = self._send_tcp_and_receive(_READ_POSITION_CMD)

                self._apply_position_response(response)

            except (OSError, RuntimeError, TimeoutError) as exc:

                logger.warning(
                    "[%s] read_chuck_position failed: %s", self.prober_name, exc
                )

        elif not use_cache:

            logger.warning(
                "[%s] TCP not connected, returning cached position",
                self.prober_name,
            )

        return ChuckPosition(
            x=self._x,
            y=self._y,
            now_die_index_x=self._now_die_index_x,
            now_die_index_y=self._now_die_index_y,
            z=self._z,
            z_state=self._z_state,
        )

    def get_chuck_z(self) -> float:
        """Return chuck Z absolute coordinate (mm) via ``ReadChuckPosition``.

        SUSS position replies store Z in µm; convert to mm for the HAL contract.
        """
        if self._tcp_client is not None and self._tcp_client.is_connected:
            logger.info("[%s] HW command: %s", self.prober_name, _READ_POSITION_CMD)
            try:
                response = self._send_tcp_and_receive(_READ_POSITION_CMD)
                self._apply_position_response(response)
            except (OSError, RuntimeError, TimeoutError) as exc:
                logger.warning("[%s] get_chuck_z failed: %s", self.prober_name, exc)
        return self._z / 1000.0

    @staticmethod
    def _parse_read_chuck_heights_response(response: str) -> float | None:
        """Parse ``ReadChuckHeights Y`` reply; return first float (um)."""
        parts = response.strip().split()
        if parts:
            try:
                return float(parts[0])
            except ValueError:
                pass

        numbers = [float(match) for match in re.findall(r"[-+]?\d*\.?\d+", response)]
        if numbers:
            return numbers[0]
        return None

    def read_chuck_contact_pos(self) -> float:
        """Read contact height via ``ReadChuckHeights Y``; unit is um (micron meter).

        Hardware reply e.g. ``10522.2 25.0 25.0 250.0 100.0``; take the first number.
        """
        logger.info("[%s] HW command: %s", self.prober_name, _READ_CONTACT_HEIGHTS_CMD)
        response = self._send_tcp_and_receive(_READ_CONTACT_HEIGHTS_CMD)
        height_um = self._parse_read_chuck_heights_response(response)
        if height_um is None:
            raise ValueError(
                f"無法解析 {_READ_CONTACT_HEIGHTS_CMD} 回傳: {response!r}"
            )
        # Contact height in um (micron meter).
        self._contact_height_um = height_um
        logger.info(
            "[%s] contact_height_um=%.3f",
            self.prober_name,
            self._contact_height_um,
        )
        return self._contact_height_um

    def set_chuck_index(self, chuck_index_x_um: int, chuck_index_y_um: int) -> None:

        self._chuck_index_x_um = chuck_index_x_um

        self._chuck_index_y_um = chuck_index_y_um

    def set_chuck_home(self, home_die_index_x: int, home_die_index_y: int) -> None:

        super().set_chuck_home(home_die_index_x, home_die_index_y)

        command = f"SetChuckHome {home_die_index_x} {home_die_index_y}"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

    def move_chuck_home(self) -> None:

        command = "MoveChuckHome 0 0 H"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

    def set_chuck_contact(self) -> None:

        command = "SetChuckContact"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

    def move_chuck_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        speed_str = f"{speed:.1f}"

        command = f"MoveChuckVelocity {vx} {vy} {vz} {speed_str}"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

    def move_chuck_z_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:

        speed_str = f"{speed:.1f}"

        command = f"MoveChuck {vx} {vy} {vz} {speed_str}"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

    def stop_chuck_movement(self) -> None:

        command = "StopChuckMovement"

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)
