"""Self-expanding I-Model machinery.

Three layers:
  - clusterer.run_clusterer(): discover/update clusters from accumulated embeddings
  - activator.get_active_clusters(): "which I-Models are firing right now?"
  - novelty.log_novelty_observation(): buffer states that don't fit existing clusters

See migrations 0002 and 0003 for the underlying schema. The architectural
commitment is that I-Models are discovered from data (HDBSCAN over BGE-M3
embeddings) rather than pre-defined.
"""

from .activator import ActiveCluster, get_active_clusters
from .cluster_labeler import label_cluster, label_unlabeled_clusters
from .clusterer import run_clusterer
from .novelty import flag_for_reclustering, log_novelty_observation
from .regis_self_projector import RegisSelfFingerprint, refresh_regis_self
from .substrate import SubstrateContext, gather_substrate

__all__ = [
    "ActiveCluster",
    "RegisSelfFingerprint",
    "SubstrateContext",
    "flag_for_reclustering",
    "gather_substrate",
    "get_active_clusters",
    "label_cluster",
    "label_unlabeled_clusters",
    "log_novelty_observation",
    "refresh_regis_self",
    "run_clusterer",
]
