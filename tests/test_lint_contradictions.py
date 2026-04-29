"""
Tests for the deep semantic contradiction detection feature (#98).

All LLM calls are mocked via the _llm_caller injection parameter so the
tests never hit a real HTTP endpoint. Embeddings are injected as plain
Python lists so the embedder HTTP call is also bypassed.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

from palinode.core.config import config
from palinode.lint.contradictions import (
    DEFAULT_MAX_LLM_CALLS,
    DEFAULT_SIMILARITY_THRESHOLD,
    _cosine_similarity,
    _parse_llm_verdict,
    run_deep_contradiction_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_decision(directory: "os.PathLike[str]", name: str, entities: list[str], body: str) -> None:
    """Write a minimal Decision markdown file."""
    ents_yaml = "\n".join(f"  - {e}" for e in entities)
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"---\n"
            f"id: {name.replace('.md', '')}\n"
            f"type: Decision\n"
            f"category: decisions\n"
            f"status: active\n"
            f"entities:\n{ents_yaml}\n"
            f"---\n\n"
            f"{body}\n"
        )


def _high_sim_embedding_pair() -> tuple[list[float], list[float]]:
    """Return two embeddings with cosine similarity == 1.0 (identical)."""
    vec = [0.5, 0.5, 0.5, 0.5]
    return vec, vec


def _low_sim_embedding_pair() -> tuple[list[float], list[float]]:
    """Return two embeddings with cosine similarity == 0.0 (orthogonal)."""
    return [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]


def _make_llm_caller(verdict: str, explanation: str = "explanation sentence."):
    """Return a fake _llm_caller that always returns the given verdict."""
    call_count = [0]

    def caller(body_a: str, body_b: str, llm_url: str, llm_model: str) -> str:
        call_count[0] += 1
        return f"{verdict}\n{explanation}"

    caller.call_count = call_count  # type: ignore[attr-defined]
    return caller


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors(self) -> None:
        assert _cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_empty_vector(self) -> None:
        assert _cosine_similarity([], [1.0]) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestParseVerdict:
    def test_contradiction(self) -> None:
        verdict, expl = _parse_llm_verdict("CONTRADICTION\nThey disagree on token rotation.")
        assert verdict == "CONTRADICTION"
        assert "token" in expl

    def test_agreement(self) -> None:
        verdict, _ = _parse_llm_verdict("AGREEMENT\nBoth say the same thing.")
        assert verdict == "AGREEMENT"

    def test_unrelated(self) -> None:
        verdict, _ = _parse_llm_verdict("UNRELATED\nDifferent topics entirely.")
        assert verdict == "UNRELATED"

    def test_empty_string(self) -> None:
        verdict, expl = _parse_llm_verdict("")
        assert verdict == "UNKNOWN"
        assert expl == ""

    def test_verdict_embedded_in_sentence(self) -> None:
        verdict, _ = _parse_llm_verdict("I think this is a CONTRADICTION because foo bar.")
        assert verdict == "CONTRADICTION"


# ---------------------------------------------------------------------------
# Integration-style tests (use tmp_path, mock embedder and LLM)
# ---------------------------------------------------------------------------

class TestDeepContradictionCheck:
    def _monkeypatch_embedder(self, monkeypatch: pytest.MonkeyPatch, embeddings: dict[str, list[float]]) -> None:
        """Patch palinode.core.embedder.embed to return embeddings by body prefix."""
        import palinode.core.embedder as _emb

        def fake_embed(text: str, backend: str = "local") -> list[float]:
            # Match by checking which body the text starts with.
            for body_prefix, vec in embeddings.items():
                if text.startswith(body_prefix[:30]):
                    return vec
            # Default: return a non-zero vector so pairs are not silently skipped.
            return [0.1, 0.2, 0.3, 0.4]

        monkeypatch.setattr(_emb, "embed", fake_embed)

    # ------------------------------------------------------------------
    # Case 1: High similarity + AGREEMENT → no contradiction surfaced
    # ------------------------------------------------------------------
    def test_agreement_not_surfaced(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """Two Decision memories with high similarity + AGREEMENT → no finding."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        body_a = "We chose session-based auth tokens for all API endpoints."
        body_b = "We confirmed session-based auth tokens as the standard approach."
        _write_decision(decisions_dir, "dec-a.md", ["project/auth"], body_a)
        _write_decision(decisions_dir, "dec-b.md", ["project/auth"], body_b)

        vec, _ = _high_sim_embedding_pair()
        self._monkeypatch_embedder(monkeypatch, {body_a: vec, body_b: vec})

        llm_caller = _make_llm_caller("AGREEMENT", "Both decisions align on session-based tokens.")
        result = run_deep_contradiction_check(
            similarity_threshold=0.5,
            max_llm_calls=10,
            memory_dir=str(tmp_path),
            _llm_caller=llm_caller,
        )

        assert result["contradictions"] == []
        assert llm_caller.call_count[0] == 1  # LLM was called (pair evaluated)

    # ------------------------------------------------------------------
    # Case 2: High similarity + CONTRADICTION → finding emitted
    # ------------------------------------------------------------------
    def test_contradiction_surfaced(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """Two Decision memories with high similarity + CONTRADICTION → finding."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        body_a = "We chose 90-day rotation for API tokens (auth decision 2025-12-01)."
        body_b = "We chose session-based tokens (no expiry) for all APIs (auth decision 2026-04-15)."
        _write_decision(decisions_dir, "auth-2025.md", ["project/auth"], body_a)
        _write_decision(decisions_dir, "auth-2026.md", ["project/auth"], body_b)

        vec, _ = _high_sim_embedding_pair()
        self._monkeypatch_embedder(monkeypatch, {body_a: vec, body_b: vec})

        explanation = "Both decisions describe authentication but pick different token rotation strategies."
        llm_caller = _make_llm_caller("CONTRADICTION", explanation)
        result = run_deep_contradiction_check(
            similarity_threshold=0.5,
            max_llm_calls=10,
            memory_dir=str(tmp_path),
            _llm_caller=llm_caller,
        )

        assert len(result["contradictions"]) == 1
        ct = result["contradictions"][0]
        assert "auth-2025.md" in ct["file_a"] or "auth-2025.md" in ct["file_b"]
        assert "auth-2026.md" in ct["file_a"] or "auth-2026.md" in ct["file_b"]
        assert ct["similarity"] >= 0.5
        assert explanation in ct["llm_explanation"]

    # ------------------------------------------------------------------
    # Case 3: Low similarity → pair not evaluated, LLM never called
    # ------------------------------------------------------------------
    def test_low_similarity_not_evaluated(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """Two Decisions with orthogonal embeddings → LLM never called."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        body_a = "We chose session-based tokens for auth."
        body_b = "We use PostgreSQL for the primary database."
        _write_decision(decisions_dir, "auth.md", ["project/backend"], body_a)
        _write_decision(decisions_dir, "db.md", ["project/backend"], body_b)

        vec_a, vec_b = _low_sim_embedding_pair()
        self._monkeypatch_embedder(monkeypatch, {body_a: vec_a, body_b: vec_b})

        llm_caller = _make_llm_caller("CONTRADICTION", "should not be called")
        result = run_deep_contradiction_check(
            similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,  # 0.75
            max_llm_calls=10,
            memory_dir=str(tmp_path),
            _llm_caller=llm_caller,
        )

        assert llm_caller.call_count[0] == 0, "LLM must not be called for low-similarity pair"
        assert result["contradictions"] == []
        assert result["candidate_pairs"] == 0

    # ------------------------------------------------------------------
    # Case 4: max_llm_calls budget cap
    # ------------------------------------------------------------------
    def test_max_llm_calls_budget(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """With 5 candidate pairs and max_llm_calls=2, only 2 LLM calls are made."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        # All share the same entity and the same high-similarity embedding.
        shared_vec = [1.0, 0.0, 0.0, 0.0]
        embedding_map: dict[str, list[float]] = {}
        for i in range(5):
            body = f"We decided to use approach {i} for the shared system."
            _write_decision(decisions_dir, f"dec-{i}.md", ["project/shared"], body)
            embedding_map[body] = shared_vec  # identical → sim=1.0

        # Patch embed to return the shared vector for all bodies.
        import palinode.core.embedder as _emb
        monkeypatch.setattr(_emb, "embed", lambda text, backend="local": shared_vec)

        llm_caller = _make_llm_caller("AGREEMENT", "they agree")
        result = run_deep_contradiction_check(
            similarity_threshold=0.5,
            max_llm_calls=2,
            memory_dir=str(tmp_path),
            _llm_caller=llm_caller,
        )

        assert llm_caller.call_count[0] == 2
        assert result["llm_calls"] == 2
        assert result["llm_budget"] == 2
        # 5 memories → C(5,2)=10 pairs, but all share the entity → all 10 candidates
        # (capped to max_llm_calls=2 by the cap logic)
        assert result["candidate_pairs"] >= 2

    # ------------------------------------------------------------------
    # Case 5: Default lint (no flag) — LLM is never imported or called
    # ------------------------------------------------------------------
    def test_default_lint_no_llm(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """run_lint_pass() (default path) never touches the contradictions module's LLM caller."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        body_a = "We chose 90-day rotation."
        body_b = "We chose session-based tokens."
        _write_decision(decisions_dir, "dec-a.md", ["project/auth"], body_a)
        _write_decision(decisions_dir, "dec-b.md", ["project/auth"], body_b)

        # Confirm run_lint_pass returns a result that does NOT include
        # deep-contradiction data (it uses only the heuristic check).
        from palinode.core.lint import run_lint_pass
        result = run_lint_pass()

        # The standard 'contradictions' key exists (heuristic), but no
        # 'decisions_found' / 'llm_calls' keys — those are deep-check only.
        assert "contradictions" in result
        assert "llm_calls" not in result
        assert "decisions_found" not in result

    # ------------------------------------------------------------------
    # Case 6: Decisions without shared entities are not paired
    # ------------------------------------------------------------------
    def test_no_shared_entity_not_paired(self, tmp_path: "os.PathLike[str]", monkeypatch: pytest.MonkeyPatch) -> None:
        """Decisions with no overlapping entities are never evaluated, even at high similarity."""
        monkeypatch.setattr(config, "memory_dir", str(tmp_path))
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir()

        body_a = "We chose session-based tokens for the auth system."
        body_b = "We chose session-based tokens for the payment system."
        # Different entities — no overlap.
        _write_decision(decisions_dir, "auth.md", ["project/auth"], body_a)
        _write_decision(decisions_dir, "pay.md", ["project/payment"], body_b)

        shared_vec = [1.0, 0.0, 0.0, 0.0]
        import palinode.core.embedder as _emb
        monkeypatch.setattr(_emb, "embed", lambda text, backend="local": shared_vec)

        llm_caller = _make_llm_caller("CONTRADICTION", "should not be called")
        result = run_deep_contradiction_check(
            similarity_threshold=0.5,
            max_llm_calls=10,
            memory_dir=str(tmp_path),
            _llm_caller=llm_caller,
        )

        assert llm_caller.call_count[0] == 0
        assert result["candidate_pairs"] == 0
        assert result["contradictions"] == []
