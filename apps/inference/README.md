# @daybook/inference

Python AI pipeline for Daybook. FastAPI inference server at the package root, plus the offline analysis suite under `analysis/`.

Migrated from `Lullaby/inference/` (FastAPI server) and `Lullaby/analysis/` (offline ML pipeline).

## Scope

- **FastAPI inference server** (root) — real-time sleep stage classification over WebSocket, JWT auth, session tracking, XGBoost classifier with planned LSTM/Transformer upgrade path.
- **Analysis suite** (`analysis/`) — Python package (`lullaby/`) for offline feature engineering, multi-session ML training, evaluation (SHAP, confusion matrix, REM onset latency), and model export (joblib + CoreML). 233 tests in `analysis/tests/`.
- **Planned additions** — cue selection algorithm and wisp utterance generation will live here as additional modules.

## Layout

```
apps/inference/
├── main.py                 FastAPI app
├── classifier.py           XGBoost wrapper
├── feature_engine.py       Real-time feature engineering
├── session_tracker.py      Per-session state
├── auth.py / schemas.py / config.py
├── models/                 Serialized classifiers
├── tests/                  Server tests
├── pyproject.toml          Python workspace config
└── analysis/               Offline analysis package (233 tests)
    ├── lullaby/            Python package
    ├── tests/
    ├── notebooks/
    └── data/
```

## Development

```bash
# (no install commands run yet — workspace setup pending)
# Once installed:
uvicorn main:app --reload                    # run inference server
cd analysis && python3 -m pytest -v          # run analysis tests
```
