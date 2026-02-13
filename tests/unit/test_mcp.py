"""Unit tests for MCP server module."""

from unittest.mock import MagicMock, patch

import pytest

from agenticos.mcp.server import create_mcp_server


class TestMCPServer:
    """Tests for the MCP server creation."""

    def test_create_server(self):
        server = create_mcp_server()
        assert server is not None
        assert server.name == "agenticos"

    def test_server_has_tools(self):
        server = create_mcp_server()
        # FastMCP registers tools as callables
        assert hasattr(server, "_tool_manager") or hasattr(server, "list_tools")
