"""YNAB MCP Server - Main server implementation."""

import os
import json
import asyncio
from mcp.server import FastMCP
from dotenv import load_dotenv

from .ynab_client import YNABClient

# Load environment variables
load_dotenv()

# Create MCP server
mcp = FastMCP("YNAB")

# YNAB client will be initialized lazily
ynab_client = None


def get_ynab_client() -> YNABClient:
    """Get or create YNAB client instance."""
    global ynab_client
    if ynab_client is None:
        ynab_client = YNABClient(os.getenv("YNAB_ACCESS_TOKEN"))
    return ynab_client


@mcp.tool()
async def get_categories(budget_id: str) -> str:
    """Get all categories for a budget.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)

    Returns:
        JSON string with category groups and categories
    """
    client = get_ynab_client()
    result = await client.get_categories(budget_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_budget_summary(budget_id: str, month: str) -> str:
    """Get budget summary for a specific month.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        month: Month in YYYY-MM-DD format (e.g., 2025-01-01 for January 2025)

    Returns:
        JSON string with budget summary including income, budgeted amounts, and category details
    """
    client = get_ynab_client()
    result = await client.get_budget_summary(budget_id, month)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_transactions(
    budget_id: str,
    since_date: str = None,
    account_id: str = None,
    category_id: str = None,
) -> str:
    """Get transactions with optional filtering.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        since_date: Only return transactions on or after this date (YYYY-MM-DD format)
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)

    Returns:
        JSON string with list of transactions
    """
    client = get_ynab_client()
    result = await client.get_transactions(budget_id, since_date, account_id, category_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def create_transaction(
    budget_id: str,
    account_id: str,
    date: str,
    amount: float,
    payee_name: str = None,
    category_id: str = None,
    memo: str = None,
    cleared: str = "uncleared",
    approved: bool = False,
) -> str:
    """Create a new transaction.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        account_id: The account ID for this transaction
        date: Transaction date in YYYY-MM-DD format
        amount: Transaction amount (positive for inflow, negative for outflow)
        payee_name: Name of the payee (optional)
        category_id: Category ID (optional)
        memo: Transaction memo (optional)
        cleared: Cleared status - 'cleared', 'uncleared', or 'reconciled' (default: 'uncleared')
        approved: Whether the transaction is approved (default: False)

    Returns:
        JSON string with the created transaction
    """
    client = get_ynab_client()
    result = await client.create_transaction(
        budget_id, account_id, date, amount, payee_name, category_id, memo, cleared, approved
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_transaction(
    budget_id: str,
    transaction_id: str,
    account_id: str = None,
    date: str = None,
    amount: float = None,
    payee_name: str = None,
    category_id: str = None,
    memo: str = None,
    cleared: str = None,
    approved: bool = None,
) -> str:
    """Update an existing transaction.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        transaction_id: The ID of the transaction to update
        account_id: The account ID (optional - keeps existing if not provided)
        date: Transaction date in YYYY-MM-DD format (optional)
        amount: Transaction amount (optional)
        payee_name: Name of the payee (optional)
        category_id: Category ID (optional)
        memo: Transaction memo (optional)
        cleared: Cleared status - 'cleared', 'uncleared', or 'reconciled' (optional)
        approved: Whether the transaction is approved (optional)

    Returns:
        JSON string with the updated transaction
    """
    client = get_ynab_client()
    result = await client.update_transaction(
        budget_id, transaction_id, account_id, date, amount, payee_name, category_id, memo, cleared, approved
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_unapproved_transactions(budget_id: str) -> str:
    """Get all unapproved transactions that need review.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)

    Returns:
        JSON string with list of unapproved transactions
    """
    client = get_ynab_client()
    result = await client.get_unapproved_transactions(budget_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_category_budget(
    budget_id: str,
    month: str,
    category_id: str,
    budgeted: float,
) -> str:
    """Update the budgeted amount for a category in a specific month.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        month: Month in YYYY-MM-DD format (e.g., 2025-01-01 for January 2025)
        category_id: The category ID to update
        budgeted: The budgeted amount to set

    Returns:
        JSON string with the updated category
    """
    client = get_ynab_client()
    result = await client.update_category_budget(budget_id, month, category_id, budgeted)
    return json.dumps(result, indent=2)


@mcp.tool()
async def move_category_funds(
    budget_id: str,
    month: str,
    from_category_id: str,
    to_category_id: str,
    amount: float,
) -> str:
    """Move funds from one category to another in a specific month.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        month: Month in YYYY-MM-DD format (e.g., 2025-01-01 for January 2025)
        from_category_id: Source category ID to move funds from
        to_category_id: Destination category ID to move funds to
        amount: Amount to move (positive value)

    Returns:
        JSON string with updated from and to categories
    """
    client = get_ynab_client()
    result = await client.move_category_funds(budget_id, month, from_category_id, to_category_id, amount)
    return json.dumps(result, indent=2)


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")
