"""YNAB API client wrapper with authentication."""

from typing import Optional, Dict, Any, List
from ynab_sdk import YNAB


class YNABClient:
    """Wrapper around YNAB SDK for MCP server."""

    def __init__(self, access_token: Optional[str]):
        """Initialize YNAB client with access token.

        Args:
            access_token: YNAB Personal Access Token

        Raises:
            ValueError: If access token is not provided
        """
        if not access_token:
            raise ValueError(
                "YNAB_ACCESS_TOKEN environment variable must be set. "
                "Get your token at: https://app.ynab.com/settings/developer"
            )

        # Initialize YNAB SDK client
        self.client = YNAB(access_token)

    async def get_budgets(self) -> List[Dict[str, Any]]:
        """Get all budgets for the authenticated user.

        Returns:
            List of budget dictionaries
        """
        try:
            response = self.client.budgets.get_budgets()
            budgets = []
            for budget in response.data.budgets:
                budgets.append({
                    "id": budget.id,
                    "name": budget.name,
                    "last_modified_on": str(budget.last_modified_on) if budget.last_modified_on else None,
                    "currency_format": {
                        "iso_code": budget.currency_format.iso_code,
                        "example_format": budget.currency_format.example_format,
                        "currency_symbol": budget.currency_format.currency_symbol,
                    }
                })
            return budgets
        except Exception as e:
            raise Exception(f"Failed to get budgets: {e}")

    async def get_categories(self, budget_id: str) -> List[Dict[str, Any]]:
        """Get all categories for a budget.

        Args:
            budget_id: The budget ID or 'last-used'

        Returns:
            List of category dictionaries grouped by category groups
        """
        try:
            response = self.client.categories.get_categories(budget_id)
            category_groups = []

            for group in response.data.category_groups:
                categories = []
                for category in group.categories:
                    categories.append({
                        "id": category.id,
                        "name": category.name,
                        "hidden": category.hidden,
                        "budgeted": category.budgeted / 1000 if category.budgeted else 0,  # Convert from milliunits
                        "activity": category.activity / 1000 if category.activity else 0,
                        "balance": category.balance / 1000 if category.balance else 0,
                    })

                category_groups.append({
                    "id": group.id,
                    "name": group.name,
                    "hidden": group.hidden,
                    "categories": categories,
                })

            return category_groups
        except Exception as e:
            raise Exception(f"Failed to get categories: {e}")

    async def get_budget_summary(self, budget_id: str, month: str) -> Dict[str, Any]:
        """Get budget summary for a specific month.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format

        Returns:
            Budget summary dictionary
        """
        try:
            response = self.client.months.get_month(budget_id, month)
            month_data = response.data.month

            # Get category details from categories endpoint
            categories_response = self.client.categories.get_categories(budget_id)
            category_groups = categories_response.data.category_groups

            # Calculate totals and collect category details
            total_budgeted = 0
            total_activity = 0
            categories = []

            for group in category_groups:
                for category in group.categories:
                    budgeted = category.budgeted / 1000 if category.budgeted else 0
                    activity = category.activity / 1000 if category.activity else 0
                    balance = category.balance / 1000 if category.balance else 0

                    total_budgeted += budgeted
                    total_activity += activity

                    categories.append({
                        "category_group": group.name,
                        "category_name": category.name,
                        "budgeted": budgeted,
                        "activity": activity,
                        "balance": balance,
                    })

            return {
                "month": month,
                "income": month_data.income / 1000 if month_data.income else 0,
                "budgeted": total_budgeted,
                "activity": total_activity,
                "to_be_budgeted": month_data.to_be_budgeted / 1000 if month_data.to_be_budgeted else 0,
                "categories": categories,
            }
        except Exception as e:
            raise Exception(f"Failed to get budget summary: {e}")
