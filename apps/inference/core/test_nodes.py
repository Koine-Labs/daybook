# apps/inference/core/test_nodes.py
import pytest

from core.nodes import PLACEMENT, role_for
from core.protocol.enums import NodeRole


def test_every_layer_has_a_placement():
    for component in ("L1.capture", "L2.features", "L3.fusion",
                      "L4.prediction", "L5.decision", "L6.output"):
        assert isinstance(role_for(component), NodeRole)


def test_heavy_compute_lives_on_desktop():
    assert role_for("L4.prediction") == NodeRole.DESKTOP_COMPUTE
    assert role_for("embeddings") == NodeRole.DESKTOP_COMPUTE


def test_llm_lives_in_cloud_and_capture_on_wisp():
    assert role_for("llm") == NodeRole.CLOUD
    assert role_for("L1.capture") == NodeRole.WISP_EDGE


def test_unknown_component_raises():
    with pytest.raises(KeyError):
        role_for("nope")
    assert PLACEMENT  # map is non-empty
