# apps/inference/core/protocol/test_enums.py
from core.protocol.enums import Intent, MetaContext, Modality, NodeRole, PayloadType


def test_enum_values_are_json_friendly_strings():
    assert NodeRole.WISP_EDGE.value == "wisp_edge"
    assert MetaContext.WAKING.value == "waking"
    assert Modality.BCI.value == "bci"
    assert Intent.CONTINUOUS.value == "continuous"
    assert PayloadType.SIGNAL.value == "signal"


def test_payload_type_covers_six_layer_boundaries():
    assert {p.value for p in PayloadType} == {
        "signal", "feature", "belief", "prediction", "action", "output"
    }


def test_modality_covers_commitment_10_set():
    assert {m.value for m in Modality} == {
        "voice", "text", "gesture", "biometric", "audio", "vision", "bci"
    }
