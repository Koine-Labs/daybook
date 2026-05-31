"""AblationBackend protocol + MacScaffoldBackend (v1) + DesktopGPUBackend slot (A6).

Compute is a swappable backend: the Mac scaffold runs deterministic numpy
combiners today; the desktop-GPU slot (JEPA encoder, #16) is a labeled stub
selected by config (ABLATION_BACKEND=desktop_gpu). Same Protocol → evaluate.py /
promote.py never change (commitment #9).
"""
from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from .combiners import fit_linear, reconstruct_linear
from .dataset import GradedPair
from .source_sets import SourceSet


@runtime_checkable
class AblationBackend(Protocol):
    def fit(
        self, axis: str, source_set: SourceSet, train: Sequence[GradedPair]
    ) -> Any: ...

    def reconstruct_belief(
        self, axis: str, source_set: SourceSet, pair: GradedPair, trained_params: Any
    ) -> Any: ...


def _scalar_truth(pair: GradedPair) -> float:
    v = pair.truth_value
    if isinstance(v, dict):
        v = v.get("value", 0.0)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class MacScaffoldBackend:
    """v1 backend — restrict the deterministic linear combiner to a source set.

    fit = least-squares weights over the restricted inputs; reconstruct = apply
    them to one sample. Pure numpy, CPU/MPS, no GPU, no LLM.
    """

    name = "mac_scaffold"

    def fit(
        self, axis: str, source_set: SourceSet, train: Sequence[GradedPair]
    ) -> list[float]:
        inputs = [p.belief_inputs for p in train]
        targets = [_scalar_truth(p) for p in train]
        return fit_linear(source_set, inputs, targets)

    def reconstruct_belief(
        self, axis: str, source_set: SourceSet, pair: GradedPair, trained_params: Any
    ) -> float:
        return reconstruct_linear(source_set, pair.belief_inputs, trained_params)


class DesktopGPUBackend:
    """DOCUMENTED SLOT (not built v1).

    When 4080 routing exists (ARCHITECTURE §7), this trains a small JEPA-family
    encoder (#16) over the source set and reconstructs belief from latent. Until
    wired it raises rather than silently fake a capability.
    """

    name = "desktop_gpu"

    def fit(self, axis: str, source_set: SourceSet, train: Sequence[GradedPair]) -> Any:
        raise NotImplementedError(
            "DesktopGPUBackend is a documented slot: JEPA encoder over source sets "
            "needs 4080 routing (not set up yet). Use ABLATION_BACKEND=mac_scaffold."
        )

    def reconstruct_belief(
        self, axis: str, source_set: SourceSet, pair: GradedPair, trained_params: Any
    ) -> Any:
        raise NotImplementedError("DesktopGPUBackend is a documented slot (see fit).")


def get_backend(name: str) -> AblationBackend:
    """Select a backend by config name."""
    if name == "mac_scaffold":
        return MacScaffoldBackend()
    if name == "desktop_gpu":
        return DesktopGPUBackend()
    raise ValueError(f"unknown ablation backend: {name!r}")
