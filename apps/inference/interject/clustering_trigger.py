"""Nightly I-Model clustering trigger.

Fires once daily (default 04:00 local) to run HDBSCAN over the user's accumulated
embeddings, discover/refresh I-Model clusters, and write embedding_cluster_memberships
rows. This is the self-expansion loop for architectural commitment #6 — I-Models
are DISCOVERED from data, not predefined.

Triggers must NEVER raise. On failure we log and return an error dict so the
scheduler keeps running.
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from imodels.clusterer import run_clusterer  # noqa: E402

from .triggers import register  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

USER_SELF_SOURCE_TYPES = ["chat_message", "regis_observation", "dream_recall", "intent", "mood"]
REGIS_OF_USER_SOURCE_TYPES = ["regis_observation"]

MIN_CLUSTER_SIZE = 4
MIN_EMBEDDINGS = 20


@register("nightly_clustering")
def run_nightly_clustering(
    user_id: str = DEFAULT_USER_ID,
    *,
    model_owner: str = "user_self",
) -> dict:
    """Run the nightly clusterer for (user, model_owner). Never raises.

    Returns:
        {
          "clusters_created": int,
          "memberships_written": int,
          "model_owner": str,
          "skipped_reason": str | None,
          "input_embeddings": int,
          "noise_points": int,
          "discovered": int,
          "updated": int,
        }
    """
    try:
        if model_owner == "user_self":
            source_types = USER_SELF_SOURCE_TYPES
        elif model_owner == "regis_of_user":
            source_types = REGIS_OF_USER_SOURCE_TYPES
        else:
            return {
                "clusters_created": 0,
                "memberships_written": 0,
                "model_owner": model_owner,
                "skipped_reason": f"unsupported_model_owner:{model_owner}",
            }

        summary = run_clusterer(
            user_id,
            model_owner=model_owner,
            source_types=source_types,
            min_cluster_size=MIN_CLUSTER_SIZE,
            min_embeddings=MIN_EMBEDDINGS,
        )

        if summary.get("skipped"):
            return {
                "clusters_created": 0,
                "memberships_written": 0,
                "model_owner": model_owner,
                "skipped_reason": summary.get("reason"),
                "input_embeddings": summary.get("have", 0),
            }

        return {
            "clusters_created": int(summary.get("discovered", 0)),
            "memberships_written": int(summary.get("total_embeddings_clustered", 0)),
            "model_owner": model_owner,
            "skipped_reason": None,
            "input_embeddings": int(summary.get("input_embeddings", 0)),
            "noise_points": int(summary.get("noise_points", 0)),
            "discovered": int(summary.get("discovered", 0)),
            "updated": int(summary.get("updated", 0)),
        }
    except Exception as e:
        logger.warning("nightly_clustering failed: %s", e)
        traceback.print_exc()
        return {
            "clusters_created": 0,
            "memberships_written": 0,
            "model_owner": model_owner,
            "skipped_reason": f"error:{e}",
        }


def _main() -> int:
    ap = argparse.ArgumentParser(prog="clustering_trigger")
    ap.add_argument("--user-id", default=DEFAULT_USER_ID)
    ap.add_argument(
        "--model-owner",
        default="user_self",
        choices=["user_self", "regis_of_user"],
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    result = run_nightly_clustering(args.user_id, model_owner=args.model_owner)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["run_nightly_clustering"]
