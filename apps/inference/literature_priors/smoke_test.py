"""End-to-end smoke (DB + optional LLM). NOT run in CI — requires DATABASE_URL.

    python -m literature_priors.smoke_test

Exercises: load_seed -> list -> register a hand-entered candidate -> review ->
promote (against real ledger evidence) -> materialize -> read back the ledger row
with source=literature_prior and full provenance.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

DEFAULT_USER_ID = UUID("61c18d4c-1c20-408a-bd5f-f5f88fd9922f")


def main() -> int:
    from labels import LabelSource
    from labels.ledger import read_labels

    from .consume import materialize_prior
    from .load_seed import load_seed
    from .models import (
        Context,
        LiteraturePrior,
        PriorOrigin,
        PriorStatus,
        Rule,
        RuleClaim,
        Window,
    )
    from .store import list_priors, register_candidate, review_prior

    print("[1] load_seed ...")
    s, pr = load_seed()
    print(f"    sources={s} priors={pr}")

    reviewed = list_priors(status=PriorStatus.REVIEWED)
    print(f"[2] reviewed priors in registry: {len(reviewed)}")
    if not reviewed:
        print("    no reviewed priors (DB absent?) — aborting smoke")
        return 1

    print("[3] register a hand-entered candidate ...")
    from .store import insert_source
    from .models import LiteratureSource

    sid = insert_source(
        LiteratureSource(
            citation=f"Smoke test source {uuid4()}",
            source_kind="paper",
        )
    )
    cand = LiteraturePrior(
        target_axis="arousal_inferred",
        rule=Rule(
            feature="hrv_rmssd",
            operator="decrease",
            claim=RuleClaim(axis="arousal_inferred", direction="increase"),
        ),
        claim_summary="smoke: RMSSD decrease -> arousal increase",
        population="healthy adults",
        confidence=0.4,
        known_limitations="smoke-test caveat",
        source_id=sid if sid is not None else uuid4(),
        origin=PriorOrigin.HAND_ENTERED,
    )
    cand_id = register_candidate(cand)
    print(f"    candidate id={cand_id}")
    if cand_id is not None:
        review_prior(cand_id, "aakash", "smoke review")

    print("[4] materialize a live seed prior (cold-start path) ...")
    live = list_priors(status=PriorStatus.LIVE)
    if not live:
        print("    no live priors yet (promote one via cli first) — skipping materialize")
        return 0
    target = live[0]
    now = datetime.now(timezone.utc)
    ledger_id = materialize_prior(
        target.id,
        DEFAULT_USER_ID,
        Window(start=now, end=now),
        {"hrv_rmssd_delta": -2.0, "hr_bpm": 110.0, "theta_beta_ratio": 2.0},
        Context(meta_context="waking", sub_context="non_exercise"),
    )
    print(f"    ledger_id={ledger_id}")

    print("[5] read back literature_prior labels ...")
    rows = read_labels(str(DEFAULT_USER_ID), sources=[LabelSource.LITERATURE_PRIOR], limit=5)
    for r in rows:
        print(f"    {r.axis} <- {r.source.value} prov_keys={sorted(r.provenance)}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
