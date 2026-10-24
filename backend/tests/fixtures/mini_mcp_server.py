"""Minimal stdio MCP server used by integration tests: exposes tool `add`."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mini-test")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
