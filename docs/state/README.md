# Daybook State Ledger

This directory is the **single source of truth** for project state. Edit the
manifest here; everything else (the STATUS.md "Current state" block, `state.json`,
the dashboard, GitHub issues) is **generated** — never edit generated outputs by hand.

## Files
- `pillars.yaml` — vision pillars + the 16 architectural commitments.
- `capabilities.yaml` — `expected_test_count` + every real capability with
  build_state / alignment / percent_done / gaps / evidence.
- `workstreams.yaml` — active/planned parallel efforts (with `owns_paths`).
- `state.json` — generated dashboard feed (do not edit).

## Commands (from `apps/inference`, venv active, DATABASE_URL unset)
- `python -m state_ledger.verify` — fails if the manifest's mechanical claims
  (module imports, code markers, test count, workstream collisions) don't match the repo.
- `python -m state_ledger.render` — regenerates the STATUS.md block + `state.json`.

## How drift is prevented
- The **verifier** runs in CI per-PR: a false mechanical claim fails the build.
- The **render-staleness check** fails CI if generated outputs don't match the manifest.
- Judgment fields (alignment / percent_done / gaps) are re-derived by the periodic
  AI **auditor** (separate plan), which proposes manifest updates via PR.

## Adding a capability
Add an entry to `capabilities.yaml` with real `evidence` (modules that import,
markers that exist). Run `verify` then `render`, and commit both.
