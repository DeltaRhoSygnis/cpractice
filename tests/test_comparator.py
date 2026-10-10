"""Tests for the output comparator."""

from __future__ import annotations

import pytest

from app.grading.comparator import (
    compare_exact_normalized,
    compare_whitespace_tolerant,
    normalize_line_endings,
    outputs_match,
)
from app.schemas.test_case import ComparisonMode


def test_normalize_line_endings_handles_crlf_and_cr() -> None:
    assert normalize_line_endings("a\r\nb\rc") == "a\nb\nc"


def test_exact_ignores_single_final_newline_by_default() -> None:
    assert compare_exact_normalized("42\n", "42")
    assert compare_exact_normalized("42", "42\n")


def test_exact_ignores_crlf_vs_lf() -> None:
    assert compare_exact_normalized("a\r\nb\r\n", "a\nb\n")


def test_exact_respects_interior_whitespace() -> None:
    # Pattern problems depend on exact spacing.
    assert not compare_exact_normalized("* * *", "*  *  *")


def test_exact_can_require_final_newline() -> None:
    assert not compare_exact_normalized("42", "42\n", ignore_final_newline=False)
    assert compare_exact_normalized("42\n", "42\n", ignore_final_newline=False)


def test_exact_rejects_different_values() -> None:
    assert not compare_exact_normalized("41", "42")


def test_whitespace_tolerant_ignores_layout() -> None:
    assert compare_whitespace_tolerant("  a   b\n c ", "a b c")


def test_whitespace_tolerant_preserves_token_order() -> None:
    assert not compare_whitespace_tolerant("b a", "a b")


def test_outputs_match_dispatches_by_mode() -> None:
    assert outputs_match("a  b", "a b", ComparisonMode.WHITESPACE_TOLERANT)
    assert not outputs_match("a  b", "a b", ComparisonMode.EXACT_NORMALIZED)


def test_outputs_match_accepts_string_mode() -> None:
    assert outputs_match("x", "x", "exact_normalized")


def test_outputs_match_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        outputs_match("x", "x", "not_a_mode")
