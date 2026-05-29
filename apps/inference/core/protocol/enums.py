# apps/inference/core/protocol/enums.py
"""Enumerations used across the message protocol. All str-valued for clean JSON."""
from __future__ import annotations

from enum import Enum


class NodeRole(str, Enum):
    """Eventual physical home of a component in the distributed system."""

    WISP_EDGE = "wisp_edge"
    PHONE_RELAY = "phone_relay"
    DESKTOP_COMPUTE = "desktop_compute"
    CLOUD = "cloud"


class MetaContext(str, Enum):
    """Top-level context that biases every layer (commitment #14)."""

    WAKING = "waking"
    SLEEP = "sleep"
    UNKNOWN = "unknown"


class Modality(str, Enum):
    """Signal type at the L1 boundary (commitment #10, modality axis)."""

    VOICE = "voice"
    TEXT = "text"
    GESTURE = "gesture"
    BIOMETRIC = "biometric"
    AUDIO = "audio"
    VISION = "vision"
    BCI = "bci"


class Intent(str, Enum):
    """Communication-intent at the L1 boundary (commitment #10, intent axis)."""

    EXPLICIT = "explicit"
    CONTINUOUS = "continuous"


class PayloadType(str, Enum):
    """Discriminator naming which layer boundary an envelope's payload crosses."""

    SIGNAL = "signal"        # L1 -> L2
    FEATURE = "feature"      # L2 -> L3
    BELIEF = "belief"        # L3 -> L4
    PREDICTION = "prediction"  # L4 -> L5
    ACTION = "action"        # L5 -> L6
    OUTPUT = "output"        # L6 -> channel
