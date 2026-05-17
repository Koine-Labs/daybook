"""FastAPI inference server with WebSocket endpoint for real-time sleep stage classification."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from auth import extract_token_from_header, validate_token
from classifier import Classifier
from config import Settings
from feature_engine import FeatureEngine
from schemas import (
    ErrorMessage,
    Prediction,
    SessionAck,
    StageProbabilities,
    parse_incoming,
)
from session_tracker import SessionTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()
app = FastAPI(title="Lullaby Inference Server")

classifier = Classifier(settings.model_path)

active_sessions: dict[str, WebSocket] = {}

LOGS_DIR = Path(__file__).parent / "logs"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": classifier.model is not None,
        "feature_count": len(classifier.feature_names),
        "env": settings.env,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    auth_header = ws.headers.get("authorization")
    token = extract_token_from_header(auth_header)
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")
        return

    try:
        user_id = validate_token(token, settings.jwt_secret)
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth token")
        return

    # Concurrent session guard
    if user_id in active_sessions:
        old_ws = active_sessions[user_id]
        try:
            await old_ws.close(code=status.WS_1000_NORMAL_CLOSURE, reason="New session started")
        except Exception:
            pass
        logger.info(f"Terminated old session for user {user_id}")

    await ws.accept()
    active_sessions[user_id] = ws
    logger.info(f"WebSocket connected: user={user_id}")

    tracker: SessionTracker | None = None
    engine = FeatureEngine(classifier.feature_names)

    try:
        while True:
            raw = await ws.receive_json()
            try:
                msg = parse_incoming(raw)
            except (ValueError, Exception) as e:
                await ws.send_json(ErrorMessage(message=str(e)).model_dump())
                continue

            if msg.type == "session_start":
                tracker = SessionTracker(
                    session_id=msg.session_id,
                    user_id=user_id,
                    started_at=msg.started_at,
                )
                engine = FeatureEngine(classifier.feature_names)
                ack = SessionAck(session_id=msg.session_id, user_id=user_id)
                await ws.send_json(ack.model_dump())
                logger.info(f"Session started: {msg.session_id}")

            elif msg.type == "sensor_epoch":
                features = engine.compute(msg.data.model_dump(), msg.timestamp)
                result = classifier.predict(features)

                pred = Prediction(
                    epoch_index=msg.epoch_index,
                    stage=result.stage,
                    confidence=result.confidence,
                    probabilities=StageProbabilities(**result.probabilities),
                )
                await ws.send_json(pred.model_dump())

                if tracker:
                    tracker.add_prediction(
                        epoch_index=msg.epoch_index,
                        timestamp=msg.timestamp,
                        stage=result.stage,
                        confidence=result.confidence,
                        probabilities=result.probabilities,
                    )

            elif msg.type == "session_end":
                if tracker:
                    await _save_predictions(tracker, user_token=token or "")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user_id}")
        if tracker:
            await _save_predictions(tracker, user_token=token or "")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        if tracker:
            await _save_predictions(tracker, user_token=token or "")
    finally:
        if active_sessions.get(user_id) is ws:
            del active_sessions[user_id]


async def _save_predictions(tracker: SessionTracker, user_token: str = "") -> None:
    if settings.env == "production" and settings.cloudflare_api_url and user_token:
        success = await tracker.upload_to_cloudflare(settings.cloudflare_api_url, user_token)
        if not success:
            tracker.save_local(LOGS_DIR)
    else:
        tracker.save_local(LOGS_DIR)
    logger.info(f"Saved {tracker.prediction_count} predictions for session {tracker.session_id}")
