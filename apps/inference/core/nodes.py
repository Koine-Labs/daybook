# apps/inference/core/nodes.py
"""Node-role body map: where each component eventually runs.

Today every role runs in one process (the Mac). This map is the destination
written as code and is what a future NetworkTransport will route by. Generalizes
apps/AI_PI_CONTRACT.md across four nodes.
"""
from __future__ import annotations

from core.protocol.enums import NodeRole

PLACEMENT: dict[str, NodeRole] = {
    "L1.capture": NodeRole.WISP_EDGE,
    "L2.features": NodeRole.WISP_EDGE,
    "L3.fusion": NodeRole.DESKTOP_COMPUTE,
    "L4.prediction": NodeRole.DESKTOP_COMPUTE,
    "L5.decision": NodeRole.DESKTOP_COMPUTE,
    "L6.output": NodeRole.WISP_EDGE,
    "llm": NodeRole.CLOUD,
    "embeddings": NodeRole.DESKTOP_COMPUTE,
}


def role_for(component: str) -> NodeRole:
    """Return the eventual NodeRole of a component; raise KeyError if unmapped."""
    try:
        return PLACEMENT[component]
    except KeyError as exc:
        raise KeyError(f"no node-role placement for component {component!r}") from exc
