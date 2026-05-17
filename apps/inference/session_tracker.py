"""Per-session prediction timeline tracker."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TrackedPrediction:
    epoch_index: int
    timestamp: str
    stage: str
    confidence: float
    probabilities: dict[str, float]


class SessionTracker:
    def __init__(self, session_id: str, user_id: str, started_at: str) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.started_at = started_at
        self._predictions: list[TrackedPrediction] = []

    @property
    def prediction_count(self) -> int:
        return len(self._predictions)

    def add_prediction(self, epoch_index: int, timestamp: str, stage: str, confidence: float, probabilities: dict[str, float]) -> None:
        self._predictions.append(TrackedPrediction(epoch_index=epoch_index, timestamp=timestamp, stage=stage, confidence=confidence, probabilities=probabilities))

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "prediction_count": len(self._predictions),
            "predictions": [{"epoch_index": p.epoch_index, "timestamp": p.timestamp, "stage": p.stage, "confidence": p.confidence, "probabilities": p.probabilities} for p in self._predictions],
        }

    def save_local(self, directory: str | Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.session_id}_predictions.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved {len(self._predictions)} predictions to {path}")
        return path

    async def upload_to_cloudflare(self, api_url: str, access_token: str) -> bool:
        url = f"{api_url}/sessions/{self.session_id}/predictions"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, json=self.to_dict(), headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0)
            if resp.status_code in (200, 201):
                logger.info(f"Uploaded predictions for {self.session_id} to Cloudflare")
                return True
            else:
                logger.error(f"Upload failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return False
