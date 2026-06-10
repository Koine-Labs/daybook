# Daybook State Ledger — Design Spec

**Date:** 2026-06-01
**Status:** Approved (brainstorming complete; ready for implementation planning)
**Author:** Aakash Agrawal + Claude

---

## 1. Problem

Daybook's docs drift from reality. A 2026-06-01 reality audit found STATUS.md
claiming "601 passed / 1 skipped" (real: 569 / 0), a "~50-55% toward v3" table
that was wildly over-stated, and a "Regis is functionally complete from the neck
up" summary describing scrapped v0 surfaces. CLAUDE.md still documented deleted
apps and a broken Pi daemon as current. The root cause: **project state is
hand-written narrative**, so it drifts the moment code moves and nobody re-writes
the prose.

For a solo founder vibe-coding with AI across many parallel workstreams, trustworthy
state is the one safeguard — and it had quietly failed.

## 2. Goal

A **self-updating system of record** that:

1. **Kills drift** — current state is *derived from verifiable signals* (tests,
   code markers, module imports), not hand-typed claims.
2. **Maps progress vs vision** — shows how far each of the 16 architectural
   commitments and the vision pillars is from done, at a glance.
3. **Coordinates parallel work** — many concurrent workstreams (founder + AI
   agents) without collisions or architecture drift.
4. **Needs near-zero manual upkeep** — automation does the bookkeeping; the founder
   almost never hand-edits a status surface.

## 3. Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Scope | Unified: anti-drift + vision-progress + parallel-coordination |
| Source of truth | Derived from code + tests, captured in a machine-readable manifest |
| Overhead | Near-zero / automated |
| Alignment engine | Hybrid: machine-readable manifest + periodic AI audit |
| Visual feedback | Yes — a generated live dashboard (Approach C) |
| Dashboard hosting | **Cloudflare Pages + Cloudflare Access** (genuinely private, cross-device, reuses existing Cloudflare stack) |
| STATUS.md handling | Generated "current state" block at top + human-written dated history below |

## 4. Architecture

The single source of truth is a **manifest** in the repo. Everything human-facing
(STATUS.md current-state block, GitHub Issues/Project, the dashboard) is **generated**
from it. Humans and AI edit only the manifest; automated checks make the manifest
unable to lie about mechanical facts.

```
   code + tests
        │
        ├──> Verifier (CI, per-PR, no AI)  ── checks mechanical claims, fails on contradiction
        │
        └──> Auditor (scheduled AI workflow) ── re-derives judgment claims, opens PR + drift report
                          │
                          ▼
                    Manifest (docs/state/*.yaml)   ◄── single source of truth
                          │
                          ▼
                    Renderers (bin/state_render.py)
                     ├──> STATUS.md generated block
                     ├──> state.json (dashboard feed)
                     ├──> GitHub Issues / Project sync
                     └──> dashboard HTML ──> Cloudflare Pages + Access
```

### 4.1 The Manifest — `docs/state/`

Human- and AI-editable YAML, diffable in git. Split for clarity:

**`pillars.yaml`** — the strategic targets:
- `vision_pillars[]`: `{ id, name, description, centrality }` — seeded from the 14
  pillars in the 2026-06-01 audit.
- `commitments[]`: the 16 architectural commitments `{ id, title, rule_summary }`.

**`capabilities.yaml`** — what actually exists, one entry per real capability
(e.g. `l3_fusion_arc`, `rem_classifier`, `network_transport`, `real_mic_arc`,
`label_ledger`, `cold_start_arbitration`). Each entry:
```yaml
- id: rem_classifier
  name: "REM sleep nowcaster (XGBoost)"
  serves_pillars: [sleep_wedge, multimodal_fusion]
  serves_commitments: [16]
  build_state: built_and_runs        # built_and_runs | scaffold | code_only_unverified | absent
  alignment: partial                 # on_track | partial | drifting | not_started
  percent_done: 60
  gaps:
    - "Needs real biometric SignalPackets on the bus; no live producer wires Watch HR in yet"
    - "f1≈0.45 — may not clear the ≥50% dream-recall bar on real data"
  evidence:
    tests: ["prediction/test_*sleep*", "prediction/predictors/test_sleep_classifier*"]
    modules: ["prediction.predictors.sleep_classifier"]
    markers: ["scaffold:False expected in fusion/axes/state_declared.py"]
    key_files: ["classifier/models/production_binary_rem.json"]
```
The `evidence` block is what makes a claim *checkable* — the Verifier runs the tests,
imports the modules, and greps the markers to confirm `build_state`.

