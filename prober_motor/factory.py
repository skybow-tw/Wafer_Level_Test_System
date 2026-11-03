"""Factory for creating prober chuck motor drivers."""

from __future__ import annotations

from enum import Enum

from prober_motor.base import ChuckMotorBase
from prober_motor.mpi_tp80 import MpiTp80ChuckMotor
from prober_motor.mpi_ts2000 import MpiTs2000ChuckMotor
from prober_motor.simulated import SimulatedChuckMotor
from prober_motor.suss import SussChuckMotor


class ProberType(Enum):
    SIMULATION = "模擬馬達"
    SUSS = "Prober_SUSS"
    MPI_TP80 = "Prober_MPI-TP80"
    MPI_TS2000 = "Prober_MPI-TS2000"


_MOTOR_CLASSES: dict[ProberType, type[ChuckMotorBase]] = {
    ProberType.SIMULATION: SimulatedChuckMotor,
    ProberType.SUSS: SussChuckMotor,
    ProberType.MPI_TP80: MpiTp80ChuckMotor,
    ProberType.MPI_TS2000: MpiTs2000ChuckMotor,
}


def create_chuck_motor(prober_type: ProberType) -> ChuckMotorBase:
    motor_cls = _MOTOR_CLASSES[prober_type]
    return motor_cls()
