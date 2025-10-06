"""YNAB MCP Server - Main server implementation."""

import os
import json
import logging
from functools import lru_cache
from mcp.server import FastMCP
from dotenv import load_dotenv

from .ynab_client import YNABClient
from .exceptions import YNABValidationError

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create MCP server
mcp = FastMCP("YNAB")


@lru_cache(maxsize=1)
def get_ynab_client() -> YNABClient:
    """Get or create YNAB client instance (cached singleton).

    Returns:
        YNABClient instance

    Raises:
        YNABValidationError: If YNAB_ACCESS_TOKEN is not set
    """
    logger.info("Getting YNAB client instance")
    token = os.getenv("YNAB_ACCESS_TOKEN")
    if not token:
        error_msg = (
            "YNAB_ACCESS_TOKEN environment variable is not set. "
            "Get your token at: https://app.ynab.com/settings/developer"
        )
        logger.error(error_msg)
        raise YNABValidationError(error_msg)
    return YNABClient(token)


@mcp.tool()
async def get_accounts(budget_id: str) -> str:
    """Get all accounts for a budget.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)

    Returns:
        JSON string with list of accounts
    """
    client = get_ynab_client()
    result = await client.get_accounts(budget_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_category(budget_id: str, category_id: str) -> str:
    """Get a single category with full details including goal information.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        category_id: The category ID

    Returns:
        JSON string with category details including goals, budgeted amounts, activity, and balance
    """
    client = get_ynab_client()
    result = await client.get_category(budget_id, category_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_categories(budget_id: str, include_hidden: bool = False) -> str:
    """Get all categories for a budget.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        include_hidden: Include hidden categories and groups (default: False)

    Returns:
        JSON string with category groups and categories
    """
    client = get_ynab_client()
    result = await client.get_categories(budget_id, include_hidden)
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
    until_date: str = None,
    account_id: str = None,
    category_id: str = None,
    limit: int = None,
    page: int = None,
) -> str:
    """Get transactions with optional filtering and pagination.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        since_date: Only return transactions on or after this date (YYYY-MM-DD format)
        until_date: Only return transactions on or before this date (YYYY-MM-DD format)
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)
        limit: Number of transactions per page (default: 100, max: 500)
        page: Page number for pagination (1-indexed, default: 1)

    Returns:
        JSON string with transactions array and pagination metadata

    Note:
        For large date ranges (>1 year), use get_category_spending_summary or
        compare_spending_by_year instead to avoid timeouts and reduce context usage.
    """
    client = get_ynab_client()
    result = await client.get_transactions(budget_id, since_date, until_date, account_id, category_id, limit, page)
    return json.dumps(result, indent=2)


@mcp.tool()
async def search_transactions(
    budget_id: str,
    search_term: str,
    since_date: str = None,
    until_date: str = None,
    limit: int = None,
) -> str:
    """Search for transactions by text in payee name or memo.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        search_term: Text to search for in payee name or memo (case-insensitive)
        since_date: Only search transactions on or after this date (YYYY-MM-DD format)
        until_date: Only search transactions on or before this date (YYYY-MM-DD format)
        limit: Maximum number of transactions to return (default: 100, max: 500)

    Returns:
        JSON string with matching transactions and count
    """
    client = get_ynab_client()
    result = await client.search_transactions(budget_id, search_term, since_date, until_date, limit)
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
async def get_category_spending_summary(
    budget_id: str,
    category_id: str,
    since_date: str,
    until_date: str,
    include_graph: bool = True,
) -> str:
    """Get spending summary for a category over a date range.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        category_id: The category ID to analyze
        since_date: Start date (YYYY-MM-DD format)
        until_date: End date (YYYY-MM-DD format)
        include_graph: Include terminal graph visualization (default: True)

    Returns:
        JSON string with summary including total spent, average per month, transaction count, monthly breakdown, and optional graph
    """
    client = get_ynab_client()
    result = await client.get_category_spending_summary(budget_id, category_id, since_date, until_date, include_graph)
    return json.dumps(result, indent=2)


@mcp.tool()
async def compare_spending_by_year(
    budget_id: str,
    category_id: str,
    start_year: int,
    num_years: int = 5,
    include_graph: bool = True,
) -> str:
    """Compare spending for a category across multiple years.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        category_id: The category ID to analyze
        start_year: Starting year (e.g., 2020)
        num_years: Number of years to compare (default: 5)
        include_graph: Include terminal graph visualization (default: True)

    Returns:
        JSON string with year-over-year comparison including totals, changes, percentage changes, and optional graph
    """
    client = get_ynab_client()
    result = await client.compare_spending_by_year(budget_id, category_id, start_year, num_years, include_graph)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_scheduled_transactions(budget_id: str) -> str:
    """Get all scheduled transactions.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)

    Returns:
        JSON string with list of scheduled transactions
    """
    client = get_ynab_client()
    result = await client.get_scheduled_transactions(budget_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def create_scheduled_transaction(
    budget_id: str,
    account_id: str,
    date_first: str,
    frequency: str,
    amount: float,
    payee_name: str = None,
    category_id: str = None,
    memo: str = None,
    flag_color: str = None,
) -> str:
    """Create a scheduled transaction (for future/recurring transactions).

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        account_id: The account ID for this scheduled transaction
        date_first: The first date the transaction should occur (YYYY-MM-DD format)
        frequency: Frequency (never, daily, weekly, everyOtherWeek, twiceAMonth, every4Weeks, monthly, everyOtherMonth, every3Months, every4Months, twiceAYear, yearly, everyOtherYear)
        amount: Transaction amount (positive for inflow, negative for outflow)
        payee_name: Name of the payee (optional)
        category_id: Category ID (optional)
        memo: Transaction memo (optional)
        flag_color: Flag color - red, orange, yellow, green, blue, purple (optional)

    Returns:
        JSON string with the created scheduled transaction
    """
    client = get_ynab_client()
    result = await client.create_scheduled_transaction(
        budget_id, account_id, date_first, frequency, amount, payee_name, category_id, memo, flag_color
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def delete_scheduled_transaction(budget_id: str, scheduled_transaction_id: str) -> str:
    """Delete a scheduled transaction.

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        scheduled_transaction_id: The ID of the scheduled transaction to delete

    Returns:
        JSON string with confirmation
    """
    client = get_ynab_client()
    result = await client.delete_scheduled_transaction(budget_id, scheduled_transaction_id)
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
async def update_category(
    budget_id: str,
    category_id: str,
    name: str = None,
    note: str = None,
    category_group_id: str = None,
    goal_target: float = None,
) -> str:
    """Update a category's properties (rename, change note, move to different group, or update goal target).

    Args:
        budget_id: The ID of the budget (use 'last-used' for default budget)
        category_id: The category ID to update
        name: New name for the category (optional)
        note: New note for the category (optional)
        category_group_id: Move to a different category group ID (optional)
        goal_target: New goal target amount - only works if category already has a goal configured (optional)

    Returns:
        JSON string with the updated category
    """
    client = get_ynab_client()
    result = await client.update_category(budget_id, category_id, name, note, category_group_id, goal_target)
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
