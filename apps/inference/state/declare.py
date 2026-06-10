"""Orchestrates the state_declared lane: L1->L2->L3 + label-ledger writes + CLI.

`assemble_declaration_arc(bus)` wires the standard L2/L3 bus participants and a
TOPIC_BELIEF subscriber that (a) writes one self_report LabelRecord per claim and
(b) persists the state_declared belief. `declare_state(text, ...)` runs the whole
arc in-process synchronously for the CLI / API / tests.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_BELIEF, MessageBus  # noqa: E402
from core.protocol.payloads import BeliefState  # noqa: E402
from features import participant as features_participant  # noqa: E402
from fusion import participant as fusion_participant  # noqa: E402
from fusion.axes import state_declared as l3_state_declared  # noqa: E402
from fusion.writer import write_axis_estimate  # noqa: E402
from labels import LabelRecord, LabelSource, canonical_axis  # noqa: E402
from labels import ledger as labels_ledger  # noqa: E402
from sensors.contract import DEFAULT_USER_ID  # noqa: E402
from sensors.declare_adapter import CONSENT_SCOPE, DeclarationBusSink  # noqa: E402

AXIS = l3_state_declared.AXIS


def _calibration_reader():
    """The L3 calibration read seam (#4): arbitration.get_calibration, lazily imported."""
    from arbitration import get_calibration

    return get_calibration


def _recompute_axis(user_id: str, axis: str) -> None:
    """Trigger cold-start arbitration recompute for one axis (#4); crash-safe.

    Imported lazily so this module's import stays DB-free; the one-way dependency
    is arbitration -> labels (never the reverse), so calling it here keeps the
    ledger free of any arbitration import.
    """
    from arbitration import recompute_axis

    recompute_axis(user_id, axis)


def _build_records(belief: BeliefState) -> list[LabelRecord]:
    """One self_report LabelRecord per declared claim, keyed to the inferred axis."""
    est = belief.estimates.get(AXIS)
    if est is None:
        return []
    raw_text = est.value.get("raw_text", "")
    classifier = est.value.get("classifier")
    records: list[LabelRecord] = []
    for claim in est.value.get("claims", []):
        records.append(
            LabelRecord(
                user_id=belief.user_id,
                axis=canonical_axis(claim["axis"]),  # join to the inferred axis (#5)
                value=claim["value"],
                source=LabelSource.SELF_REPORT,
                observed_at=est.timestamp,
                confidence=float(claim.get("confidence", 1.0)),
                provenance={"declaration_text": raw_text, "classifier": classifier},
                consent_scope=CONSENT_SCOPE,
                i_model_id=est.i_model_id,  # carry-through (#1); None until clustering
                meta_context=est.meta_context,
            )
        )
    return records


def record_self_report_labels(
    env: Any,
    *,
    persist: bool = True,
    sink: list[LabelRecord] | None = None,
    counter: list[int] | None = None,
) -> list[LabelRecord]:
    """On a belief carrying state_declared: write per-claim labels + persist the belief.

    Returns the LabelRecords it built (also appended to `sink` if given) so callers
    can assert without a DB. When `persist` is False, no DB writes happen. The
    persist path writes labels ATOMICALLY via record_labels; the actual written
    count (what record_labels returns) is appended to `counter` when given so the
    reported count reflects reality, not just len(records).
    """
    belief = getattr(env, "payload", None)
    if not isinstance(belief, BeliefState):
        return []
    est = belief.estimates.get(AXIS)
    if est is None or est.source != LabelSource.SELF_REPORT.value:
        return []
    records = _build_records(belief)
    if sink is not None:
        sink.extend(records)
    if persist:
        written = labels_ledger.record_labels(records)
        write_axis_estimate(belief.user_id, est)
        for axis in dict.fromkeys(r.axis for r in records):  # distinct, order-stable
            try:
                _recompute_axis(belief.user_id, axis)
            except Exception:  # noqa: BLE001 — recompute is best-effort; the label write already committed.
                pass
    else:
        written = len(records)
    if counter is not None:
        counter.append(written)
    return records


def assemble_declaration_arc(
    bus: MessageBus,
    *,
    persist: bool = True,
    sink: list[LabelRecord] | None = None,
    counter: list[int] | None = None,
) -> None:
    """Register the L2 extractor, the L3 axis, and the self-report belief subscriber."""
    features_participant.register(bus)
    fusion_participant.register(bus, calibration_reader=_calibration_reader())
    bus.subscribe(
        TOPIC_BELIEF,
        lambda env: record_self_report_labels(env, persist=persist, sink=sink, counter=counter),
    )


def declare_state(
    text: str,
    *,
    user_id: str = DEFAULT_USER_ID,
    persist: bool = True,
    offline: bool = False,
) -> dict[str, Any]:
    """Run the in-process declaration arc synchronously; return a small result dict."""
    bus = MessageBus()
    sink: list[LabelRecord] = []
    counter: list[int] = []
    assemble_declaration_arc(bus, persist=persist, sink=sink, counter=counter)

    beliefs: list[BeliefState] = []
    bus.subscribe(
        TOPIC_BELIEF,
        lambda env: beliefs.append(env.payload) if isinstance(env.payload, BeliefState) else None,
    )

    prev = os.environ.get("DAYBOOK_DECLARE_OFFLINE")
    if offline:
        os.environ["DAYBOOK_DECLARE_OFFLINE"] = "1"
    try:
        DeclarationBusSink(bus, user_id=user_id).declare(text)
    finally:
        if offline:
            if prev is None:
                os.environ.pop("DAYBOOK_DECLARE_OFFLINE", None)
            else:
                os.environ["DAYBOOK_DECLARE_OFFLINE"] = prev

    est = beliefs[-1].estimates.get(AXIS) if beliefs else None
    if est is not None and est.source != LabelSource.SELF_REPORT.value:
        est = None  # the OFFLINE sentinel is not a real declaration (garbled/empty text).
    claims = est.value.get("claims", []) if est is not None else []
    classifier = est.value.get("classifier") if est is not None else None
    return {
        "axis": est.axis if est is not None else None,
        "claims": claims,
        "raw_text": text,
        "classifier": classifier,
        "labels": sum(counter),  # ACTUAL written count (record_labels return), not len(sink)
        "persisted": persist and est is not None,
    }


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Declare your current state to Regis.")
    parser.add_argument("text", help="the state declaration, e.g. \"I'm locked in\"")
    parser.add_argument("--offline", action="store_true", help="force the offline lexicon")
    parser.add_argument("--user", default=DEFAULT_USER_ID, help="user id override")
    return parser.parse_args()


def main() -> None:
    """CLI entry: declare a state and print the parsed result."""
    args = _parse_args()
    result = declare_state(args.text, user_id=args.user, offline=args.offline)
    print(result)


if __name__ == "__main__":
    main()
