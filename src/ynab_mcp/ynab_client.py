"""YNAB API client wrapper with authentication."""

from __future__ import annotations

import asyncio
import logging
import sys
from io import StringIO
from typing import Any

import httpx
from termgraph import termgraph as tg
from ynab_sdk import YNAB

from .exceptions import (
    YNABAPIError,
    YNABConnectionError,
    YNABRateLimitError,
    YNABValidationError,
)
from .validation import (
    validate_budget_id,
    validate_date,
)

# Constants
MILLIUNITS_FACTOR = 1000
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3

# Configure logging
logger = logging.getLogger(__name__)


class YNABClient:
    """Wrapper around YNAB SDK for MCP server."""

    def __init__(self, access_token: str | None):
        """Initialize YNAB client with access token.

        Args:
            access_token: YNAB Personal Access Token

        Raises:
            YNABValidationError: If access token is not provided
        """
        if not access_token:
            raise YNABValidationError(
                "YNAB_ACCESS_TOKEN environment variable must be set. "
                "Get your token at: https://app.ynab.com/settings/developer"
            )

        logger.info("Initializing YNAB client")

        # Initialize YNAB SDK client
        self.client = YNAB(access_token)
        self._access_token = access_token
        self.api_base_url = "https://api.ynab.com/v1"
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling.

        Returns:
            Configured HTTP client instance
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            logger.debug("Created new HTTP client")
        return self._http_client

    async def close(self):
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("Closed HTTP client")

    def _filter_categories(
        self, categories: list[dict[str, Any]], include_hidden: bool = False
    ) -> list[dict[str, Any]]:
        """Filter categories to exclude hidden/deleted ones by default.

        Args:
            categories: List of category dictionaries from API
            include_hidden: If True, include hidden categories (default: False)

        Returns:
            Filtered list of categories
        """
        filtered = []
        for category in categories:
            # Always skip deleted categories
            if category.get("deleted"):
                continue
            # Skip hidden categories unless explicitly included
            if not include_hidden and category.get("hidden"):
                continue
            filtered.append(category)
        return filtered

    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make API request with retry logic for rate limits.

        Args:
            method: HTTP method (get, post, put, patch, delete)
            url: Full URL to request
            **kwargs: Additional arguments to pass to httpx

        Returns:
            Parsed JSON response

        Raises:
            YNABRateLimitError: If rate limited after retries
            YNABAPIError: If API returns an error
            YNABConnectionError: If connection fails
        """
        client = await self._get_http_client()

        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(
                    f"Making {method.upper()} request to {url} (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                response = await getattr(client, method)(url, **kwargs)
                response.raise_for_status()
                logger.debug(f"Request successful: {response.status_code}")
                return response.json()

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == 429:
                    # Rate limited
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limited (429), retry after {retry_after}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )

                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise YNABRateLimitError(
                            f"Rate limit exceeded. Retry after {retry_after} seconds.",
                            retry_after=retry_after,
                        ) from e

                # Other HTTP errors
                logger.error(f"HTTP error {status_code}: {e.response.text}")
                raise YNABAPIError(
                    f"API request failed: HTTP {status_code}",
                    status_code=status_code,
                ) from e

            except httpx.TimeoutException as e:
                logger.error(f"Request timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    continue
                raise YNABConnectionError(f"Request timeout after {MAX_RETRIES} attempts") from e

            except httpx.NetworkError as e:
                logger.error(f"Network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    continue
                raise YNABConnectionError(f"Network error after {MAX_RETRIES} attempts") from e

            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                raise YNABAPIError(f"Unexpected error: {e}") from e

        # Should never reach here, but just in case
        raise YNABAPIError(f"Request failed after {MAX_RETRIES} attempts")

    async def get_budgets(self) -> list[dict[str, Any]]:
        """Get all budgets for the authenticated user.

        Returns:
            List of budget dictionaries
        """
        try:
            response = self.client.budgets.get_budgets()
            budgets = []
            for budget in response.data.budgets:
                budgets.append(
                    {
                        "id": budget.id,
                        "name": budget.name,
                        "last_modified_on": str(budget.last_modified_on)
                        if budget.last_modified_on
                        else None,
                        "currency_format": {
                            "iso_code": budget.currency_format.iso_code,
                            "example_format": budget.currency_format.example_format,
                            "currency_symbol": budget.currency_format.currency_symbol,
                        },
                    }
                )
            return budgets
        except Exception as e:
            raise Exception(f"Failed to get budgets: {e}") from e

    async def get_accounts(self, budget_id: str) -> list[dict[str, Any]]:
        """Get all accounts for a budget.

        Args:
            budget_id: The budget ID or 'last-used'

        Returns:
            List of account dictionaries
        """
        try:
            response = self.client.accounts.get_accounts(budget_id)
            accounts = []

            for account in response.data.accounts:
                # Skip deleted accounts
                if account.deleted:
                    continue

                accounts.append(
                    {
                        "id": account.id,
                        "name": account.name,
                        "type": account.type,
                        "on_budget": account.on_budget,
                        "closed": account.closed,
                        "balance": account.balance / 1000 if account.balance else 0,
                    }
                )

            return accounts
        except Exception as e:
            raise Exception(f"Failed to get accounts: {e}") from e

    async def get_category(self, budget_id: str, category_id: str) -> dict[str, Any]:
        """Get a single category with all details including goal information.

        Args:
            budget_id: The budget ID or 'last-used'
            category_id: The category ID

        Returns:
            Category dictionary with full details

        Raises:
            YNABValidationError: If parameters are invalid
            YNABAPIError: If API request fails
        """
        logger.debug(f"Getting category {category_id} for budget {budget_id}")

        # Validate inputs
        budget_id = validate_budget_id(budget_id)

        url = f"{self.api_base_url}/budgets/{budget_id}/categories/{category_id}"
        result = await self._make_request_with_retry("get", url)

        cat = result["data"]["category"]

        return {
            "id": cat["id"],
            "name": cat["name"],
            "category_group_id": cat.get("category_group_id"),
            "hidden": cat.get("hidden"),
            "note": cat.get("note"),
            "budgeted": cat.get("budgeted", 0) / MILLIUNITS_FACTOR if cat.get("budgeted") else 0,
            "activity": cat.get("activity", 0) / MILLIUNITS_FACTOR if cat.get("activity") else 0,
            "balance": cat.get("balance", 0) / MILLIUNITS_FACTOR if cat.get("balance") else 0,
            "goal_type": cat.get("goal_type"),
            "goal_target": cat.get("goal_target", 0) / MILLIUNITS_FACTOR
            if cat.get("goal_target")
            else 0,
            "goal_target_month": cat.get("goal_target_month"),
            "goal_percentage_complete": cat.get("goal_percentage_complete"),
            "goal_months_to_budget": cat.get("goal_months_to_budget"),
            "goal_under_funded": cat.get("goal_under_funded", 0) / MILLIUNITS_FACTOR
            if cat.get("goal_under_funded")
            else 0,
            "goal_overall_funded": cat.get("goal_overall_funded", 0) / MILLIUNITS_FACTOR
            if cat.get("goal_overall_funded")
            else 0,
            "goal_overall_left": cat.get("goal_overall_left", 0) / MILLIUNITS_FACTOR
            if cat.get("goal_overall_left")
            else 0,
        }

    async def get_categories(
        self, budget_id: str, include_hidden: bool = False
    ) -> list[dict[str, Any]]:
        """Get all categories for a budget.

        Args:
            budget_id: The budget ID or 'last-used'
            include_hidden: Include hidden categories and groups (default: False)

        Returns:
            List of category dictionaries grouped by category groups
        """
        try:
            response = self.client.categories.get_categories(budget_id)
            category_groups = []

            for group in response.data.category_groups:
                categories = []
                for category in group.categories:
                    # Skip hidden and deleted categories unless requested
                    if not include_hidden and (category.hidden or category.deleted):
                        continue

                    categories.append(
                        {
                            "id": category.id,
                            "name": category.name,
                            "balance": category.balance / 1000 if category.balance else 0,
                            "hidden": category.hidden,
                        }
                    )

                # Skip hidden groups unless requested, and skip empty groups
                if (not include_hidden and group.hidden) or not categories:
                    continue

                category_groups.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "hidden": group.hidden,
                        "categories": categories,
                    }
                )

            return category_groups
        except Exception as e:
            raise Exception(f"Failed to get categories: {e}") from e

    async def get_underfunded_goals(
        self,
        budget_id: str,
        month: str,
    ) -> dict[str, Any]:
        """Get all underfunded category goals for a specific month.

        Retrieves categories with goals that need additional funding to meet
        their targets for the specified month.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format (e.g., 2025-01-01)

        Returns:
            Dictionary with underfunded goals summary:
            - month: The month being analyzed
            - total_underfunded: Total amount needed across all goals
            - underfunded_count: Number of categories that are underfunded
            - underfunded_categories: List of underfunded category details including:
                - category_group: The category group name
                - category_name: The category name
                - category_id: The category ID
                - budgeted: Amount currently budgeted
                - goal_target: The goal target amount
                - goal_under_funded: Amount still needed to meet goal
                - goal_type: Type of goal (e.g., TB, TBD, MF, NEED, DEBT)

        Note:
            goal_under_funded represents the amount needed in the current month
            to stay on track towards completing the goal within the goal period.
        """
        logger.debug(f"Getting underfunded goals for {budget_id}, month {month}")

        # Validate inputs
        budget_id = validate_budget_id(budget_id)
        month = validate_date(month, "month")

        # Use direct API call to get month-specific budget data
        url = f"{self.api_base_url}/budgets/{budget_id}/months/{month}"
        result = await self._make_request_with_retry("get", url)

        month_data = result["data"]["month"]

        # Get category groups to map category IDs to group names
        categories_response = self.client.categories.get_categories(budget_id)
        category_group_map = {}
        for group in categories_response.data.category_groups:
            for cat in group.categories:
                category_group_map[cat.id] = group.name

        # Collect underfunded categories
        underfunded_categories = []
        total_underfunded = 0

        # Filter out hidden and deleted categories
        categories = self._filter_categories(month_data.get("categories", []))

        for category in categories:
            goal_under_funded = (
                category.get("goal_under_funded", 0) / MILLIUNITS_FACTOR
                if category.get("goal_under_funded")
                else 0
            )

            # Only include categories that have goals and are underfunded
            if goal_under_funded > 0:
                category_group_name = category_group_map.get(category["id"], "Unknown")

                underfunded_categories.append(
                    {
                        "category_group": category_group_name,
                        "category_name": category["name"],
                        "category_id": category["id"],
                        "budgeted": category.get("budgeted", 0) / MILLIUNITS_FACTOR
                        if category.get("budgeted")
                        else 0,
                        "goal_target": category.get("goal_target", 0) / MILLIUNITS_FACTOR
                        if category.get("goal_target")
                        else 0,
                        "goal_under_funded": goal_under_funded,
                        "goal_type": category.get("goal_type"),
                    }
                )
                total_underfunded += goal_under_funded

        return {
            "month": month,
            "total_underfunded": total_underfunded,
            "underfunded_count": len(underfunded_categories),
            "underfunded_categories": underfunded_categories,
        }

    async def get_budget_summary(self, budget_id: str, month: str) -> dict[str, Any]:
        """Get budget summary for a specific month.

        Uses direct API to get month-specific data since SDK doesn't support it.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format (e.g., 2025-01-01)

        Returns:
            Budget summary dictionary

        Raises:
            YNABValidationError: If parameters are invalid
            YNABAPIError: If API request fails
        """
        logger.debug(f"Getting budget summary for {budget_id}, month {month}")

        # Validate inputs
        budget_id = validate_budget_id(budget_id)
        month = validate_date(month, "month")

        # Use direct API call to get month-specific budget data
        url = f"{self.api_base_url}/budgets/{budget_id}/months/{month}"
        result = await self._make_request_with_retry("get", url)

        month_data = result["data"]["month"]

        # Debug: Check what keys are available
        if "categories" not in month_data:
            raise YNABAPIError(f"Month data keys: {list(month_data.keys())}")

        # Get category groups to map category IDs to group names
        categories_response = self.client.categories.get_categories(budget_id)
        category_group_map = {}
        for group in categories_response.data.category_groups:
            for cat in group.categories:
                category_group_map[cat.id] = group.name

        # Calculate totals and collect category details
        total_budgeted = 0
        total_activity = 0
        total_balance = 0
        categories = []

        # Month data has a flat list of categories, not grouped
        # Filter out hidden and deleted categories
        filtered_categories = self._filter_categories(month_data.get("categories", []))

        for category in filtered_categories:
            budgeted = category["budgeted"] / MILLIUNITS_FACTOR if category["budgeted"] else 0
            activity = category["activity"] / MILLIUNITS_FACTOR if category["activity"] else 0
            balance = category["balance"] / MILLIUNITS_FACTOR if category["balance"] else 0

            total_budgeted += budgeted
            total_activity += activity
            total_balance += balance

            category_group_name = category_group_map.get(category["id"], "Unknown")

            categories.append(
                {
                    "category_group": category_group_name,
                    "category_name": category["name"],
                    "budgeted": budgeted,
                    "activity": activity,
                    "balance": balance,
                }
            )

        return {
            "month": month,
            "income": month_data["income"] / MILLIUNITS_FACTOR if month_data.get("income") else 0,
            "budgeted": total_budgeted,
            "activity": total_activity,
            "balance": total_balance,
            "to_be_budgeted": month_data["to_be_budgeted"] / MILLIUNITS_FACTOR
            if month_data.get("to_be_budgeted")
            else 0,
            "categories": categories,
        }

    async def get_transactions(
        self,
        budget_id: str,
        since_date: str | None = None,
        until_date: str | None = None,
        account_id: str | None = None,
        category_id: str | None = None,
        limit: int | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Get transactions with optional filtering and pagination.

        Args:
            budget_id: The budget ID or 'last-used'
            since_date: Only return transactions on or after this date (YYYY-MM-DD)
            until_date: Only return transactions on or before this date (YYYY-MM-DD)
            account_id: Filter by account ID
            category_id: Filter by category ID
            limit: Number of transactions per page (default: 100, max: 500)
            page: Page number for pagination (1-indexed, default: 1)

        Returns:
            Dictionary with transactions, pagination info, and total count

        Note:
            For large date ranges (>1 year), consider using get_category_spending_summary
            or compare_spending_by_year instead to avoid timeouts and reduce context usage.
        """
        try:
            # Use direct API call for better filtering support
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"
            params = {}
            if since_date:
                params["since_date"] = since_date
            if account_id:
                url = f"{self.api_base_url}/budgets/{budget_id}/accounts/{account_id}/transactions"

            result = await self._make_request_with_retry("get", url, params=params)

            txn_data = result["data"]["transactions"]

            # Apply filters
            filtered_transactions = []
            for txn in txn_data:
                # Filter by category_id if provided
                if category_id and txn.get("category_id") != category_id:
                    continue

                # Filter by until_date if provided (client-side filtering)
                if until_date and txn["date"] > until_date:
                    continue

                filtered_transactions.append(txn)

            # Pagination
            page_size = min(limit or 100, 500)  # Default 100, max 500
            page_num = max(page or 1, 1)  # Default to page 1, minimum 1

            total_count = len(filtered_transactions)
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

            start_idx = (page_num - 1) * page_size
            end_idx = start_idx + page_size

            paginated_txns = filtered_transactions[start_idx:end_idx]

            transactions = []
            for txn in paginated_txns:
                transactions.append(
                    {
                        "id": txn["id"],
                        "date": txn["date"],
                        "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                        "memo": txn.get("memo"),
                        "cleared": txn.get("cleared"),
                        "approved": txn.get("approved"),
                        "account_id": txn.get("account_id"),
                        "account_name": txn.get("account_name"),
                        "payee_id": txn.get("payee_id"),
                        "payee_name": txn.get("payee_name"),
                        "category_id": txn.get("category_id"),
                        "category_name": txn.get("category_name"),
                        "transfer_account_id": txn.get("transfer_account_id"),
                        "deleted": txn.get("deleted"),
                    }
                )

            return {
                "transactions": transactions,
                "pagination": {
                    "page": page_num,
                    "per_page": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next_page": page_num < total_pages,
                    "has_prev_page": page_num > 1,
                },
            }
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Failed to get transactions: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise Exception(f"Failed to get transactions: {type(e).__name__}: {e}") from e

    async def search_transactions(
        self,
        budget_id: str,
        search_term: str,
        since_date: str | None = None,
        until_date: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Search transactions by text matching in payee name or memo.

        Args:
            budget_id: The budget ID or 'last-used'
            search_term: Text to search for in payee name or memo (case-insensitive)
            since_date: Only return transactions on or after this date (YYYY-MM-DD)
            until_date: Only return transactions on or before this date (YYYY-MM-DD)
            limit: Maximum number of transactions to return (default: 100, max: 500)

        Returns:
            Dictionary with matching transactions and count
        """
        try:
            # Get all transactions with date filtering
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"
            params = {}
            if since_date:
                params["since_date"] = since_date

            result = await self._make_request_with_retry("get", url, params=params)

            txn_data = result["data"]["transactions"]

            # Search and filter
            search_lower = search_term.lower()
            matching_transactions = []

            for txn in txn_data:
                # Filter by until_date if provided
                if until_date and txn["date"] > until_date:
                    continue

                # Search in payee_name and memo
                payee_name = (txn.get("payee_name") or "").lower()
                memo = (txn.get("memo") or "").lower()

                if search_lower in payee_name or search_lower in memo:
                    matching_transactions.append(
                        {
                            "id": txn["id"],
                            "date": txn["date"],
                            "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                            "memo": txn.get("memo"),
                            "cleared": txn.get("cleared"),
                            "approved": txn.get("approved"),
                            "account_id": txn.get("account_id"),
                            "account_name": txn.get("account_name"),
                            "payee_id": txn.get("payee_id"),
                            "payee_name": txn.get("payee_name"),
                            "category_id": txn.get("category_id"),
                            "category_name": txn.get("category_name"),
                        }
                    )

                    # Apply limit if specified
                    if limit and len(matching_transactions) >= limit:
                        break

            return {
                "search_term": search_term,
                "transactions": matching_transactions,
                "count": len(matching_transactions),
            }
        except Exception as e:
            raise Exception(f"Failed to search transactions: {e}") from e

    async def create_transaction(
        self,
        budget_id: str,
        account_id: str,
        date: str,
        amount: float,
        payee_name: str | None = None,
        category_id: str | None = None,
        memo: str | None = None,
        cleared: str = "uncleared",
        approved: bool = False,
    ) -> dict[str, Any]:
        """Create a new transaction.

        Args:
            budget_id: The budget ID or 'last-used'
            account_id: The account ID
            date: Transaction date (YYYY-MM-DD)
            amount: Transaction amount (positive for inflow, negative for outflow)
            payee_name: Payee name
            category_id: Category ID
            memo: Transaction memo
            cleared: Cleared status ('cleared', 'uncleared', 'reconciled')
            approved: Whether transaction is approved

        Returns:
            Created transaction dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"

            transaction_data = {
                "account_id": account_id,
                "date": date,
                "amount": int(amount * 1000),  # Convert to milliunits
                "cleared": cleared,
                "approved": approved,
            }

            if payee_name is not None:
                transaction_data["payee_name"] = payee_name
            if category_id is not None:
                transaction_data["category_id"] = category_id
            if memo is not None:
                transaction_data["memo"] = memo

            data = {"transaction": transaction_data}

            result = await self._make_request_with_retry("post", url, json=data)

            txn = result["data"]["transaction"]

            return {
                "id": txn["id"],
                "date": txn["date"],
                "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                "memo": txn.get("memo"),
                "cleared": txn.get("cleared"),
                "approved": txn.get("approved"),
                "account_id": txn.get("account_id"),
                "account_name": txn.get("account_name"),
                "payee_id": txn.get("payee_id"),
                "payee_name": txn.get("payee_name"),
                "category_id": txn.get("category_id"),
                "category_name": txn.get("category_name"),
            }
        except Exception as e:
            raise Exception(f"Failed to create transaction: {e}") from e

    async def update_transaction(
        self,
        budget_id: str,
        transaction_id: str,
        account_id: str | None = None,
        date: str | None = None,
        amount: float | None = None,
        payee_name: str | None = None,
        category_id: str | None = None,
        memo: str | None = None,
        cleared: str | None = None,
        approved: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing transaction.

        Args:
            budget_id: The budget ID or 'last-used'
            transaction_id: The transaction ID to update
            account_id: The account ID
            date: Transaction date (YYYY-MM-DD)
            amount: Transaction amount (positive for inflow, negative for outflow)
            payee_name: Payee name
            category_id: Category ID
            memo: Transaction memo
            cleared: Cleared status ('cleared', 'uncleared', 'reconciled')
            approved: Whether transaction is approved

        Returns:
            Updated transaction dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions/{transaction_id}"

            # Build update payload with only provided fields
            transaction_data = {}
            if account_id is not None:
                transaction_data["account_id"] = account_id
            if date is not None:
                transaction_data["date"] = date
            if amount is not None:
                transaction_data["amount"] = int(amount * 1000)  # Convert to milliunits
            if payee_name is not None:
                transaction_data["payee_name"] = payee_name
            if category_id is not None:
                transaction_data["category_id"] = category_id
            if memo is not None:
                transaction_data["memo"] = memo
            if cleared is not None:
                transaction_data["cleared"] = cleared
            if approved is not None:
                transaction_data["approved"] = approved

            data = {"transaction": transaction_data}

            result = await self._make_request_with_retry("put", url, json=data)

            txn = result["data"]["transaction"]

            return {
                "id": txn["id"],
                "date": txn["date"],
                "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                "memo": txn.get("memo"),
                "cleared": txn.get("cleared"),
                "approved": txn.get("approved"),
                "account_id": txn.get("account_id"),
                "account_name": txn.get("account_name"),
                "payee_id": txn.get("payee_id"),
                "payee_name": txn.get("payee_name"),
                "category_id": txn.get("category_id"),
                "category_name": txn.get("category_name"),
            }
        except Exception as e:
            raise Exception(f"Failed to update transaction: {e}") from e

    def _generate_graph(self, data: list[tuple], title: str = "") -> str:
        """Generate a terminal graph using termgraph.

        Args:
            data: List of (label, value) tuples
            title: Graph title

        Returns:
            String containing the terminal graph
        """
        if not data:
            return ""

        # Capture termgraph output
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            # Prepare data for termgraph
            labels = [label for label, _ in data]
            values = [[abs(value)] for _, value in data]

            # Configure termgraph
            args = {
                "stacked": False,
                "width": 50,
                "format": "{:.2f}",
                "suffix": "",
                "no_labels": False,
                "color": None,
                "vertical": False,
                "different_scale": False,
                "calendar": False,
                "start_dt": None,
                "custom_tick": "",
                "delim": "",
                "verbose": False,
                "label_before": False,
                "histogram": False,
                "no_values": False,
            }

            # Print title
            if title:
                print(f"\n{title}")
                print("=" * len(title))

            # Generate graph
            tg.chart(colors=[], data=values, args=args, labels=labels)

            # Get the output
            output = sys.stdout.getvalue()
            return output

        finally:
            sys.stdout = old_stdout

    async def get_category_spending_summary(
        self,
        budget_id: str,
        category_id: str,
        since_date: str,
        until_date: str,
        include_graph: bool = True,
    ) -> dict[str, Any]:
        """Get spending summary for a category over a date range.

        Args:
            budget_id: The budget ID or 'last-used'
            category_id: The category ID to analyze
            since_date: Start date (YYYY-MM-DD)
            until_date: End date (YYYY-MM-DD)
            include_graph: Include terminal graph visualization (default: True)

        Returns:
            Summary with total spent, average, transaction count, and monthly breakdown
        """
        try:
            # Get transactions for the category
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"
            params = {"since_date": since_date}

            result = await self._make_request_with_retry("get", url, params=params)

            txn_data = result["data"]["transactions"]

            # Filter and aggregate
            total_spent = 0
            transaction_count = 0
            monthly_totals = {}

            for txn in txn_data:
                # Filter by category and date range
                if txn.get("category_id") != category_id:
                    continue
                if txn["date"] > until_date:
                    continue

                amount = txn["amount"] / 1000 if txn.get("amount") else 0
                total_spent += amount
                transaction_count += 1

                # Track monthly totals
                month_key = txn["date"][:7]  # YYYY-MM
                if month_key not in monthly_totals:
                    monthly_totals[month_key] = 0
                monthly_totals[month_key] += amount

            # Calculate average per month
            num_months = len(monthly_totals) if monthly_totals else 1
            average_per_month = total_spent / num_months if num_months > 0 else 0

            # Convert monthly totals to sorted list
            monthly_breakdown = [
                {"month": month, "spent": amount}
                for month, amount in sorted(monthly_totals.items())
            ]

            result = {
                "category_id": category_id,
                "date_range": {"start": since_date, "end": until_date},
                "total_spent": total_spent,
                "transaction_count": transaction_count,
                "average_per_month": average_per_month,
                "num_months": num_months,
                "monthly_breakdown": monthly_breakdown,
            }

            # Add graph if requested
            if include_graph and monthly_breakdown:
                graph_data = [(item["month"], item["spent"]) for item in monthly_breakdown]
                result["graph"] = self._generate_graph(
                    graph_data, f"Monthly Spending: {since_date} to {until_date}"
                )

            return result
        except Exception as e:
            raise Exception(f"Failed to get category spending summary: {e}") from e

    async def compare_spending_by_year(
        self,
        budget_id: str,
        category_id: str,
        start_year: int,
        num_years: int = 5,
        include_graph: bool = True,
    ) -> dict[str, Any]:
        """Compare spending for a category across multiple years.

        Args:
            budget_id: The budget ID or 'last-used'
            category_id: The category ID to analyze
            start_year: Starting year (e.g., 2020)
            num_years: Number of years to compare (default: 5)
            include_graph: Include terminal graph visualization (default: True)

        Returns:
            Year-over-year comparison with totals and percentage changes
        """
        try:
            # Get all transactions since the start year
            since_date = f"{start_year}-01-01"
            end_year = start_year + num_years - 1
            until_date = f"{end_year}-12-31"

            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"
            params = {"since_date": since_date}

            result = await self._make_request_with_retry("get", url, params=params)

            txn_data = result["data"]["transactions"]

            # Aggregate by year
            yearly_totals = {}
            for year in range(start_year, end_year + 1):
                yearly_totals[str(year)] = 0

            for txn in txn_data:
                # Filter by category and date range
                if txn.get("category_id") != category_id:
                    continue
                if txn["date"] > until_date:
                    continue

                year = txn["date"][:4]
                if year in yearly_totals:
                    amount = txn["amount"] / 1000 if txn.get("amount") else 0
                    yearly_totals[year] += amount

            # Calculate year-over-year changes
            comparisons = []
            years_sorted = sorted(yearly_totals.keys())

            for i, year in enumerate(years_sorted):
                year_data = {
                    "year": year,
                    "total_spent": yearly_totals[year],
                }

                if i > 0:
                    prev_year = years_sorted[i - 1]
                    prev_total = yearly_totals[prev_year]
                    change = yearly_totals[year] - prev_total

                    if prev_total != 0:
                        percent_change = (change / abs(prev_total)) * 100
                    else:
                        percent_change = 0 if change == 0 else float("inf")

                    year_data["change_from_previous"] = change
                    year_data["percent_change"] = percent_change

                comparisons.append(year_data)

            # Calculate overall statistics
            totals = [yearly_totals[year] for year in years_sorted]
            average_per_year = sum(totals) / len(totals) if totals else 0

            result_data = {
                "category_id": category_id,
                "years": f"{start_year}-{end_year}",
                "average_per_year": average_per_year,
                "yearly_comparison": comparisons,
            }

            # Add graph if requested
            if include_graph and yearly_totals:
                graph_data = [(year, yearly_totals[year]) for year in years_sorted]
                result_data["graph"] = self._generate_graph(
                    graph_data, f"Year-over-Year Comparison: {start_year}-{end_year}"
                )

            return result_data
        except Exception as e:
            raise Exception(f"Failed to compare spending by year: {e}") from e

    async def get_scheduled_transactions(self, budget_id: str) -> list[dict[str, Any]]:
        """Get all scheduled transactions.

        Args:
            budget_id: The budget ID or 'last-used'

        Returns:
            List of scheduled transaction dictionaries
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/scheduled_transactions"

            result = await self._make_request_with_retry("get", url)

            scheduled_txns = []
            for txn in result["data"]["scheduled_transactions"]:
                scheduled_txns.append(
                    {
                        "id": txn["id"],
                        "date_first": txn.get("date_first"),
                        "date_next": txn.get("date_next"),
                        "frequency": txn.get("frequency"),
                        "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                        "memo": txn.get("memo"),
                        "flag_color": txn.get("flag_color"),
                        "account_id": txn.get("account_id"),
                        "account_name": txn.get("account_name"),
                        "payee_id": txn.get("payee_id"),
                        "payee_name": txn.get("payee_name"),
                        "category_id": txn.get("category_id"),
                        "category_name": txn.get("category_name"),
                        "deleted": txn.get("deleted"),
                    }
                )

            return scheduled_txns
        except Exception as e:
            raise Exception(f"Failed to get scheduled transactions: {e}") from e

    async def create_scheduled_transaction(
        self,
        budget_id: str,
        account_id: str,
        date_first: str,
        frequency: str,
        amount: float,
        payee_name: str | None = None,
        category_id: str | None = None,
        memo: str | None = None,
        flag_color: str | None = None,
    ) -> dict[str, Any]:
        """Create a scheduled transaction.

        Args:
            budget_id: The budget ID or 'last-used'
            account_id: The account ID
            date_first: The first date the transaction should occur (YYYY-MM-DD)
            frequency: Frequency (never, daily, weekly, everyOtherWeek, twiceAMonth, every4Weeks, monthly, everyOtherMonth, every3Months, every4Months, twiceAYear, yearly, everyOtherYear)
            amount: Transaction amount (positive for inflow, negative for outflow)
            payee_name: Payee name (optional)
            category_id: Category ID (optional)
            memo: Transaction memo (optional)
            flag_color: Flag color (red, orange, yellow, green, blue, purple, optional)

        Returns:
            Created scheduled transaction dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/scheduled_transactions"

            scheduled_transaction_data = {
                "account_id": account_id,
                "date": date_first,
                "frequency": frequency,
                "amount": int(amount * 1000),  # Convert to milliunits
            }

            if payee_name is not None:
                scheduled_transaction_data["payee_name"] = payee_name
            if category_id is not None:
                scheduled_transaction_data["category_id"] = category_id
            if memo is not None:
                scheduled_transaction_data["memo"] = memo
            if flag_color is not None:
                scheduled_transaction_data["flag_color"] = flag_color

            data = {"scheduled_transaction": scheduled_transaction_data}

            result = await self._make_request_with_retry("post", url, json=data)

            txn = result["data"]["scheduled_transaction"]

            return {
                "id": txn["id"],
                "date_first": txn.get("date_first"),
                "date_next": txn.get("date_next"),
                "frequency": txn.get("frequency"),
                "amount": txn["amount"] / 1000 if txn.get("amount") else 0,
                "memo": txn.get("memo"),
                "flag_color": txn.get("flag_color"),
                "account_id": txn.get("account_id"),
                "payee_name": txn.get("payee_name"),
                "category_id": txn.get("category_id"),
            }
        except Exception as e:
            raise Exception(f"Failed to create scheduled transaction: {e}") from e

    async def delete_scheduled_transaction(
        self,
        budget_id: str,
        scheduled_transaction_id: str,
    ) -> dict[str, Any]:
        """Delete a scheduled transaction.

        Args:
            budget_id: The budget ID or 'last-used'
            scheduled_transaction_id: The scheduled transaction ID to delete

        Returns:
            Confirmation dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/scheduled_transactions/{scheduled_transaction_id}"

            result = await self._make_request_with_retry("delete", url)

            return {
                "scheduled_transaction": result["data"]["scheduled_transaction"],
                "deleted": True,
            }
        except Exception as e:
            raise Exception(f"Failed to delete scheduled transaction: {e}") from e

    async def get_unapproved_transactions(self, budget_id: str) -> list[dict[str, Any]]:
        """Get all unapproved transactions.

        Args:
            budget_id: The budget ID or 'last-used'

        Returns:
            List of unapproved transaction dictionaries
        """
        try:
            response = self.client.transactions.get_transactions(budget_id)

            transactions = []
            for txn in response.data.transactions:
                if not txn.approved and not txn.deleted:
                    transactions.append(
                        {
                            "id": txn.id,
                            "date": str(txn.date),
                            "amount": txn.amount / 1000 if txn.amount else 0,
                            "memo": txn.memo,
                            "cleared": txn.cleared,
                            "account_id": txn.account_id,
                            "account_name": txn.account_name,
                            "payee_id": txn.payee_id,
                            "payee_name": txn.payee_name,
                            "category_id": txn.category_id,
                            "category_name": txn.category_name,
                        }
                    )

            return transactions
        except Exception as e:
            raise Exception(f"Failed to get unapproved transactions: {e}") from e

    async def update_category_budget(
        self,
        budget_id: str,
        month: str,
        category_id: str,
        budgeted: float,
    ) -> dict[str, Any]:
        """Update the budgeted amount for a category in a specific month.

        Uses direct API calls since ynab-sdk is read-only.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format (e.g., 2025-01-01)
            category_id: The category ID to update
            budgeted: The budgeted amount to set

        Returns:
            Updated category dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/months/{month}/categories/{category_id}"
            data = {
                "category": {
                    "budgeted": int(budgeted * 1000)  # Convert to milliunits
                }
            }

            result = await self._make_request_with_retry("patch", url, json=data)

            cat = result["data"]["category"]
            return {
                "id": cat["id"],
                "name": cat["name"],
                "budgeted": cat["budgeted"] / 1000 if cat["budgeted"] else 0,
                "activity": cat["activity"] / 1000 if cat["activity"] else 0,
                "balance": cat["balance"] / 1000 if cat["balance"] else 0,
            }
        except Exception as e:
            raise Exception(f"Failed to update category budget: {e}") from e

    async def update_category(
        self,
        budget_id: str,
        category_id: str,
        name: str | None = None,
        note: str | None = None,
        category_group_id: str | None = None,
        goal_target: float | None = None,
    ) -> dict[str, Any]:
        """Update a category's properties.

        Args:
            budget_id: The budget ID or 'last-used'
            category_id: The category ID to update
            name: New name for the category (optional)
            note: New note for the category (optional)
            category_group_id: Move to a different category group (optional)
            goal_target: New goal target amount - only works if category already has a goal configured (optional)

        Returns:
            Updated category dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/categories/{category_id}"

            # Build update payload with only provided fields
            category_data = {}
            if name is not None:
                category_data["name"] = name
            if note is not None:
                category_data["note"] = note
            if category_group_id is not None:
                category_data["category_group_id"] = category_group_id
            if goal_target is not None:
                category_data["goal_target"] = int(goal_target * 1000)  # Convert to milliunits

            if not category_data:
                raise ValueError(
                    "At least one field (name, note, category_group_id, or goal_target) must be provided"
                )

            data = {"category": category_data}

            result = await self._make_request_with_retry("patch", url, json=data)

            cat = result["data"]["category"]
            return {
                "id": cat["id"],
                "name": cat["name"],
                "category_group_id": cat.get("category_group_id"),
                "note": cat.get("note"),
                "goal_type": cat.get("goal_type"),
                "goal_target": cat.get("goal_target", 0) / 1000 if cat.get("goal_target") else 0,
                "budgeted": cat.get("budgeted", 0) / 1000 if cat.get("budgeted") else 0,
                "activity": cat.get("activity", 0) / 1000 if cat.get("activity") else 0,
                "balance": cat.get("balance", 0) / 1000 if cat.get("balance") else 0,
            }
        except Exception as e:
            raise Exception(f"Failed to update category: {e}") from e

    async def move_category_funds(
        self,
        budget_id: str,
        month: str,
        from_category_id: str,
        to_category_id: str,
        amount: float,
    ) -> dict[str, Any]:
        """Move funds from one category to another in a specific month.

        Uses direct API calls since ynab-sdk is read-only.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format (e.g., 2025-01-01)
            from_category_id: Source category ID
            to_category_id: Destination category ID
            amount: Amount to move (positive value)

        Returns:
            Dictionary with updated from and to categories
        """
        try:
            # Get current budgeted amounts
            categories_response = self.client.categories.get_categories(budget_id)
            categories = {}
            for group in categories_response.data.category_groups:
                for cat in group.categories:
                    if cat.id in [from_category_id, to_category_id]:
                        categories[cat.id] = {"budgeted": cat.budgeted, "name": cat.name}

            if from_category_id not in categories or to_category_id not in categories:
                raise ValueError("One or both category IDs not found")

            # Calculate new budgeted amounts
            from_budgeted = (categories[from_category_id]["budgeted"] / 1000) - amount
            to_budgeted = (categories[to_category_id]["budgeted"] / 1000) + amount

            # Update both categories using direct API calls
            base_url = f"{self.api_base_url}/budgets/{budget_id}/months/{month}/categories"

            # Update from_category
            from_url = f"{base_url}/{from_category_id}"
            from_data = {"category": {"budgeted": int(from_budgeted * MILLIUNITS_FACTOR)}}
            from_result = await self._make_request_with_retry("patch", from_url, json=from_data)

            # Update to_category
            to_url = f"{base_url}/{to_category_id}"
            to_data = {"category": {"budgeted": int(to_budgeted * MILLIUNITS_FACTOR)}}
            to_result = await self._make_request_with_retry("patch", to_url, json=to_data)

            from_cat = from_result["data"]["category"]
            to_cat = to_result["data"]["category"]

            return {
                "from_category": {
                    "id": from_cat["id"],
                    "name": from_cat["name"],
                    "budgeted": from_cat["budgeted"] / 1000 if from_cat["budgeted"] else 0,
                    "balance": from_cat["balance"] / 1000 if from_cat["balance"] else 0,
                },
                "to_category": {
                    "id": to_cat["id"],
                    "name": to_cat["name"],
                    "budgeted": to_cat["budgeted"] / 1000 if to_cat["budgeted"] else 0,
                    "balance": to_cat["balance"] / 1000 if to_cat["balance"] else 0,
                },
                "amount_moved": amount,
            }
        except Exception as e:
            raise Exception(f"Failed to move category funds: {e}") from e

    async def get_transaction(
        self,
        budget_id: str,
        transaction_id: str,
    ) -> dict[str, Any]:
        """Get a single transaction with all details including subtransactions.

        Args:
            budget_id: The budget ID or 'last-used'
            transaction_id: The transaction ID to retrieve

        Returns:
            Transaction dictionary with full details
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions/{transaction_id}"
            result = await self._make_request_with_retry("get", url)

            txn = result["data"]["transaction"]

            # Format subtransactions if present
            subtransactions = []
            if txn.get("subtransactions"):
                for sub in txn["subtransactions"]:
                    subtransactions.append(
                        {
                            "id": sub.get("id"),
                            "amount": sub["amount"] / MILLIUNITS_FACTOR if sub.get("amount") else 0,
                            "memo": sub.get("memo"),
                            "payee_id": sub.get("payee_id"),
                            "payee_name": sub.get("payee_name"),
                            "category_id": sub.get("category_id"),
                            "category_name": sub.get("category_name"),
                        }
                    )

            return {
                "id": txn["id"],
                "date": txn["date"],
                "amount": txn["amount"] / MILLIUNITS_FACTOR if txn.get("amount") else 0,
                "memo": txn.get("memo"),
                "cleared": txn.get("cleared"),
                "approved": txn.get("approved"),
                "account_id": txn.get("account_id"),
                "account_name": txn.get("account_name"),
                "payee_id": txn.get("payee_id"),
                "payee_name": txn.get("payee_name"),
                "category_id": txn.get("category_id"),
                "category_name": txn.get("category_name"),
                "transfer_account_id": txn.get("transfer_account_id"),
                "subtransactions": subtransactions if subtransactions else None,
            }
        except Exception as e:
            raise Exception(f"Failed to get transaction: {e}") from e

    async def create_split_transaction(
        self,
        budget_id: str,
        account_id: str,
        date: str,
        amount: float,
        subtransactions: list[dict[str, Any]],
        payee_name: str | None = None,
        memo: str | None = None,
        cleared: str = "uncleared",
        approved: bool = False,
    ) -> dict[str, Any]:
        """Create a new split transaction with subtransactions.

        Args:
            budget_id: The budget ID or 'last-used'
            account_id: The account ID for this transaction
            date: Transaction date in YYYY-MM-DD format
            amount: Total transaction amount (positive for inflow, negative for outflow)
            subtransactions: List of subtransaction dictionaries, each containing:
                - amount (float, required): Subtransaction amount
                - category_id (str, optional): Category ID for this subtransaction
                - payee_id (str, optional): Payee ID for this subtransaction
                - memo (str, optional): Memo for this subtransaction
            payee_name: Name of the payee for the main transaction (optional)
            memo: Transaction memo (optional)
            cleared: Cleared status - 'cleared', 'uncleared', or 'reconciled' (default: 'uncleared')
            approved: Whether the transaction is approved (default: False)

        Returns:
            JSON string with the created split transaction

        Note:
            - The sum of subtransaction amounts should equal the total transaction amount
            - category_id on the main transaction will be set to null automatically for split transactions
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"

            # Format subtransactions
            formatted_subtransactions = []
            for sub in subtransactions:
                sub_data = {
                    "amount": int(sub["amount"] * MILLIUNITS_FACTOR),
                }
                if sub.get("category_id"):
                    sub_data["category_id"] = sub["category_id"]
                if sub.get("payee_id"):
                    sub_data["payee_id"] = sub["payee_id"]
                if sub.get("memo"):
                    sub_data["memo"] = sub["memo"]
                formatted_subtransactions.append(sub_data)

            # Build transaction data with subtransactions
            transaction_data = {
                "account_id": account_id,
                "date": date,
                "amount": int(amount * MILLIUNITS_FACTOR),
                "category_id": None,  # Must be null for split transactions
                "subtransactions": formatted_subtransactions,
                "cleared": cleared,
                "approved": approved,
            }

            if payee_name is not None:
                transaction_data["payee_name"] = payee_name
            if memo is not None:
                transaction_data["memo"] = memo

            data = {"transaction": transaction_data}

            result = await self._make_request_with_retry("post", url, json=data)

            txn = result["data"]["transaction"]

            # Format subtransactions in response
            subtransactions_response = []
            if txn.get("subtransactions"):
                for sub in txn["subtransactions"]:
                    subtransactions_response.append(
                        {
                            "id": sub.get("id"),
                            "amount": sub["amount"] / MILLIUNITS_FACTOR if sub.get("amount") else 0,
                            "memo": sub.get("memo"),
                            "payee_id": sub.get("payee_id"),
                            "payee_name": sub.get("payee_name"),
                            "category_id": sub.get("category_id"),
                            "category_name": sub.get("category_name"),
                        }
                    )

            return {
                "id": txn["id"],
                "date": txn["date"],
                "amount": txn["amount"] / MILLIUNITS_FACTOR if txn.get("amount") else 0,
                "memo": txn.get("memo"),
                "cleared": txn.get("cleared"),
                "approved": txn.get("approved"),
                "account_id": txn.get("account_id"),
                "account_name": txn.get("account_name"),
                "payee_id": txn.get("payee_id"),
                "payee_name": txn.get("payee_name"),
                "category_id": txn.get("category_id"),
                "category_name": txn.get("category_name"),
                "subtransactions": subtransactions_response,
            }
        except Exception as e:
            raise Exception(f"Failed to create split transaction: {e}") from e

    async def prepare_split_for_matching(
        self,
        budget_id: str,
        transaction_id: str,
        subtransactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Prepare a split transaction to match with an existing imported transaction.

        This fetches an existing transaction's details and creates a new unapproved split
        transaction with the same date, amount, account, and payee. You can then manually
        match them in the YNAB UI.

        Args:
            budget_id: The budget ID or 'last-used'
            transaction_id: The ID of the existing transaction to base the split on
            subtransactions: List of subtransaction dictionaries, each containing:
                - amount (float, required): Subtransaction amount
                - category_id (str, optional): Category ID for this subtransaction
                - payee_id (str, optional): Payee ID for this subtransaction
                - memo (str, optional): Memo for this subtransaction

        Returns:
            Dictionary with original transaction details and newly created split transaction

        Note:
            - The new split transaction is created as unapproved
            - You must manually match them in the YNAB UI
            - The sum of subtransaction amounts should equal the original transaction amount
        """
        try:
            # Fetch the original transaction details
            original = await self.get_transaction(budget_id, transaction_id)

            # Create a new split transaction with the same details but unapproved
            new_split = await self.create_split_transaction(
                budget_id=budget_id,
                account_id=original["account_id"],
                date=original["date"],
                amount=original["amount"],
                subtransactions=subtransactions,
                payee_name=original.get("payee_name"),
                memo=original.get("memo"),
                cleared=original.get("cleared", "uncleared"),
                approved=False,  # Always create as unapproved for manual matching
            )

            return {
                "original_transaction": {
                    "id": original["id"],
                    "date": original["date"],
                    "amount": original["amount"],
                    "payee_name": original.get("payee_name"),
                    "account_name": original.get("account_name"),
                },
                "new_split_transaction": new_split,
                "instructions": (
                    "A new unapproved split transaction has been created. "
                    "Go to YNAB and manually match these two transactions together. "
                    "Look for the match indicator in the YNAB UI."
                ),
            }
        except Exception as e:
            raise Exception(f"Failed to prepare split for matching: {e}") from e

    async def start_reconciliation(
        self,
        budget_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        """Start an interactive reconciliation session for an account.

        Retrieves the account's cleared balance and transaction counts to begin
        the reconciliation process. The cleared balance should be compared against
        the user's bank statement.

        Args:
            budget_id: The budget ID or 'last-used'
            account_id: The account ID to reconcile

        Returns:
            Dictionary with reconciliation session data:
            - account_id: The account ID
            - account_name: The account name
            - cleared_balance: Balance of all cleared transactions (compare to bank statement)
            - uncleared_balance: Balance of uncleared transactions
            - total_balance: Total account balance
            - cleared_transaction_count: Number of cleared transactions to be reconciled
            - uncleared_transaction_count: Number of uncleared transactions (will be left alone)
            - cleared_transaction_ids: List of transaction IDs that are cleared

        Next step:
            Ask the user if the cleared_balance matches their bank statement balance.
            Then call complete_reconciliation() with the user's response.
        """
        try:
            # Get account details
            url = f"{self.api_base_url}/budgets/{budget_id}/accounts/{account_id}"
            account_result = await self._make_request_with_retry("get", url)
            account = account_result["data"]["account"]

            # Get transactions for the account
            txn_url = f"{self.api_base_url}/budgets/{budget_id}/accounts/{account_id}/transactions"
            txn_result = await self._make_request_with_retry("get", txn_url)

            # Count cleared vs uncleared transactions, collect IDs of cleared ones
            cleared_count = 0
            uncleared_count = 0
            cleared_transaction_ids = []

            for txn in txn_result["data"]["transactions"]:
                if txn.get("deleted"):
                    continue

                if txn.get("cleared") == "cleared":
                    cleared_count += 1
                    cleared_transaction_ids.append(txn["id"])
                elif txn.get("cleared") == "uncleared":
                    uncleared_count += 1
                # Skip 'reconciled' transactions - they're already locked

            return {
                "account_id": account["id"],
                "account_name": account["name"],
                "cleared_balance": account["cleared_balance"] / MILLIUNITS_FACTOR
                if account.get("cleared_balance")
                else 0,
                "uncleared_balance": account["uncleared_balance"] / MILLIUNITS_FACTOR
                if account.get("uncleared_balance")
                else 0,
                "total_balance": account["balance"] / MILLIUNITS_FACTOR
                if account.get("balance")
                else 0,
                "cleared_transaction_count": cleared_count,
                "uncleared_transaction_count": uncleared_count,
                "cleared_transaction_ids": cleared_transaction_ids,
            }
        except Exception as e:
            raise Exception(f"Failed to start reconciliation: {e}") from e

    async def complete_reconciliation(
        self,
        budget_id: str,
        account_id: str,
        cleared_transaction_ids: list[str],
        matches: bool,
        bank_balance: float | None = None,
        create_adjustment: bool = False,
    ) -> dict[str, Any]:
        """Complete a reconciliation session.

        If balances match: marks all cleared transactions as reconciled (locks them).
        If balances don't match: calculates the discrepancy and optionally creates
        an adjustment transaction.

        Args:
            budget_id: The budget ID or 'last-used'
            account_id: The account ID being reconciled
            cleared_transaction_ids: List of transaction IDs that are cleared (from start_reconciliation)
            matches: True if YNAB cleared balance matches bank statement
            bank_balance: (required if matches=False) The actual bank statement balance
            create_adjustment: If True and there's a discrepancy, create an adjustment transaction

        Returns:
            Dictionary with reconciliation results:
            - If matches=True:
                - reconciled_count: Number of transactions marked as reconciled
                - status: "completed"
            - If matches=False:
                - ynab_cleared_balance: What YNAB shows
                - bank_balance: What the bank shows
                - difference: The discrepancy amount
                - adjustment_created: Whether an adjustment transaction was created
                - adjustment_transaction: Details of adjustment (if created)
                - status: "discrepancy_found" or "completed" (if adjustment created)

        Raises:
            YNABValidationError: If matches=False but bank_balance not provided
        """
        try:
            if matches:
                # Mark all cleared transactions as reconciled
                reconciled_count = 0
                for txn_id in cleared_transaction_ids:
                    try:
                        url = f"{self.api_base_url}/budgets/{budget_id}/transactions/{txn_id}"
                        data = {"transaction": {"cleared": "reconciled"}}
                        await self._make_request_with_retry("put", url, json=data)
                        reconciled_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to reconcile transaction {txn_id}: {e}")

                return {
                    "status": "completed",
                    "reconciled_count": reconciled_count,
                    "message": f"Successfully reconciled {reconciled_count} transactions.",
                }
            else:
                # Balances don't match - calculate discrepancy
                if bank_balance is None:
                    raise YNABValidationError(
                        "bank_balance is required when matches=False"
                    )

                # Get current cleared balance
                url = f"{self.api_base_url}/budgets/{budget_id}/accounts/{account_id}"
                account_result = await self._make_request_with_retry("get", url)
                account = account_result["data"]["account"]

                ynab_cleared = (
                    account["cleared_balance"] / MILLIUNITS_FACTOR
                    if account.get("cleared_balance")
                    else 0
                )
                difference = bank_balance - ynab_cleared

                result = {
                    "status": "discrepancy_found",
                    "ynab_cleared_balance": ynab_cleared,
                    "bank_balance": bank_balance,
                    "difference": difference,
                    "adjustment_created": False,
                }

                if create_adjustment:
                    # Create adjustment transaction
                    import datetime

                    adjustment_txn = await self.create_transaction(
                        budget_id=budget_id,
                        account_id=account_id,
                        date=datetime.date.today().isoformat(),
                        amount=difference,
                        payee_name="Reconciliation Adjustment",
                        memo=f"Adjustment to match bank balance of {bank_balance}",
                        cleared="cleared",
                        approved=True,
                    )

                    result["adjustment_created"] = True
                    result["adjustment_transaction"] = adjustment_txn
                    result["status"] = "completed_with_adjustment"
                    result["message"] = (
                        f"Created adjustment transaction for {difference}. "
                        f"Balances should now match."
                    )

                return result

        except Exception as e:
            raise Exception(f"Failed to complete reconciliation: {e}") from e
