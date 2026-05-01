"""Tests for the slug-validation step in `_apply_wiki_footer` (#284 / Tier B #4).

The auto-footer constructs ``[[slug]]`` markdown wikilinks from the request's
``entities`` list. Without validation, an entity like ``foo]]hostile[[`` could
break the wikilink syntax and inject arbitrary markdown structure into the
saved memory file.

This suite verifies that:
- bad slugs are dropped (silently — they just don't appear in the footer)
- safe nested-namespace slashes work via the entity-prefix split
- the underlying _safe_wiki_slug helper rejects every dangerous character
  class we care about: brackets, pipes, newlines, null bytes, whitespace
"""
from __future__ import annotations

import pytest

from palinode.api.server import (
    _WIKI_FOOTER_MARKER,
    _apply_wiki_footer,
    _safe_wiki_slug,
)


# ---------------------------------------------------------------------------
# _safe_wiki_slug unit tests
# ---------------------------------------------------------------------------


class TestSafeWikiSlug:
    @pytest.mark.parametrize(
        "slug",
        [
            "palinode",
            "palinode-mcp",
            "alice_bob",
            "v0.5.0",
            "a",
            "a-b-c",
            "x.y.z",
            "ABC123",
        ],
    )
    def test_safe_slugs_accepted(self, slug: str) -> None:
        assert _safe_wiki_slug(slug) is True

    @pytest.mark.parametrize(
        "slug",
        [
            "",  # empty
            "foo]]bar",  # closing bracket break-out
            "foo[[bar",  # opening bracket break-out
            "foo]]bar[[",  # the report's literal example
            "foo|bar",  # pipe — wikilink alias separator
            "foo bar",  # whitespace
            "foo\nbar",  # newline
            "foo\tbar",  # tab
            "foo\x00bar",  # null byte
            "foo<script>",  # html injection
            "foo`bar",  # backtick
            "foo*bar",  # markdown emphasis
            "foo#bar",  # markdown header
            "foo/bar",  # slug already split on '/' — should never contain it
            "x" * 250,  # length cap
        ],
    )
    def test_unsafe_slugs_rejected(self, slug: str) -> None:
        assert _safe_wiki_slug(slug) is False


# ---------------------------------------------------------------------------
# _apply_wiki_footer integration with hostile entities
# ---------------------------------------------------------------------------


class TestApplyWikiFooterRejectsBadSlugs:
    def test_hostile_slug_dropped_from_footer(self):
        """The literal example from the marketplace report."""
        content = "Some decision text."
        # The entity ref is e.g. "project/foo]]bar[[" — the slug split would
        # produce "foo]]bar[[" which is hostile.
        result = _apply_wiki_footer(content, ["project/foo]]bar[["])
        # The footer must NOT appear (we had no safe slugs to emit)
        assert "## See also" not in result
        # The hostile string must NOT have leaked into the output
        assert "foo]]bar[[" not in result
        assert _WIKI_FOOTER_MARKER not in result

    def test_mixed_safe_and_hostile_only_safe_kept(self):
        content = "Body text."
        result = _apply_wiki_footer(
            content,
            ["project/palinode", "person/alice]]inject[[", "project/foo|bar"],
        )
        # Safe slug appears
        assert "[[palinode]]" in result
        # Hostile ones do not
        assert "alice]]inject[[" not in result
        assert "foo|bar" not in result
        assert "## See also" in result
        assert _WIKI_FOOTER_MARKER in result

    def test_only_hostile_slugs_no_footer(self):
        content = "Body."
        result = _apply_wiki_footer(
            content,
            ["project/with space", "person/with\nnewline", "tag/with]]bracket"],
        )
        assert "## See also" not in result
        assert _WIKI_FOOTER_MARKER not in result

    def test_null_byte_slug_rejected(self):
        content = "Body."
        result = _apply_wiki_footer(content, ["project/has\x00null"])
        assert "\x00" not in result
        assert "## See also" not in result

    def test_overly_long_slug_dropped(self):
        content = "Body."
        long_slug = "a" * 250
        result = _apply_wiki_footer(content, [f"project/{long_slug}"])
        assert long_slug not in result
        assert "## See also" not in result
