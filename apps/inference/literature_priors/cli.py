"""Review/promote/list workflow: `python -m literature_priors.cli`.

Human-in-the-loop only. No auto-promotion. DB-touching imports are inside main()
so importing this module stays DB-free.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Literature-prior registry workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list priors")
    p_list.add_argument("--axis")
    p_list.add_argument("--status")

    sub.add_parser("load-seed", help="idempotently load the curated seed set")

    p_review = sub.add_parser("review", help="mark a candidate reviewed")
    p_review.add_argument("prior_id")
    p_review.add_argument("--reviewer", required=True)
    p_review.add_argument("--notes", default=None)

    p_promote = sub.add_parser("promote", help="run the promotion gate (reviewed -> live)")
    p_promote.add_argument("prior_id")
    p_promote.add_argument("--reviewer", required=True)
    p_promote.add_argument("--evidence-user-id", default=DEFAULT_USER_ID)
    p_promote.add_argument("--min-labels", type=int, default=20)
    p_promote.add_argument("--threshold", type=float, default=0.6)

    p_retire = sub.add_parser("retire", help="retire a prior")
    p_retire.add_argument("prior_id")
    p_retire.add_argument("--reviewer", required=True)
    p_retire.add_argument("--reason", required=True)

    args = parser.parse_args(argv)

    from .models import PriorStatus
    from .store import list_priors, retire_prior, review_prior

    if args.cmd == "list":
        status = PriorStatus(args.status) if args.status else None
        for p in list_priors(axis=args.axis, status=status):
            print(f"{p.id}  [{p.status.value:9}] {p.target_axis:16} {p.claim_summary}")
        return 0

    if args.cmd == "load-seed":
        from .load_seed import load_seed

        s, pr = load_seed()
        print(f"loaded {s} sources, {pr} priors")
        return 0

    if args.cmd == "review":
        ok = review_prior(UUID(args.prior_id), args.reviewer, args.notes)
        print("reviewed" if ok else "no row updated (DB absent or unknown id)")
        return 0 if ok else 1

    if args.cmd == "promote":
        from .gate import promote_prior

        promo = promote_prior(
            UUID(args.prior_id),
            reviewer=args.reviewer,
            evidence_user_id=UUID(args.evidence_user_id),
            min_labels=args.min_labels,
            threshold=args.threshold,
        )
        verdict = "PROMOTED to live" if promo.passed else "DENIED (stays reviewed)"
        print(f"{verdict}: score={promo.validation_score} n={promo.evidence_label_count}")
        return 0 if promo.passed else 2

    if args.cmd == "retire":
        ok = retire_prior(UUID(args.prior_id), args.reviewer, args.reason)
        print("retired" if ok else "no row updated")
        return 0 if ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
