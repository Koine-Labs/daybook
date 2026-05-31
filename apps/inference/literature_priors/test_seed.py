"""Seed-data integrity: every seed prior satisfies the #17 model invariants. DB-free."""
from __future__ import annotations

import json
from pathlib import Path

from literature_priors.load_seed import SEED_DIR, load_seed_priors
from literature_priors.models import PriorOrigin, PriorStatus


def test_all_seed_priors_validate() -> None:
    priors = load_seed_priors()
    assert 6 <= len(priors) <= 12
    for p in priors:
        assert p.origin is PriorOrigin.SEED
        assert p.status is PriorStatus.REVIEWED
        assert p.rule.claim.axis == p.target_axis
        assert 0.0 <= p.confidence <= 1.0
        assert p.known_limitations.strip()
        assert p.population.strip()
        assert p.citation


def test_every_seed_prior_references_a_known_source() -> None:
    sources = json.loads((SEED_DIR / "sources.json").read_text(encoding="utf-8"))
    citations = {s["citation"] for s in sources}
    for p in load_seed_priors():
        assert p.citation in citations, f"unknown source citation: {p.citation}"


def test_seed_corpus_files_exist_and_are_local() -> None:
    sources = json.loads((SEED_DIR / "sources.json").read_text(encoding="utf-8"))
    for s in sources:
        cp = s.get("corpus_path")
        if cp is None:
            continue
        resolved = SEED_DIR / "corpus" / Path(cp).name
        assert resolved.exists(), f"missing corpus excerpt: {resolved}"


def test_corpus_dir_has_excerpts() -> None:
    excerpts = list((SEED_DIR / "corpus").glob("*.txt"))
    assert len(excerpts) >= 5
