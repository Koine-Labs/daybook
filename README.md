# Daybook

Daybook is Koine Labs' always-on AI empath prototype: a sensing and inference
system that turns body/environment signals into a live belief map Regis can act
on. The near-term MVP is a waking, distributed hardware rig: MacBook as the
inference hub, Raspberry Pi / ESP32 / EXG / mic / camera as sensor satellites.
Sleep and dream recall remain the long-term validation wedge, but the immediate
work is proving the live multimodal substrate.

## Current Shape

- `apps/inference/` — Python L1-L6 nervous-system stack: protocol, bus,
  sensors, feature extraction, fusion axes, prediction, decision, output.
- `apps/api/` — FastAPI bridge for future clients and local service calls.
- `apps/wisp/` — Regis persona and generative composer.
- `apps/recall/` — dream-recall capture path retained from the earlier wedge.
- `apps/pi/` — legacy Pi daemon surface; currently stale and scheduled to be
  rebuilt against `NetworkTransport` and the L1 sensor producers.
- `packages/shared/` — TypeScript mirror of shared protocol/entity types.
- `docs/` — positioning, architecture, status, runbook, and implementation specs.

Deleted/stale v0 surfaces such as `apps/ios`, `apps/chat`, `apps/inference/realtime.py`,
and `apps/inference/cue_decision.py` are intentionally gone after the May 2026
architecture rebuild. Use `docs/STATUS.md` as the operational source of truth.

## Verified Locally

From the repo root:

```bash
pnpm typecheck
```

From `apps/inference`:

```bash
.venv/bin/python -m pytest -q
```

Recent audit result: `307 passed` for the inference suite and TypeScript
typecheck green for `@daybook/shared`.

## Next Engineering Frontier

The code spine is ahead of the physical rig. The highest-leverage next work is:

1. Rebuild `apps/pi` as a real satellite that sends Daybook `SignalPacket`s over
   `NetworkTransport`.
2. Prove one EXG/mic/camera packet can travel Pi -> Mac -> L1-L6 pipeline.
3. Add cold-start calibration, self-report, and outcome logging so I-Models and
   learning loops have real data to grow from.

For product strategy, read `docs/POSITIONING.md`. For current operational state,
read `docs/STATUS.md`.
