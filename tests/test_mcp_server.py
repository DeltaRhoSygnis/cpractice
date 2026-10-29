"""Tests for the CPractice MCP server.

Covered without a live server: frontier-pair derivation, the reveal gate
(level-5 reference solution must never leak without explicit confirm), the
HTTP error contract the tools expose, and tool registration itself (skipped
when the optional ``mcp`` SDK is not installed).
"""

from __future__ import annotations

import asyncio
import types
from typing import Any

import httpx
import pytest

from app.mcp import server as mcp_server

_CURRICULUM = {
    "stages": [
        {"index": 0, "concepts": ["read_code", "types"]},
        {"index": 1, "concepts": ["if_else"]},
        {"index": 2, "concepts": ["for_loops", "while_loops"]},
        {"index": 3, "concepts": ["arrays"]},
    ]
}


class _ForbiddenClient:
    """A client that must not be touched by a given tool implementation."""

    async def reveal_solution(self, problem_id: str) -> dict:  # pragma: no cover
        raise AssertionError("reveal path must not run without confirm")


class _FailingTransport(httpx.MockTransport):
    def __init__(self) -> None:
        super().__init__(self._handler)
        self.status_code = 404
        self.payload: Any = {"detail": "no package 'ghost'"}

    def _handler(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(self.status_code, json=self.payload)


def test_derive_frontier_pair_picks_first_unknown_concept() -> None:
    derived = mcp_server.derive_frontier_pair(
        _CURRICULUM, ["read_code", "types", "if_else"]
    )
    # Stage 2's first unknown concept is the frontier new concept.
    assert derived["new_concept"] == "for_loops"
    assert derived["new_stage"] == 2
    # Known concepts from earlier stages, closest stages first, capped at 4.
    assert derived["assumed_known"] == ["read_code", "types", "if_else"]


def test_derive_frontier_pair_completed_ladder_has_no_new_concept() -> None:
    derived = mcp_server.derive_frontier_pair(
        _CURRICULUM, ["read_code", "types", "if_else", "for_loops", "while_loops", "arrays"]
    )
    assert derived["new_concept"] is None


def test_reveal_solution_requires_explicit_confirm() -> None:
    mcp_server.configure_client(_ForbiddenClient())  # type: ignore[arg-type]
    try:
        result = asyncio.run(mcp_server.tool_reveal_solution("any-problem"))
        assert result["ok"] is False
        assert "confirm" in result["error"]
    finally:
        mcp_server.configure_client(None)


def test_api_errors_expose_status_and_detail() -> None:
    client = mcp_server.CPracticeClient("http://unit")
    # Patch the client factory per call: _call opens its own AsyncClient.
    transport = _FailingTransport()

    from unittest.mock import patch

    real_async_client = httpx.AsyncClient
    with patch.object(httpx, "AsyncClient", lambda **kw: real_async_client(**{**kw, "transport": transport})):
        with pytest.raises(mcp_server.CPracticeAPIError) as excinfo:
            asyncio.run(client.get_problem("ghost"))

    assert excinfo.value.status_code == 404
    assert excinfo.value.to_payload()["error"] == "no package 'ghost'"
    assert excinfo.value.to_payload()["ok"] is False


def _run_async_tools() -> list:
    pytest.importorskip("mcp", reason="optional MCP SDK not installed")

    from app.mcp.server import build_server

    mcp = build_server("http://127.0.0.1:1")  # base URL is never contacted
    tools = mcp.list_tools()
    if hasattr(tools, "__await__"):
        tools = asyncio.run(tools)
    return tools


def test_server_registers_expected_tools() -> None:
    tools = _run_async_tools()
    names = {tool.name for tool in tools}
    assert names == set(mcp_server.TOOL_FUNCS)
    assert len(names) > 0


def test_reveal_tool_is_advertised_with_confirm_gate() -> None:
    tools = _run_async_tools()
    reveal = next(t for t in tools if t.name == "reveal_solution")
    assert "confirm" in (reveal.description or "")
    assert "explicitly" in (reveal.description or "")


def test_main_explains_missing_mcp_sdk(monkeypatch, capsys) -> None:
    def boom(base_url=None):
        raise ImportError("No module named 'mcp'")

    monkeypatch.setattr(mcp_server, "build_server", boom)
    assert mcp_server.main([]) == 1
    assert "cpractice[mcp]" in capsys.readouterr().out


def test_main_runs_server_and_returns_zero(monkeypatch) -> None:
    class _FakeServer:
        def __init__(self) -> None:
            self.settings = types.SimpleNamespace(host=None, port=None)
            self.transports: list[str] = []

        def run(self, transport: str) -> None:
            self.transports.append(transport)

    fake = _FakeServer()
    monkeypatch.setattr(mcp_server, "build_server", lambda base_url=None: fake)

    code = mcp_server.main(["--transport", "streamable-http", "--port", "8123"])

    assert code == 0
    assert fake.transports == ["streamable-http"]
    assert fake.settings.port == 8123
