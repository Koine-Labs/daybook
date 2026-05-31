"""extract.py — stubbed ChatClient + path-guard + no-HTTP-import. DB-free, LLM-free."""
from __future__ import annotations

from pathlib import Path

import pytest

from literature_priors import extract
from literature_priors.extract import SEED_ROOT, propose_candidates_from_corpus
from literature_priors.models import PriorOrigin, PriorStatus


class StubClient:
    """Mimics the real ChatClient.chat_structured: validates a canned dict into the
    Pydantic `schema` and returns the INSTANCE (not a raw dict). No network."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple] = []

    def chat_structured(self, *, system: str, user: str, schema):
        self.calls.append((system, user, schema))
        return schema.model_validate(self.payload)


_VALID_PAYLOAD = {
    "priors": [
        {
            "target_axis": "arousal_inferred",
            "rule": {
                "feature": "hrv_rmssd",
                "modality": "biometric",
                "operator": "decrease",
                "threshold": None,
                "window_s": 60,
                "claim": {"axis": "arousal_inferred", "direction": "increase", "magnitude": "weak"},
                "context_gate": {"meta_context": "waking"},
            },
            "claim_summary": "RMSSD decrease -> arousal increase",
            "population": "healthy adults",
            "confidence": 0.4,
            "known_limitations": "motion confound",
            "extracted_excerpt": "RMSSD fell during stress.",
        }
    ]
}


def test_proposes_candidates_as_bootstrap_candidates(tmp_path) -> None:
    corpus = SEED_ROOT / "corpus"
    client = StubClient(_VALID_PAYLOAD)
    out = propose_candidates_from_corpus(corpus, ["arousal_inferred"], client, dry_run=True)
    assert len(out) == 1
    p = out[0]
    assert p.origin is PriorOrigin.LLM_LITERATURE_BOOTSTRAP
    assert p.status is PriorStatus.CANDIDATE
    assert p.target_axis == "arousal_inferred"
    assert client.calls, "the LLM client must have been invoked"


def test_dry_run_does_not_persist() -> None:
    corpus = SEED_ROOT / "corpus"
    client = StubClient(_VALID_PAYLOAD)
    # No store injection / DB needed: dry_run must not even attempt a write.
    out = propose_candidates_from_corpus(corpus, ["arousal_inferred"], client, dry_run=True)
    assert out  # returned but not persisted (no exception, no DB)


def test_path_guard_rejects_escape() -> None:
    client = StubClient(_VALID_PAYLOAD)
    with pytest.raises(ValueError, match="seed/ tree"):
        propose_candidates_from_corpus(Path("/etc"), ["arousal_inferred"], client)


def test_malformed_candidate_is_skipped() -> None:
    bad = {"priors": [{"target_axis": "arousal_inferred"}]}  # missing rule etc.
    client = StubClient(bad)
    out = propose_candidates_from_corpus(
        SEED_ROOT / "corpus", ["arousal_inferred"], client, dry_run=True
    )
    assert out == []


def test_claim_axis_mismatch_skipped() -> None:
    mismatch = {
        "priors": [
            {
                "target_axis": "arousal_inferred",
                "rule": {
                    "feature": "hrv_rmssd",
                    "operator": "decrease",
                    "claim": {"axis": "cognitive_load", "direction": "increase"},
                },
                "claim_summary": "x",
                "population": "adults",
                "confidence": 0.3,
                "known_limitations": "y",
            }
        ]
    }
    client = StubClient(mismatch)
    out = propose_candidates_from_corpus(
        SEED_ROOT / "corpus", ["arousal_inferred"], client, dry_run=True
    )
    assert out == []


def test_module_imports_no_http_client() -> None:
    src = Path(extract.__file__).read_text(encoding="utf-8")
    for banned in (
        "import requests",
        "import httpx",
        "import urllib.request",
        "import urllib",
        "import aiohttp",
        "from requests",
        "from httpx",
        "from aiohttp",
    ):
        assert banned not in src, f"extract.py must import no HTTP client; found {banned!r}"
