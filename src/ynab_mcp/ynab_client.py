"""YNAB API client wrapper with authentication."""

from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
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
        self.access_token = access_token
        self.api_base_url = "https://api.ynab.com/v1"

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

    async def get_accounts(self, budget_id: str) -> List[Dict[str, Any]]:
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

                accounts.append({
                    "id": account.id,
                    "name": account.name,
                    "type": account.type,
                    "on_budget": account.on_budget,
                    "closed": account.closed,
                    "balance": account.balance / 1000 if account.balance else 0,
                })

            return accounts
        except Exception as e:
            raise Exception(f"Failed to get accounts: {e}")

    async def get_categories(self, budget_id: str, include_hidden: bool = False) -> List[Dict[str, Any]]:
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

                    categories.append({
                        "id": category.id,
                        "name": category.name,
                        "balance": category.balance / 1000 if category.balance else 0,
                        "hidden": category.hidden,
                    })

                # Skip hidden groups unless requested, and skip empty groups
                if (not include_hidden and group.hidden) or not categories:
                    continue

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

        Uses direct API to get month-specific data since SDK doesn't support it.

        Args:
            budget_id: The budget ID or 'last-used'
            month: Month in YYYY-MM-DD format

        Returns:
            Budget summary dictionary
        """
        try:
            # Use direct API call to get month-specific budget data
            url = f"{self.api_base_url}/budgets/{budget_id}/months/{month}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()

            month_data = result["data"]["month"]

            # Debug: Check what keys are available
            if "categories" not in month_data:
                raise Exception(f"Month data keys: {list(month_data.keys())}")

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
            for category in month_data.get("categories", []):
                budgeted = category["budgeted"] / 1000 if category["budgeted"] else 0
                activity = category["activity"] / 1000 if category["activity"] else 0
                balance = category["balance"] / 1000 if category["balance"] else 0

                total_budgeted += budgeted
                total_activity += activity
                total_balance += balance

                category_group_name = category_group_map.get(category["id"], "Unknown")

                categories.append({
                    "category_group": category_group_name,
                    "category_name": category["name"],
                    "budgeted": budgeted,
                    "activity": activity,
                    "balance": balance,
                })

            return {
                "month": month,
                "income": month_data["income"] / 1000 if month_data.get("income") else 0,
                "budgeted": total_budgeted,
                "activity": total_activity,
                "balance": total_balance,
                "to_be_budgeted": month_data["to_be_budgeted"] / 1000 if month_data.get("to_be_budgeted") else 0,
                "categories": categories,
            }
        except Exception as e:
            raise Exception(f"Failed to get budget summary: {e}")

    async def get_transactions(
        self,
        budget_id: str,
        since_date: Optional[str] = None,
        account_id: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get transactions with optional filtering.

        Args:
            budget_id: The budget ID or 'last-used'
            since_date: Only return transactions on or after this date (YYYY-MM-DD)
            account_id: Filter by account ID
            category_id: Filter by category ID

        Returns:
            List of transaction dictionaries
        """
        try:
            # Use direct API call for better filtering support
            url = f"{self.api_base_url}/budgets/{budget_id}/transactions"
            params = {}
            if since_date:
                params["since_date"] = since_date
            if account_id:
                url = f"{self.api_base_url}/budgets/{budget_id}/accounts/{account_id}/transactions"

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                result = response.json()

            txn_data = result["data"]["transactions"]

            transactions = []
            for txn in txn_data:
                # Filter by category_id if provided
                if category_id and txn.get("category_id") != category_id:
                    continue

                transactions.append({
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
                })

            return transactions
        except Exception as e:
            raise Exception(f"Failed to get transactions: {e}")

    async def create_transaction(
        self,
        budget_id: str,
        account_id: str,
        date: str,
        amount: float,
        payee_name: Optional[str] = None,
        category_id: Optional[str] = None,
        memo: Optional[str] = None,
        cleared: str = "uncleared",
        approved: bool = False,
    ) -> Dict[str, Any]:
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
            from ynab_sdk.api.models.requests.transaction import TransactionRequest

            transaction = TransactionRequest(
                account_id=account_id,
                date=datetime.strptime(date, "%Y-%m-%d").date(),
                amount=int(amount * 1000),  # Convert to milliunits
                payee_name=payee_name,
                category_id=category_id,
                memo=memo,
                cleared=cleared,
                approved=approved,
            )

            response = self.client.transactions.create_transaction(budget_id, transaction)
            txn = response.data.transaction

            return {
                "id": txn.id,
                "date": str(txn.date),
                "amount": txn.amount / 1000 if txn.amount else 0,
                "memo": txn.memo,
                "cleared": txn.cleared,
                "approved": txn.approved,
                "account_id": txn.account_id,
                "account_name": txn.account_name,
                "payee_id": txn.payee_id,
                "payee_name": txn.payee_name,
                "category_id": txn.category_id,
                "category_name": txn.category_name,
            }
        except Exception as e:
            raise Exception(f"Failed to create transaction: {e}")

    async def update_transaction(
        self,
        budget_id: str,
        transaction_id: str,
        account_id: Optional[str] = None,
        date: Optional[str] = None,
        amount: Optional[float] = None,
        payee_name: Optional[str] = None,
        category_id: Optional[str] = None,
        memo: Optional[str] = None,
        cleared: Optional[str] = None,
        approved: Optional[bool] = None,
    ) -> Dict[str, Any]:
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
            from ynab_sdk.api.models.requests.transaction import TransactionRequest

            # First get the existing transaction
            existing = self.client.transactions.get_transaction_by_id(budget_id, transaction_id)
            existing_txn = existing.data.transaction

            # Build update with provided values or existing values
            transaction = TransactionRequest(
                account_id=account_id if account_id else existing_txn.account_id,
                date=datetime.strptime(date, "%Y-%m-%d").date() if date else existing_txn.date,
                amount=int(amount * 1000) if amount is not None else existing_txn.amount,
                payee_name=payee_name if payee_name is not None else existing_txn.payee_name,
                category_id=category_id if category_id is not None else existing_txn.category_id,
                memo=memo if memo is not None else existing_txn.memo,
                cleared=cleared if cleared else existing_txn.cleared,
                approved=approved if approved is not None else existing_txn.approved,
            )

            response = self.client.transactions.update_transaction(budget_id, transaction_id, transaction)
            txn = response.data.transaction

            return {
                "id": txn.id,
                "date": str(txn.date),
                "amount": txn.amount / 1000 if txn.amount else 0,
                "memo": txn.memo,
                "cleared": txn.cleared,
                "approved": txn.approved,
                "account_id": txn.account_id,
                "account_name": txn.account_name,
                "payee_id": txn.payee_id,
                "payee_name": txn.payee_name,
                "category_id": txn.category_id,
                "category_name": txn.category_name,
            }
        except Exception as e:
            raise Exception(f"Failed to update transaction: {e}")

    async def get_unapproved_transactions(self, budget_id: str) -> List[Dict[str, Any]]:
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
                    transactions.append({
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
                    })

            return transactions
        except Exception as e:
            raise Exception(f"Failed to get unapproved transactions: {e}")

    async def update_category_budget(
        self,
        budget_id: str,
        month: str,
        category_id: str,
        budgeted: float,
    ) -> Dict[str, Any]:
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
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            data = {
                "category": {
                    "budgeted": int(budgeted * 1000)  # Convert to milliunits
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.patch(url, json=data, headers=headers)
                response.raise_for_status()
                result = response.json()

            cat = result["data"]["category"]
            return {
                "id": cat["id"],
                "name": cat["name"],
                "budgeted": cat["budgeted"] / 1000 if cat["budgeted"] else 0,
                "activity": cat["activity"] / 1000 if cat["activity"] else 0,
                "balance": cat["balance"] / 1000 if cat["balance"] else 0,
            }
        except Exception as e:
            raise Exception(f"Failed to update category budget: {e}")

    async def update_category(
        self,
        budget_id: str,
        category_id: str,
        name: Optional[str] = None,
        note: Optional[str] = None,
        category_group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a category's properties.

        Args:
            budget_id: The budget ID or 'last-used'
            category_id: The category ID to update
            name: New name for the category (optional)
            note: New note for the category (optional)
            category_group_id: Move to a different category group (optional)

        Returns:
            Updated category dictionary
        """
        try:
            url = f"{self.api_base_url}/budgets/{budget_id}/categories/{category_id}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Build update payload with only provided fields
            category_data = {}
            if name is not None:
                category_data["name"] = name
            if note is not None:
                category_data["note"] = note
            if category_group_id is not None:
                category_data["category_group_id"] = category_group_id

            if not category_data:
                raise ValueError("At least one field (name, note, or category_group_id) must be provided")

            data = {"category": category_data}

            async with httpx.AsyncClient() as client:
                response = await client.patch(url, json=data, headers=headers)
                response.raise_for_status()
                result = response.json()

            cat = result["data"]["category"]
            return {
                "id": cat["id"],
                "name": cat["name"],
                "category_group_id": cat.get("category_group_id"),
                "note": cat.get("note"),
                "budgeted": cat.get("budgeted", 0) / 1000 if cat.get("budgeted") else 0,
                "activity": cat.get("activity", 0) / 1000 if cat.get("activity") else 0,
                "balance": cat.get("balance", 0) / 1000 if cat.get("balance") else 0,
            }
        except Exception as e:
            raise Exception(f"Failed to update category: {e}")

    async def move_category_funds(
        self,
        budget_id: str,
        month: str,
        from_category_id: str,
        to_category_id: str,
        amount: float,
    ) -> Dict[str, Any]:
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
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                # Update from_category
                from_response = await client.patch(
                    f"{base_url}/{from_category_id}",
                    json={"category": {"budgeted": int(from_budgeted * 1000)}},
                    headers=headers,
                )
                from_response.raise_for_status()
                from_result = from_response.json()

                # Update to_category
                to_response = await client.patch(
                    f"{base_url}/{to_category_id}",
                    json={"category": {"budgeted": int(to_budgeted * 1000)}},
                    headers=headers,
                )
                to_response.raise_for_status()
                to_result = to_response.json()

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
            raise Exception(f"Failed to move category funds: {e}")
