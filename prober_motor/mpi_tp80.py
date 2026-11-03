"""MPI TP80 prober chuck motor driver with TCP command interface."""

from __future__ import annotations


import logging

import re

from prober_motor.base import ChuckMotorBase, ChuckPosition

from prober_motor.tcp_client import CRLF_SUFFIX, ProberTcpClient


logger = logging.getLogger(__name__)


_READ_XY_CMD = "get_chuck_xy"
_READ_Z_CMD = "get_chuck_z"
_READ_CONTACT_POS_CMD = "get_chuck_contact_pos"
_XY_POSITION_TOLERANCE_MM = 0.02


class MpiTp80ChuckMotor(ChuckMotorBase):
    """MPI TP80 prober HAL — sends move_chuck_* commands over TCP when connected."""

    def __init__(self) -> None:

        super().__init__()

        self._x = 0.0

        self._y = 0.0

        self._z = 0.0

        self._z_state = "load"

        self._tcp_client: ProberTcpClient | None = None

    @property
    def prober_name(self) -> str:

        return "Prober_MPI-TP80"

    @property
    def xy_move_ends_at_contact(self) -> bool:
        # ``move_chuck_xy …,1`` is a safe move: raise Z, XY, then contact.
        return True

    def set_tcp_client(self, client: ProberTcpClient | None) -> None:

        self._tcp_client = client
        if client is not None:
            client.command_suffix = CRLF_SUFFIX

    def _send_tcp(self, command: str) -> None:

        if self._tcp_client is None or not self._tcp_client.is_connected:

            raise RuntimeError("請先連接 Prober Server (Connect)")

        self._tcp_client.send(command)

    def _send_tcp_and_receive(self, command: str, timeout: float | None = None) -> str:

        if self._tcp_client is None or not self._tcp_client.is_connected:

            raise RuntimeError("請先連接 Prober Server (Connect)")

        if timeout is None:
            return self._tcp_client.send_and_receive(command)
        return self._tcp_client.send_and_receive(command, timeout=timeout)

    @staticmethod
    def _is_z_move_success_response(response: str) -> bool:
        """Return True for SENTIO Z-move success: ``0,0,OK`` or ``0,0,<height>``."""
        parts = [part.strip() for part in response.strip().split(",") if part.strip()]
        if len(parts) < 3 or parts[0] != "0":
            return False
        if parts[-1].upper() == "OK":
            return True
        try:
            float(parts[-1])
            return True
        except ValueError:
            return False

    def expected_xy_um_for_die(self, die_x: int, die_y: int) -> tuple[float, float]:
        d_x = die_x - self.home_die_index_x
        d_y = die_y - self.home_die_index_y
        x_um = -d_x * self._chuck_index_x_um + self._home_abs_coord_x
        y_um = d_y * self._chuck_index_y_um + self._home_abs_coord_y
        return x_um, y_um

    def _wait_for_z_state(self, target_state: str, timeout_sec: float) -> None:
        """Send Z move and wait for TCP success reply (``0,0,OK`` or ``0,0,<z>``)."""
        command_by_state = {
            "contact": "move_chuck_contact",
            "separation": "move_chuck_separation",
        }
        command = command_by_state.get(target_state)
        if command is None:
            raise ValueError(f"unsupported Z state: {target_state!r}")

        logger.info("[%s] HW command: %s", self.prober_name, command)
        response = self._send_tcp_and_receive(command, timeout=timeout_sec)
        if not response:
            raise TimeoutError(
                f"等待 Z 軸指令 {command!r} 回傳逾時 ({timeout_sec:g} 秒)"
            )
        if not self._is_z_move_success_response(response):
            raise RuntimeError(
                f"Z 軸指令 {command!r} 回傳非預期: {response!r}"
                "（預期 0,0,OK 或 0,0,<height>）"
            )
        self._z_state = target_state
        logger.info(
            "[%s] Z -> %s (reply=%s)",
            self.prober_name,
            target_state,
            response,
        )

    @staticmethod
    def _parse_get_chuck_xy_response(response: str) -> tuple[float, float] | None:

        parts = [part.strip() for part in response.split(",")]

        if len(parts) >= 4:

            try:

                return float(parts[2]), float(parts[3])

            except ValueError:

                pass

        numbers = [float(match) for match in re.findall(r"[-+]?\d*\.?\d+", response)]

        if len(numbers) >= 4:

            return numbers[2], numbers[3]

        return None

    def _query_chuck_xy(self) -> tuple[float, float] | None:

        logger.info("[%s] HW command: %s", self.prober_name, _READ_XY_CMD)

        response = self._send_tcp_and_receive(_READ_XY_CMD)

        parsed = self._parse_get_chuck_xy_response(response)

        if parsed is None:

            logger.warning(
                "[%s] Unable to parse %s response: %r",
                self.prober_name,
                _READ_XY_CMD,
                response,
            )

        return parsed

    @staticmethod
    def _parse_get_chuck_z_response(response: str) -> float | None:
        """Parse ``get_chuck_z`` reply ``0,0,x.xxxx``; return last float (mm)."""
        parts = [part.strip() for part in response.split(",") if part.strip()]
        if len(parts) >= 3:
            try:
                return float(parts[-1])
            except ValueError:
                pass

        numbers = [float(match) for match in re.findall(r"[-+]?\d*\.?\d+", response)]
        if numbers:
            return numbers[-1]
        return None

    def get_chuck_z(self) -> float:
        logger.info("[%s] HW command: %s", self.prober_name, _READ_Z_CMD)
        response = self._send_tcp_and_receive(_READ_Z_CMD)
        parsed = self._parse_get_chuck_z_response(response)
        if parsed is None:
            raise ValueError(f"無法解析 {_READ_Z_CMD} 回傳: {response!r}")
        self._z = parsed
        return self._z

    @staticmethod
    def _parse_get_chuck_contact_pos_response(response: str) -> float | None:
        """Parse ``get_chuck_contact_pos`` reply ``0,0,7.356``; return last float (mm)."""
        parts = [part.strip() for part in response.split(",") if part.strip()]
        if len(parts) >= 3:
            try:
                return float(parts[-1])
            except ValueError:
                pass

        numbers = [float(match) for match in re.findall(r"[-+]?\d*\.?\d+", response)]
        if numbers:
            return numbers[-1]
        return None

    def read_chuck_contact_pos(self) -> float:
        """Read contact height via ``get_chuck_contact_pos``; unit is um (micron meter).

        Hardware reply is mm (e.g. ``0,0,7.356``); convert last value * 1000 to um.
        """
        logger.info("[%s] HW command: %s", self.prober_name, _READ_CONTACT_POS_CMD)
        response = self._send_tcp_and_receive(_READ_CONTACT_POS_CMD)
        height_mm = self._parse_get_chuck_contact_pos_response(response)
        if height_mm is None:
            raise ValueError(f"無法解析 {_READ_CONTACT_POS_CMD} 回傳: {response!r}")
        # Contact height in um (micron meter).
        self._contact_height_um = height_mm * 1000.0
        logger.info(
            "[%s] contact_height_um=%.3f (from %s mm)",
            self.prober_name,
            self._contact_height_um,
            height_mm,
        )
        return self._contact_height_um

    def _relative_move_command(self, x_um: float, y_um: float) -> str:

        return f"move_chuck_xy Relative,{x_um / 1000.0},{y_um / 1000.0},1"

    def _home_move_command(self, x_um: float, y_um: float) -> str:

        return f"move_chuck_xy Zero,{x_um / 1000.0},{y_um / 1000.0},1"

    def move_chuck_xy(self, x: float, y: float) -> None:

        command = self._home_move_command(x, y)

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._x = x

        self._y = y

    def move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:

        x_um = num_x_index * self._chuck_index_x_um

        y_um = num_y_index * self._chuck_index_y_um

        if x_um != 0 or y_um != 0:

            command = self._relative_move_command(float(x_um), float(y_um))

            logger.info("[%s] HW command: %s", self.prober_name, command)

            self._send_tcp(command)

            self._x += x_um

            self._y += y_um

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

    def move_chuck_index_jump(
        self, target_die_index_x: int, target_die_index_y: int
    ) -> None:

        if target_die_index_x < 0 or target_die_index_y < 0:

            raise ValueError("wafer map index must be non-negative")

        if (
            target_die_index_x == self._now_die_index_x
            and target_die_index_y == self._now_die_index_y
        ):

            return

        dX = target_die_index_x - self.home_die_index_x

        dY = target_die_index_y - self.home_die_index_y

        x_um = -dX * self._chuck_index_x_um + self.home_abs_coord_x

        y_um = dY * self._chuck_index_y_um + self.home_abs_coord_y

        # convert um to mm
        command = self._home_move_command(float(x_um), float(y_um))

        logger.info("[%s] HW command: %s", self.prober_name, command)

        self._send_tcp(command)

        self._x = x_um

        self._y = y_um

        self._now_die_index_x = target_die_index_x

        self._now_die_index_y = target_die_index_y

        logger.info(
            "[%s] move_chuck_index_jump(%d, %d) -> coord=(%d, %d)",
            self.prober_name,
            target_die_index_x,
            target_die_index_y,
            self._now_die_index_x,
            self._now_die_index_y,
        )

    def move_chuck_load(self) -> None:
        command = "move_chuck_load"
        logger.info("[%s] HW command: %s", self.prober_name, command)
        response = self._send_tcp_and_receive(command)
        if not response:
            raise TimeoutError(f"等待 Z 軸指令 {command!r} 回傳逾時")
        if not self._is_z_move_success_response(response):
            raise RuntimeError(
                f"Z 軸指令 {command!r} 回傳非預期: {response!r}"
                "（預期 0,0,OK 或 0,0,<height>）"
            )
        self._z_state = "load"
        logger.info("[%s] Z -> load (reply=%s)", self.prober_name, response)

    def move_chuck_seperation(self) -> None:
        """Raise chuck to separation and consume TCP reply ``0,0,OK``."""
        self._wait_for_z_state("separation", timeout_sec=60.0)

    def move_chuck_contact(self) -> None:
        """Lower chuck to contact and consume TCP reply ``0,0,OK``."""
        self._wait_for_z_state("contact", timeout_sec=60.0)

    def move_chuck_seperation_and_wait(self, timeout_sec: float = 60.0) -> None:
        """Raise chuck to separation and wait for TCP reply ``0,0,OK``."""
        self._wait_for_z_state("separation", timeout_sec)

    def move_chuck_contact_and_wait(self, timeout_sec: float = 60.0) -> None:
        """Lower chuck to contact and wait for TCP reply ``0,0,OK``."""
        self._wait_for_z_state("contact", timeout_sec)

    def is_z_at(self, z_state: str) -> bool:
        return self._z_state == z_state

    def is_at_die_index(self, die_x: int, die_y: int) -> bool:
        if self._tcp_client is None or not self._tcp_client.is_connected:
            return super().is_at_die_index(die_x, die_y)

        expected_x_um, expected_y_um = self.expected_xy_um_for_die(die_x, die_y)
        expected_x_mm = expected_x_um / 1000.0
        expected_y_mm = expected_y_um / 1000.0
        parsed = self._query_chuck_xy()
        if parsed is None:
            return False

        x_mm, y_mm = parsed
        tolerance = _XY_POSITION_TOLERANCE_MM
        return (
            abs(x_mm - expected_x_mm) <= tolerance
            and abs(y_mm - expected_y_mm) <= tolerance
        )

    def move_to_die_and_wait(
        self,
        die_x: int,
        die_y: int,
        timeout_sec: float = 120.0,
    ) -> None:
        if die_x < 0 or die_y < 0:
            raise ValueError("wafer map index must be non-negative")

        # calculate the difference between the die index and the home die index
        d_x = die_x - self.home_die_index_x
        d_y = die_y - self.home_die_index_y
        # convert the difference to absolute coordinate using the chuck index
        # the x direction of the chuck is opposite to the x direction of the die
        x_um = -d_x * self._chuck_index_x_um + self.home_abs_coord_x
        y_um = d_y * self._chuck_index_y_um + self.home_abs_coord_y

        # Trailing ``1`` = safe move: raise Z, XY, then lower to contact.
        # On arrival TP80 replies with current XY, same format as get_chuck_xy: ``0,0,x,y``.
        command = self._home_move_command(float(x_um), float(y_um))
        logger.info("[%s] HW command: %s", self.prober_name, command)
        response = self._send_tcp_and_receive(command, timeout=timeout_sec)
        if not response:
            raise TimeoutError(
                f"等待移動至 die ({die_x}, {die_y}) 逾時 ({timeout_sec:g} 秒)"
            )

        parsed = self._parse_get_chuck_xy_response(response)
        if parsed is None:
            raise RuntimeError(
                f"移動至 die ({die_x}, {die_y}) 回傳非預期: {response!r}"
                "（預期 0,0,x,y）"
            )

        self._x, self._y = parsed
        self._now_die_index_x = die_x
        self._now_die_index_y = die_y
        self._z_state = "contact"
        logger.info(
            "[%s] move_to_die_and_wait(%d, %d) arrived (Z=contact, reply=%s)",
            self.prober_name,
            die_x,
            die_y,
            response,
        )

    def read_chuck_position(self, *, use_cache: bool = False) -> ChuckPosition:

        if (
            not use_cache
            and self._tcp_client is not None
            and self._tcp_client.is_connected
        ):

            try:

                parsed = self._query_chuck_xy()

                if parsed is not None:

                    self._x, self._y = parsed

                self._z = self.get_chuck_z()

            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:

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

    def set_chuck_index(self, chuck_index_x_um: int, chuck_index_y_um: int) -> None:

        logger.info(
            "[%s] HW command: ChuckSetIndex(%d, %d)",
            self.prober_name,
            chuck_index_x_um,
            chuck_index_y_um,
        )

        self._chuck_index_x_um = chuck_index_x_um

        self._chuck_index_y_um = chuck_index_y_um

    def set_chuck_home(self, home_die_index_x: int, home_die_index_y: int) -> None:

        super().set_chuck_home(home_die_index_x, home_die_index_y)

        parsed = self._query_chuck_xy()

        if parsed is None:

            raise ValueError(f"無法解析 {_READ_XY_CMD} 回傳座標")

        home_x_mm, home_y_mm = parsed
        self._x = home_x_mm
        self._y = home_y_mm
        self._home_abs_coord_x = home_x_mm * 1000.0
        self._home_abs_coord_y = home_y_mm * 1000.0

        logger.info(
            "[%s] set_chuck_home die=(%d, %d) home_abs_coord=(%.3f, %.3f) um",
            self.prober_name,
            home_die_index_x,
            home_die_index_y,
            self._home_abs_coord_x,
            self._home_abs_coord_y,
        )

    def move_chuck_home(self) -> None:
        command = self._home_move_command(self.home_abs_coord_x, self.home_abs_coord_y)

        logger.info("[%s] HW command: %s", self.prober_name, command)
        self._send_tcp(command)

        self._x = self.home_abs_coord_x
        self._y = self.home_abs_coord_y
        self._now_die_index_x = self.home_die_index_x
        self._now_die_index_y = self.home_die_index_y

    def set_chuck_contact(self) -> None:

        pass

    def move_chuck_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:
        """Velocity-mode XY step: relative move of ``0.1 * speed`` mm per press."""
        self._move_chuck_xy_relative_step(vx, vy, 0.1 * float(speed))

    def move_chuck_xy_jog(self, vx: str, vy: str) -> None:
        """Jog XY by 0.001 mm via ``move_chuck_xy Relative``."""
        self._move_chuck_xy_relative_step(vx, vy, 0.001)

    def _move_chuck_xy_relative_step(self, vx: str, vy: str, step_mm: float) -> None:
        """Send ``move_chuck_xy Relative``; X→/Y↑ = +step, X←/Y↓ = -step (mm)."""

        def _axis_mm(token: str) -> float:
            if token == "+":
                return step_mm
            if token == "-":
                return -step_mm
            return 0.0

        dx_mm = _axis_mm(vx)
        dy_mm = _axis_mm(vy)
        if dx_mm == 0.0 and dy_mm == 0.0:
            return

        command = self._relative_move_command(dx_mm * 1000.0, dy_mm * 1000.0)
        logger.info("[%s] HW command: %s", self.prober_name, command)
        response = self._send_tcp_and_receive(command)
        parsed = self._parse_get_chuck_xy_response(response)
        if parsed is not None:
            self._x, self._y = parsed

    def move_chuck_z_velocity(self, vx: str, vy: str, vz: str, speed: float) -> None:
        """Velocity-mode Z step: ``move_chuck_z Relative`` by ``0.01 * speed`` mm."""
        self._move_chuck_z_relative_step(vz, 0.01 * float(speed))

    def move_chuck_z_jog(self, vz: str) -> None:
        """Jog/Index Z step: ``move_chuck_z Relative`` by 0.001 mm."""
        self._move_chuck_z_relative_step(vz, 0.001)

    def _move_chuck_z_relative_step(self, vz: str, step_mm: float) -> None:
        """Z↑ = +step_mm, Z↓ = -step_mm. Waits for TCP reply."""
        if vz == "+":
            distance_mm = step_mm
        elif vz == "-":
            distance_mm = -step_mm
        else:
            return

        command = f"move_chuck_z Relative,{distance_mm:.3f}"
        logger.info("[%s] HW command: %s", self.prober_name, command)
        response = self._send_tcp_and_receive(command)
        if not self._is_z_move_success_response(response):
            raise RuntimeError(
                f"Z 相對移動回傳非預期: {response!r}（預期 0,0,OK 或 0,0,<height>）"
            )
        parts = [part.strip() for part in response.split(",") if part.strip()]
        if len(parts) >= 3 and parts[-1].upper() != "OK":
            try:
                self._z = float(parts[-1])
            except ValueError:
                pass

    def stop_chuck_movement(self) -> None:

        pass
