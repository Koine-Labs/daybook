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
from .clusterer import run_clusterer
from .novelty import flag_for_reclustering, log_novelty_observation

__all__ = [
    "ActiveCluster",
    "flag_for_reclustering",
    "get_active_clusters",
    "log_novelty_observation",
    "run_clusterer",
]
