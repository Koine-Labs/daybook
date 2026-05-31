# literature_priors — Literature-Prior Registry (commitment #17)

A curated, citation-backed store of **weak priors** mapping a sensor/feature condition
to a claimed value on a target axis (e.g. "RMSSD decrease -> arousal increase, healthy
adults"). Each prior carries everything #17 demands: target axis, the rule, citation,
population, confidence, and **known limitations**. This package is a *producer and
reader* of the frozen `labels/` ledger — it never forks or alters it.

## Honesty statement (no scraping)

This registry is a **small, hand-curated seed set plus a human gate** — NOT a crawler.

- The corpus under `seed/corpus/` is local, committed, and hand-selected. `extract.py`
  imports **no HTTP client** and performs no network IO; its path guard refuses any
  `corpus_dir` outside `seed/`.
- LLM extraction (`propose_candidates_from_corpus`) is **dry-run by default** and only
  *proposes* candidates. A human reviews/edits before `register_candidate`.
- A candidate becomes **live** only after `promote_prior` validates it against real
  ledger evidence (ground-truth / self-report / observed-outcome). A prior that can't
  be validated stays `reviewed`. Auto-promotion is forbidden.
- Literature priors sit at the **weakest** rung of `labels.TRUST_ORDER` and are always
  emitted with their source tag, confidence, and population attached — never disguised.

## Lifecycle

```
candidate --review_prior--> reviewed --promote_prior(gate)--> live --retire_prior--> retired
```

Seeds load at `reviewed` (a human curated them) but still must pass the gate to go live.

## Layout

- `models.py` — typed models; #17 invariants enforced in `__post_init__`.
- `rules.py` — PURE `evaluate_rule` (no DB/LLM/network); the unit-test heart.
- `store.py` / `store_promotions.py` — crash-safe DB CRUD over migration 0012.
- `gate.py` — promotion gate (`validate_against_ledger` + `promote_prior`); reads the
  ledger, never writes it.
- `consume.py` — `priors_for`, `weak_supervision_for`, `materialize_prior`,
  `applies_to_user`.
- `emit.py` — the ONLY function that writes a weak label into the ledger
  (`source=LITERATURE_PRIOR`, full provenance round-tripped).
- `extract.py` — human-reviewable LLM candidate proposer (dry-run default, path guard).
- `seed/` — `sources.json`, `seed_priors.json`, `corpus/*.txt`; `load_seed.py` is
  idempotent.
- `cli.py` — `python -m literature_priors.cli {list,load-seed,review,promote,retire}`.

## Run

```bash
cd apps/inference && source .venv/bin/activate
# CI-safe pure tests (no DATABASE_URL, no LLM):
env -u DATABASE_URL python -m pytest literature_priors/ -q
# DB+LLM smoke (requires DATABASE_URL + migration 0012 applied):
python -m literature_priors.smoke_test
```

## Consumption (NOT wired here — controller's job)

`priors_for` / `weak_supervision_for` are designed to feed cold-start (#4) and L3
fusion / L4 training as down-weighted, source-tagged inputs, plus the #5 leave-one-
source-out fusion-ablation hook. Wiring those call sites is left to the controller.
