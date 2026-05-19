"""Self-expanding I-Model machinery.

Five layers:
  - clusterer.run_clusterer(): discover/update clusters from accumulated embeddings
  - activator.get_active_clusters(): "which I-Models are firing right now?"
  - novelty.log_novelty_observation(): buffer states that don't fit existing clusters
  - mode_decider.decide_mode(): Witness vs Companion vs Neutral from live state
  - regis_self.read_regis_self(): snapshot of who Regis currently is

See migrations 0002 and 0003 for the underlying schema. The architectural
commitment is that I-Models are discovered from data (HDBSCAN over BGE-M3
embeddings) rather than pre-defined.
"""

from .activator import ActiveCluster, get_active_clusters
from .clusterer import run_clusterer
from .mode_decider import ModeDecision, decide_mode, derive_mode_for_chat
from .novelty import flag_for_reclustering, log_novelty_observation
from .regis_self import RegisSelf, read_regis_self, refresh_regis_self_cluster

__all__ = [
    "ActiveCluster",
    "ModeDecision",
    "RegisSelf",
    "decide_mode",
    "derive_mode_for_chat",
    "flag_for_reclustering",
    "get_active_clusters",
    "log_novelty_observation",
    "read_regis_self",
    "refresh_regis_self_cluster",
    "run_clusterer",
]