**`workstreams.yaml`** — active/planned parallel efforts:
```yaml
- id: first-real-signal
  title: "One real packet through the live arc (mic-first)"
  status: planned                    # planned | in_progress | blocked | done
  owns_paths: ["apps/inference/runtime/waking_arc.py", "apps/inference/voice/"]
  touches_commitments: [3, 11, 14]
  branch: null
  worktree: null
  github_issue: null
```
`owns_paths` enables collision detection when two workstreams touch the same files.

### 4.2 The Verifier — `bin/state_verify.py` (per-PR, no AI, no tokens)

Runs in CI on every PR. For each capability:
- Runs the referenced `tests` (DB-free/LLM-free, the established CI mode).
- Imports the referenced `modules`.
- Greps the `markers` (e.g. confirms `scaffold:True` is/ isn't present where claimed).
- Re-counts the full DB-free suite and compares to a recorded number.

**Fails CI** when the manifest contradicts the repo: claims `built_and_runs` but
tests fail; claims a scaffold was removed but the flag persists; the recorded test
count drifts (this is exactly what would have caught 601 vs 569). Also warns when
two `in_progress` workstreams share an `owns_paths` entry.

The Verifier checks only **mechanical** facts. It never touches the judgment fields
(`alignment`, `percent_done`, `gaps`).

### 4.3 The Auditor — scheduled AI workflow (the judgment layer)

The 2026-06-01 reality-audit workflow, formalized as a reusable Workflow script.
- **Cadence:** weekly cron + on-demand (manual dispatch / label).
- **What it does:** re-derives the judgment fields the Verifier can't — `alignment`,
  `percent_done`, `gaps` — by reading code and running probes, exactly as the
  one-off audit did. Diffs its findings against the current manifest.
- **Output:** opens a **PR** updating `capabilities.yaml` judgment fields, and posts
  a **drift report** ("manifest said X; reality is Y") as the PR body / an issue.
- It proposes; the founder merges. The manifest is never auto-mutated on `main`
  without a reviewable PR.

This is the token-costly layer, which is why it is periodic, not per-PR.

### 4.4 The Renderers — `bin/state_render.py`

Pure function: manifest → generated artifacts. Run in CI on merge to `main` (and
locally on demand). Outputs:
- **STATUS.md current-state block** — a clearly delimited, auto-generated section
  (between `<!-- STATE:BEGIN -->` / `<!-- STATE:END -->` markers) at the top of
  STATUS.md. The dated narrative history below the markers stays human-written.
  Re-rendering only ever touches between the markers.
- **`state.json`** — the data feed for the dashboard.
- **GitHub sync** — create/close Issues from `workstreams.yaml`; populate a Project
  board (best-effort, via `gh`/API). No manual board upkeep.

A CI check fails the PR if the committed generated artifacts are stale vs the manifest
(i.e. someone changed the manifest but didn't re-render) — keeping generated output
honest without trusting discipline.

### 4.5 The Dashboard — live visual feedback (Approach C)

A **static** HTML/CSS/JS page (no backend) reading `state.json`:
- Progress bars per vision pillar and per commitment, color-coded by `build_state`.
- Capability cards grouped by pillar, showing `alignment` + `percent_done` + gaps.
- Active workstreams with status.
- A **drift-over-time sparkline** — each Auditor run appends a dated snapshot to a
  small `history.jsonl`, so the dashboard shows progress trending up over weeks.
- "Last audited" + "last rendered" timestamps.

Regenerated on every push and every audit, so it is always current.

**Hosting: Cloudflare Pages + Cloudflare Access.**
- Static output deployed to a Cloudflare Pages project on push (CI step).
- Gated behind Cloudflare Access (Zero Trust) — founder login / email allowlist —
  so the dashboard is genuinely private and viewable cross-device, while the
  sensitive vision/strategy content is never publicly exposed.
- Reuses the existing Cloudflare account + domain; free tier suffices.
- **Note:** plain GitHub Pages was rejected because, on standard plans, a published
  Pages site is public even from a private repo.

### 4.6 Parallel coordination

- Each workstream entry ↔ a GitHub Issue (rendered).
- `owns_paths` lets the Verifier warn on file-ownership collisions between concurrent
  in-progress workstreams.
- Work happens in git worktrees, one per stream (matches existing repo convention;
  see the worktree-venv memory).
- The `theory-aligner` agent runs as a pre-merge gate that checks the change against
  the 16 commitments and updates the affected capability rows in the manifest as part
  of the PR.

## 5. Data flow (end to end)

1. Founder/AI makes a code change in a worktree for a workstream.
2. On PR: **Verifier** checks the manifest's mechanical claims still hold; the
   render-staleness check confirms generated artifacts match the manifest.
3. On merge to `main`: **Renderers** regenerate STATUS block, `state.json`, GitHub
   sync, and deploy the dashboard to Cloudflare Pages.
4. Weekly: **Auditor** re-derives judgment fields, opens a manifest-update PR + drift
   report; appends a snapshot to `history.jsonl`.
5. Founder watches progress live on the private dashboard; reviews/merges audit PRs.

## 6. Seed content

The manifest's first content is the 2026-06-01 audit itself:
- `pillars.yaml` ← the 14 vision pillars + 16 commitments.
- `capabilities.yaml` ← the audited capabilities with their `build_state` /
  `alignment` / `percent_done` / `gaps` (e.g. `l1_l6_arc` built_and_runs ~on_track;
  `jepa_predictor` scaffold/partial; `network_transport` scaffold/drifting (orphaned);
  `i_models_clustering` code_only/not_started; etc.).
- `workstreams.yaml` ← seeded with the two follow-ups already surfaced: doc-drift
  (done) and "first real signal through the arc".

## 7. File layout

```
docs/state/
  pillars.yaml
  capabilities.yaml
  workstreams.yaml
  history.jsonl            # appended by Auditor; dashboard trend source
  dashboard/              # static dashboard source (HTML/CSS/JS template)
  README.md               # how the ledger works; "edit the manifest, never the outputs"
bin/
  state_verify.py         # per-PR mechanical verifier
  state_render.py         # manifest -> STATUS block + state.json + GitHub + dashboard build
  state_audit.workflow.js # the formalized AI auditor (Workflow script)
.github/workflows/
  state-verify.yml        # per-PR: verifier + render-staleness check
  state-render.yml        # on merge to main: render + Cloudflare Pages deploy
  state-audit.yml         # weekly cron + manual dispatch: AI auditor
```

## 8. Testing strategy

- `bin/state_verify.py` and `bin/state_render.py` are pure-Python with unit tests
  (DB-free, deterministic). Test: a manifest with a deliberately false claim makes
  the Verifier exit non-zero; a correct manifest exits zero; the Renderer is
  idempotent (render twice = byte-identical) and only edits between STATUS markers.
- Dashboard render tested by snapshotting `state.json` → expected HTML structure.
- The Auditor workflow is validated by a dry-run that emits a manifest-diff without
  opening a PR.

## 9. Out of scope (YAGNI)

- Multi-user / team features (single founder).
- Real-time websockets dashboard ("live" = regenerate-on-push is enough).
- Two-way GitHub Project sync (one-way render → GitHub only; manifest stays canonical).
- Migrating existing CLAUDE.md repo-layout sections (separate cleanup; the banner
  fix on 2026-06-01 already neutralizes them).

## 10. Success criteria

- A false claim in the manifest fails CI (drift is mechanically impossible to merge).
- STATUS.md current-state block is generated and matches the repo.
- The private Cloudflare dashboard shows per-pillar/commitment progress and a drift
  trend, updating on push.
- The weekly Auditor opens a manifest-update PR with a drift report, unattended.
- Parallel workstreams are visible with collision warnings, needing no manual board.
