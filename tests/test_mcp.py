"""Tests for the MCP layer (palinode/mcp.py).

Pure-function helpers that the dispatcher delegates to. These tests don't
exercise the async tool dispatch — they cover only the logic the dispatcher
calls into, which is what changes most often and is easiest to regress.
"""
import pytest

from palinode.mcp import _coerce_str_array, _resolve_save_type


# ---- _coerce_str_array (#147 — JSON-encoded array args from MCP clients) ----


def test_coerce_str_array_decodes_json_array_string():
    assert _coerce_str_array('["a", "b"]') == ["a", "b"]


def test_coerce_str_array_passes_native_list_through():
    assert _coerce_str_array(["a", "b"]) == ["a", "b"]


def test_coerce_str_array_returns_none_unchanged():
    assert _coerce_str_array(None) is None


def test_coerce_str_array_returns_non_array_json_unchanged():
    # A JSON object string is not an array — leave it for downstream validation.
    assert _coerce_str_array('{"a": 1}') == '{"a": 1}'


def test_coerce_str_array_returns_invalid_json_unchanged():
    assert _coerce_str_array("not json at all") == "not json at all"


def test_coerce_str_array_handles_empty_array_string():
    assert _coerce_str_array("[]") == []


def test_coerce_str_array_preserves_inner_types():
    # Decoder preserves whatever JSON yields; validation downstream catches mismatches.
    assert _coerce_str_array("[1, 2, 3]") == [1, 2, 3]


# ---- _resolve_save_type (#136 — palinode_save type / ps=true shortcut) ----


def test_resolve_save_type_explicit_type():
    assert _resolve_save_type("Decision", None) == "Decision"
    assert _resolve_save_type("ProjectSnapshot", None) == "ProjectSnapshot"
    assert _resolve_save_type("Insight", False) == "Insight"


def test_resolve_save_type_ps_shortcut_only():
    assert _resolve_save_type(None, True) == "ProjectSnapshot"


def test_resolve_save_type_ps_with_redundant_matching_type():
    # ps=true + type=ProjectSnapshot is redundant but explicitly OK
    assert _resolve_save_type("ProjectSnapshot", True) == "ProjectSnapshot"


def test_resolve_save_type_ps_conflict_with_other_type():
    with pytest.raises(ValueError, match="conflicts"):
        _resolve_save_type("Decision", True)
    with pytest.raises(ValueError, match="conflicts"):
        _resolve_save_type("Insight", True)


def test_resolve_save_type_neither_specified():
    with pytest.raises(ValueError, match="must specify"):
        _resolve_save_type(None, None)
    with pytest.raises(ValueError, match="must specify"):
        _resolve_save_type(None, False)
    with pytest.raises(ValueError, match="must specify"):
        _resolve_save_type("", False)


def test_resolve_save_type_falsy_ps_treated_as_unset():
    # ps=False with a real type should pass the type through
    assert _resolve_save_type("Decision", False) == "Decision"
