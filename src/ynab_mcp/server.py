"""YNAB MCP Server - Main server implementation."""

import os
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

from .ynab_client import YNABClient

# Load environment variables
load_dotenv()

# Initialize server
app = Server("ynab-mcp")

# Initialize YNAB client
ynab_client = YNABClient(os.getenv("YNAB_ACCESS_TOKEN"))


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available YNAB tools."""
    return [
        Tool(
            name="get_categories",
            description="Get all categories for a budget",
            inputSchema={
                "type": "object",
                "properties": {
                    "budget_id": {
                        "type": "string",
                        "description": "The ID of the budget (use 'last-used' for default budget)",
                    }
                },
                "required": ["budget_id"],
            },
        ),
        Tool(
            name="get_budget_summary",
            description="Get budget summary for a specific month",
            inputSchema={
                "type": "object",
                "properties": {
                    "budget_id": {
                        "type": "string",
                        "description": "The ID of the budget (use 'last-used' for default budget)",
                    },
                    "month": {
                        "type": "string",
                        "description": "Month in YYYY-MM-DD format (e.g., 2025-01-01)",
                    },
                },
                "required": ["budget_id", "month"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "get_categories":
            result = await ynab_client.get_categories(arguments["budget_id"])
            return [TextContent(type="text", text=str(result))]

        elif name == "get_budget_summary":
            result = await ynab_client.get_budget_summary(
                arguments["budget_id"], arguments["month"]
            )
            return [TextContent(type="text", text=str(result))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )
