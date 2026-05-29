"""Vision software lane — semantic-first scene extraction (commitment #11).

The edge (camera satellite) runs a detector over a frame and discards the raw
pixels; only a small `visual_scene` semantic packet rides the bus. `perception`
holds the canonical edge math both the off-CI edge stub and any real producer
call; `sensors.vision_adapter` is the transport-agnostic bus producer. Mirrors
the BCI lane (`bci.bandpower` + `sensors.eeg_adapter`).
"""
