"""Pydantic models for WebSocket message protocol."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel


class SensorData(BaseModel):
    hr_samples: list[float]
    hrv_samples: list[float] = []
    accel_x: list[float] = []
    accel_y: list[float] = []
    accel_z: list[float] = []
    sonar_breathing_rate: Optional[float] = None
    sonar_amplitude: Optional[float] = None
    audio_rms: Optional[float] = None
    audio_zcr: Optional[float] = None
    audio_spectral_centroid: Optional[float] = None
    audio_class: Optional[str] = None


class SensorEpoch(BaseModel):
    type: Literal["sensor_epoch"]
    epoch_index: int
    timestamp: str
    data: SensorData


class SessionStart(BaseModel):
    type: Literal["session_start"]
    session_id: str
    started_at: str


class SessionEnd(BaseModel):
    type: Literal["session_end"] = "session_end"


class StageProbabilities(BaseModel):
    awake: float
    remSleep: float
    coreLight: float
    deepSleep: float
    inBed: float


class Prediction(BaseModel):
    type: Literal["prediction"] = "prediction"
    epoch_index: int
    stage: str
    confidence: float
    probabilities: StageProbabilities


class SessionAck(BaseModel):
    type: Literal["session_ack"] = "session_ack"
    session_id: str
    user_id: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


IncomingMessage = Union[SensorEpoch, SessionStart, SessionEnd]


def parse_incoming(data: dict) -> IncomingMessage:
    msg_type = data.get("type")
    if msg_type == "sensor_epoch":
        return SensorEpoch(**data)
    elif msg_type == "session_start":
        return SessionStart(**data)
    elif msg_type == "session_end":
        return SessionEnd()
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
