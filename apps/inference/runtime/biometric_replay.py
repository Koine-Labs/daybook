"""Off-CI real-data smoke: replay an imported sleep session onto the L1->L4 bus.

The first live biometric bus producer (#14): it reuses classifier.data to read a
labeled sleep session's bare-name readings (heart_rate/hrv/respiratory_rate/spo2)
from the DB, windows them with sensors.watch_adapter.window_readings, and pushes
each epoch window through a WatchBusSink(meta_context=SLEEP). The same packets
flow L2 (features.participant -> 24 REM features) -> L4 (prediction.
feature_participant -> a "rem" Prediction), exactly as a live watch satellite will
over NetworkTransport — WatchBusSink is transport-agnostic, so nothing here
changes when the real HealthKit stream lands (#9).

NOT on the CI path: it needs DATABASE_URL. Heavy/DB imports (classifier.data,
db) are done LAZILY inside the functions, so `import runtime.biometric_replay`
succeeds with no DATABASE_URL and no DB driver in the import graph (mirrors
runtime/waking_arc.py). Verified by the spec's import-clean check.

Run on the Mac (venv + live Neon creds in apps/inference/.env.local):
  cd apps/inference && python -m runtime.biometric_replay
"""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = INF_DIR.parent
for p in (str(INF_DIR), str(APPS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.bus.bus import TOPIC_PREDICTION, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope
from sensors.contract import DEFAULT_USER_ID
from sensors.watch_adapter import WatchBusSink, window_readings


def build_biometric_lane(bus: MessageBus | None = None) -> MessageBus:
    """Register the L2 biometric extractor + the L4 REM participant onto a bus.

    Imports the participants lazily so this module stays import-clean with no DB.
    """
    from features import participant as features_participant
    from prediction import feature_participant as prediction_participant

    bus = bus or MessageBus()
    features_participant.register(bus)        # L2: SignalPacket -> 24-feature FeatureSnapshot
    prediction_participant.register(bus)      # L4: FeatureSnapshot -> "rem" Prediction
    return bus


def replay_session(session_id: str, *, bus: MessageBus, user_id: str = DEFAULT_USER_ID) -> int:
    """Stream one labeled sleep session's readings onto the bus; return windows emitted.

    Lazy DB import: classifier.data is imported here, not at module load.
    """
    from classifier.data import load_session

    bundle = load_session(session_id)
    sensors = bundle.sensors
    readings = [
        {"recorded_at": row.recorded_at, "kind": row.kind, "value": float(row.value)}
        for row in sensors.itertuples(index=False)
    ]
    session_started_at = bundle.started_at.to_pydatetime()
    sink = WatchBusSink(bus, user_id=user_id, meta_context=MetaContext.SLEEP)

    n = 0
    for window in window_readings(readings):
        sink.emit_window(
            epoch_start_at=window["epoch_start_at"],
            readings=window["readings"],
            session_started_at=session_started_at,
            hr_mean_history=window["hr_mean_history"],
            user_id=user_id,
        )
        n += 1
    return n


def main() -> None:
    """Replay one recent labeled sleep session end-to-end as a real-data smoke."""
    from classifier.data import list_sessions

    sessions = list_sessions()
    if sessions.empty:
        print("No eligible labeled sleep sessions found.", flush=True)
        return
    top = sessions.sort_values("started_at").iloc[-1]
    session_id = str(top["id"])

    bus = build_biometric_lane()
    preds: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, preds.append)

    print(f"Replaying session {session_id} "
          f"({top['duration_seconds'] / 3600:.1f}h) onto the L1->L4 bus...", flush=True)
    n_windows = replay_session(session_id, bus=bus)

    rem_calls = [p for p in preds if p.payload.distribution["rem"] >= 0.23]
    print(f"  windows emitted : {n_windows}", flush=True)
    print(f"  rem predictions : {len(preds)}", flush=True)
    print(f"  P(REM)>=thresh  : {len(rem_calls)}", flush=True)
    if preds:
        last = preds[-1].payload
        print(f"  last P(REM)     : {last.distribution['rem']:.3f} "
              f"(meta={preds[-1].meta_context.value}, scope={preds[-1].consent_scope})",
              flush=True)


if __name__ == "__main__":
    main()
