"""Output comparison.

Two explicit modes are supported. The mode is chosen per problem (or per
test), never silently defaulted to the most permissive option: pattern-printing
problems often depend on exact spacing.
"""

from __future__ import annotations

from app.schemas.test_case import ComparisonMode


def normalize_line_endings(text: str) -> str:
    """Convert CRLF and lone CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compare_exact_normalized(
    observed: str,
    expected: str,
    *,
    ignore_final_newline: bool = True,
) -> bool:
    """Compare after normalising line endings.

    When ``ignore_final_newline`` is set, a single trailing newline is
    disregarded on both sides. Interior whitespace is significant.
    """
    left = normalize_line_endings(observed)
    right = normalize_line_endings(expected)

    if ignore_final_newline:
        if left.endswith("\n"):
            left = left[:-1]
        if right.endswith("\n"):
            right = right[:-1]

    return left == right


def compare_whitespace_tolerant(observed: str, expected: str) -> bool:
    """Compare as whitespace-separated tokens, preserving token order."""
    return normalize_line_endings(observed).split() == normalize_line_endings(
        expected
    ).split()


def outputs_match(
    observed: str,
    expected: str,
    mode: ComparisonMode | str,
    *,
    ignore_final_newline: bool = True,
) -> bool:
    """Dispatch to the requested comparison mode."""
    resolved = ComparisonMode(mode)

    if resolved is ComparisonMode.EXACT_NORMALIZED:
        return compare_exact_normalized(
            observed, expected, ignore_final_newline=ignore_final_newline
        )

    if resolved is ComparisonMode.WHITESPACE_TOLERANT:
        return compare_whitespace_tolerant(observed, expected)

    raise ValueError(f"unsupported comparison mode: {mode!r}")  # pragma: no cover
