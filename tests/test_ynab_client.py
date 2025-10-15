"""Tests for YNAB client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ynab_mcp.exceptions import YNABValidationError
from src.ynab_mcp.ynab_client import YNABClient


@pytest.fixture
def mock_ynab_sdk():
    """Mock YNAB SDK."""
    with patch("src.ynab_mcp.ynab_client.YNAB") as mock:
        yield mock


@pytest.fixture
def client(mock_ynab_sdk):
    """Create YNABClient instance with mocked SDK."""
    return YNABClient("test_token")


def test_client_initialization():
    """Test client initializes with access token."""
    client = YNABClient("test_token")
    assert client._access_token == "test_token"
    assert client.api_base_url == "https://api.ynab.com/v1"


def test_client_initialization_fails_without_token():
    """Test client raises error without access token."""
    with pytest.raises(
        YNABValidationError, match="YNAB_ACCESS_TOKEN environment variable must be set"
    ):
        YNABClient(None)


@pytest.mark.asyncio
async def test_get_budgets(client, mock_ynab_sdk):
    """Test get_budgets returns formatted budget list."""
    # Mock budget response
    mock_budget = MagicMock()
    mock_budget.id = "budget-123"
    mock_budget.name = "Test Budget"
    mock_budget.last_modified_on = "2025-10-05"
    mock_budget.currency_format.iso_code = "USD"
    mock_budget.currency_format.example_format = "$123.45"
    mock_budget.currency_format.currency_symbol = "$"

    mock_response = MagicMock()
    mock_response.data.budgets = [mock_budget]
    client.client.budgets.get_budgets.return_value = mock_response

    result = await client.get_budgets()

    assert len(result) == 1
    assert result[0]["id"] == "budget-123"
    assert result[0]["name"] == "Test Budget"
    assert result[0]["currency_format"]["iso_code"] == "USD"


@pytest.mark.asyncio
async def test_get_accounts(client, mock_ynab_sdk):
    """Test get_accounts returns formatted account list."""
    # Mock account response
    mock_account = MagicMock()
    mock_account.id = "account-123"
    mock_account.name = "Checking"
    mock_account.type = "checking"
    mock_account.on_budget = True
    mock_account.closed = False
    mock_account.balance = 10000000  # $10,000 in milliunits
    mock_account.deleted = False

    mock_response = MagicMock()
    mock_response.data.accounts = [mock_account]
    client.client.accounts.get_accounts.return_value = mock_response

    result = await client.get_accounts("budget-123")

    assert len(result) == 1
    assert result[0]["id"] == "account-123"
    assert result[0]["name"] == "Checking"
    assert result[0]["balance"] == 10000.0  # Converted from milliunits


@pytest.mark.asyncio
async def test_get_accounts_skips_deleted(client, mock_ynab_sdk):
    """Test get_accounts skips deleted accounts."""
    # Mock deleted account
    mock_account = MagicMock()
    mock_account.deleted = True

    mock_response = MagicMock()
    mock_response.data.accounts = [mock_account]
    client.client.accounts.get_accounts.return_value = mock_response

    result = await client.get_accounts("budget-123")

    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_categories(client, mock_ynab_sdk):
    """Test get_categories returns formatted category list."""
    # Mock category response
    mock_category = MagicMock()
    mock_category.id = "cat-123"
    mock_category.name = "Groceries"
    mock_category.balance = 50000  # $50 in milliunits
    mock_category.hidden = False
    mock_category.deleted = False

    mock_group = MagicMock()
    mock_group.id = "group-123"
    mock_group.name = "Food"
    mock_group.hidden = False
    mock_group.categories = [mock_category]

    mock_response = MagicMock()
    mock_response.data.category_groups = [mock_group]
    client.client.categories.get_categories.return_value = mock_response

    result = await client.get_categories("budget-123")

    assert len(result) == 1
    assert result[0]["name"] == "Food"
    assert len(result[0]["categories"]) == 1
    assert result[0]["categories"][0]["name"] == "Groceries"
    assert result[0]["categories"][0]["balance"] == 50.0


@pytest.mark.asyncio
async def test_get_categories_skips_hidden_by_default(client, mock_ynab_sdk):
    """Test get_categories skips hidden categories by default."""
    # Mock hidden category
    mock_category = MagicMock()
    mock_category.hidden = True
    mock_category.deleted = False

    mock_group = MagicMock()
    mock_group.id = "group-123"
    mock_group.name = "Hidden Group"
    mock_group.hidden = False
    mock_group.categories = [mock_category]

    mock_response = MagicMock()
    mock_response.data.category_groups = [mock_group]
    client.client.categories.get_categories.return_value = mock_response

    result = await client.get_categories("budget-123", include_hidden=False)

    # Should skip the group since it has no visible categories
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_categories_includes_hidden_when_requested(client, mock_ynab_sdk):
    """Test get_categories includes hidden categories when requested."""
    # Mock hidden category
    mock_category = MagicMock()
    mock_category.id = "cat-123"
    mock_category.name = "Hidden Cat"
    mock_category.balance = 0
    mock_category.hidden = True
    mock_category.deleted = False

    mock_group = MagicMock()
    mock_group.id = "group-123"
    mock_group.name = "Group"
    mock_group.hidden = False
    mock_group.categories = [mock_category]

    mock_response = MagicMock()
    mock_response.data.category_groups = [mock_group]
    client.client.categories.get_categories.return_value = mock_response

    result = await client.get_categories("budget-123", include_hidden=True)

    assert len(result) == 1
    assert result[0]["categories"][0]["hidden"]


@pytest.mark.asyncio
async def test_milliunits_conversion():
    """Test milliunits conversion for various amounts."""
    YNABClient("test_token")

    # Test conversion from milliunits to dollars
    assert 10000000 / 1000 == 10000.0
    assert 1234567 / 1000 == 1234.567
    assert -50000 / 1000 == -50.0

    # Test conversion from dollars to milliunits
    assert int(100.50 * 1000) == 100500
    assert int(-25.75 * 1000) == -25750


@pytest.mark.asyncio
async def test_search_transactions_handles_null_fields(client):
    """Test search_transactions handles null payee_name and memo."""
    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {
            "data": {
                "transactions": [
                    {
                        "id": "txn-1",
                        "date": "2025-10-01",
                        "amount": -5000,
                        "payee_name": None,
                        "memo": None,
                    },
                    {
                        "id": "txn-2",
                        "date": "2025-10-02",
                        "amount": -3000,
                        "payee_name": "Store",
                        "memo": "groceries",
                    },
                ]
            }
        }

        result = await client.search_transactions("budget-123", "groceries")

        # Should find the transaction with "groceries" in memo
        assert result["count"] == 1
        assert result["transactions"][0]["id"] == "txn-2"


@pytest.mark.asyncio
async def test_pagination_calculations(client):
    """Test pagination metadata calculations."""
    # Mock 250 transactions
    transactions = [
        {
            "id": f"txn-{i}",
            "date": "2025-10-01",
            "amount": -1000,
        }
        for i in range(250)
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        # Get page 1 with limit 100
        result = await client.get_transactions("budget-123", limit=100, page=1)

        assert result["pagination"]["page"] == 1
        assert result["pagination"]["per_page"] == 100
        assert result["pagination"]["total_count"] == 250
        assert result["pagination"]["total_pages"] == 3
        assert result["pagination"]["has_next_page"]
        assert not result["pagination"]["has_prev_page"]
        assert len(result["transactions"]) == 100

        # Get page 3 (last page)
        result = await client.get_transactions("budget-123", limit=100, page=3)

        assert result["pagination"]["page"] == 3
        assert not result["pagination"]["has_next_page"]
        assert result["pagination"]["has_prev_page"]
        assert len(result["transactions"]) == 50  # Remaining transactions


@pytest.mark.asyncio
async def test_get_category_spending_summary(client):
    """Test get_category_spending_summary aggregates correctly."""
    # Mock transactions over 3 months
    transactions = [
        # January 2025
        {"id": "txn-1", "date": "2025-01-15", "amount": -10000, "category_id": "cat-123"},
        {"id": "txn-2", "date": "2025-01-20", "amount": -15000, "category_id": "cat-123"},
        # February 2025
        {"id": "txn-3", "date": "2025-02-10", "amount": -12000, "category_id": "cat-123"},
        {"id": "txn-4", "date": "2025-02-25", "amount": -13000, "category_id": "cat-123"},
        # March 2025
        {"id": "txn-5", "date": "2025-03-05", "amount": -11000, "category_id": "cat-123"},
        # Different category (should be excluded)
        {"id": "txn-6", "date": "2025-01-10", "amount": -5000, "category_id": "cat-999"},
        # Outside date range (should be excluded)
        {"id": "txn-7", "date": "2025-04-01", "amount": -20000, "category_id": "cat-123"},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        result = await client.get_category_spending_summary(
            "budget-123", "cat-123", "2025-01-01", "2025-03-31", include_graph=False
        )

        # Total: -10 + -15 + -12 + -13 + -11 = -61
        assert result["total_spent"] == -61.0
        assert result["transaction_count"] == 5
        assert result["num_months"] == 3
        assert result["average_per_month"] == pytest.approx(-20.333, rel=0.01)
        assert "graph" not in result  # Graph should not be included

        # Check monthly breakdown
        assert len(result["monthly_breakdown"]) == 3
        assert result["monthly_breakdown"][0]["month"] == "2025-01"
        assert result["monthly_breakdown"][0]["spent"] == -25.0
        assert result["monthly_breakdown"][1]["month"] == "2025-02"
        assert result["monthly_breakdown"][1]["spent"] == -25.0
        assert result["monthly_breakdown"][2]["month"] == "2025-03"
        assert result["monthly_breakdown"][2]["spent"] == -11.0


@pytest.mark.asyncio
async def test_compare_spending_by_year(client):
    """Test compare_spending_by_year calculates year-over-year correctly."""
    # Mock transactions over 3 years
    transactions = [
        # 2023: $100 total
        {"id": "txn-1", "date": "2023-03-15", "amount": -50000, "category_id": "cat-123"},
        {"id": "txn-2", "date": "2023-09-20", "amount": -50000, "category_id": "cat-123"},
        # 2024: $150 total (50% increase)
        {"id": "txn-3", "date": "2024-02-10", "amount": -75000, "category_id": "cat-123"},
        {"id": "txn-4", "date": "2024-08-25", "amount": -75000, "category_id": "cat-123"},
        # 2025: $120 total (20% decrease)
        {"id": "txn-5", "date": "2025-01-05", "amount": -60000, "category_id": "cat-123"},
        {"id": "txn-6", "date": "2025-06-15", "amount": -60000, "category_id": "cat-123"},
        # Different category (should be excluded)
        {"id": "txn-7", "date": "2024-05-10", "amount": -30000, "category_id": "cat-999"},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        result = await client.compare_spending_by_year(
            "budget-123", "cat-123", 2023, 3, include_graph=False
        )

        assert result["years"] == "2023-2025"
        assert result["average_per_year"] == pytest.approx(-123.333, rel=0.01)
        assert "graph" not in result  # Graph should not be included

        # Check yearly comparison
        assert len(result["yearly_comparison"]) == 3

        # 2023
        assert result["yearly_comparison"][0]["year"] == "2023"
        assert result["yearly_comparison"][0]["total_spent"] == -100.0
        assert "change_from_previous" not in result["yearly_comparison"][0]

        # 2024 (50% increase in spending - more negative)
        assert result["yearly_comparison"][1]["year"] == "2024"
        assert result["yearly_comparison"][1]["total_spent"] == -150.0
        assert result["yearly_comparison"][1]["change_from_previous"] == -50.0
        # Change is -50 / |-100| * 100 = -50% (spending increased)
        assert result["yearly_comparison"][1]["percent_change"] == pytest.approx(-50.0, rel=0.01)

        # 2025 (20% decrease in spending - less negative)
        assert result["yearly_comparison"][2]["year"] == "2025"
        assert result["yearly_comparison"][2]["total_spent"] == -120.0
        assert result["yearly_comparison"][2]["change_from_previous"] == 30.0
        # Change is 30 / |-150| * 100 = 20% (spending decreased)
        assert result["yearly_comparison"][2]["percent_change"] == pytest.approx(20.0, rel=0.01)


@pytest.mark.asyncio
async def test_compare_spending_by_year_handles_zero_spending(client):
    """Test compare_spending_by_year handles years with zero spending."""
    # Mock transactions with gap year
    transactions = [
        {"id": "txn-1", "date": "2023-03-15", "amount": -10000, "category_id": "cat-123"},
        # 2024 has no transactions
        {"id": "txn-2", "date": "2025-01-20", "amount": -10000, "category_id": "cat-123"},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        result = await client.compare_spending_by_year(
            "budget-123", "cat-123", 2023, 3, include_graph=False
        )

        # Check that 2024 has zero spending
        assert result["yearly_comparison"][1]["year"] == "2024"
        assert result["yearly_comparison"][1]["total_spent"] == 0.0
        assert "graph" not in result

        # Check that percentage change handles zero correctly
        # Change is 10 / |-10| * 100 = 100%
        assert result["yearly_comparison"][1]["change_from_previous"] == 10.0
        assert result["yearly_comparison"][1]["percent_change"] == pytest.approx(100.0, rel=0.01)


@pytest.mark.asyncio
async def test_get_category_spending_summary_with_graph(client):
    """Test get_category_spending_summary includes graph when requested."""
    # Mock transactions over 2 months
    transactions = [
        {"id": "txn-1", "date": "2025-01-15", "amount": -10000, "category_id": "cat-123"},
        {"id": "txn-2", "date": "2025-02-10", "amount": -20000, "category_id": "cat-123"},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        result = await client.get_category_spending_summary(
            "budget-123", "cat-123", "2025-01-01", "2025-02-28", include_graph=True
        )

        # Verify graph is included
        assert "graph" in result
        assert isinstance(result["graph"], str)
        assert len(result["graph"]) > 0
        # Check that graph contains the month labels
        assert "2025-01" in result["graph"]
        assert "2025-02" in result["graph"]


@pytest.mark.asyncio
async def test_compare_spending_by_year_with_graph(client):
    """Test compare_spending_by_year includes graph when requested."""
    # Mock transactions over 2 years
    transactions = [
        {"id": "txn-1", "date": "2023-03-15", "amount": -50000, "category_id": "cat-123"},
        {"id": "txn-2", "date": "2024-02-10", "amount": -75000, "category_id": "cat-123"},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transactions": transactions}}

        result = await client.compare_spending_by_year(
            "budget-123", "cat-123", 2023, 2, include_graph=True
        )

        # Verify graph is included
        assert "graph" in result
        assert isinstance(result["graph"], str)
        assert len(result["graph"]) > 0
        # Check that graph contains the year labels
        assert "2023" in result["graph"]
        assert "2024" in result["graph"]


@pytest.mark.asyncio
async def test_get_scheduled_transactions(client):
    """Test get_scheduled_transactions returns formatted scheduled transactions."""
    # Mock scheduled transactions response
    scheduled_txns = [
        {
            "id": "sched-1",
            "date_first": "2025-11-01",
            "date_next": "2025-11-01",
            "frequency": "monthly",
            "amount": -100000,
            "memo": "Rent",
            "flag_color": "red",
            "account_id": "account-123",
            "account_name": "Checking",
            "payee_id": "payee-1",
            "payee_name": "Landlord",
            "category_id": "cat-123",
            "category_name": "Housing",
        },
        {
            "id": "sched-2",
            "date_first": "2025-10-15",
            "date_next": "2025-10-29",
            "frequency": "everyOtherWeek",
            "amount": 200000,
            "memo": "Paycheck",
            "flag_color": None,
            "account_id": "account-123",
            "account_name": "Checking",
            "payee_id": "payee-2",
            "payee_name": "Employer",
            "category_id": None,
            "category_name": None,
        },
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"scheduled_transactions": scheduled_txns}}

        result = await client.get_scheduled_transactions("budget-123")

        assert len(result) == 2

        # Check first scheduled transaction
        assert result[0]["id"] == "sched-1"
        assert result[0]["frequency"] == "monthly"
        assert result[0]["amount"] == -100.0
        assert result[0]["payee_name"] == "Landlord"
        assert result[0]["memo"] == "Rent"

        # Check second scheduled transaction
        assert result[1]["id"] == "sched-2"
        assert result[1]["frequency"] == "everyOtherWeek"
        assert result[1]["amount"] == 200.0
        assert result[1]["payee_name"] == "Employer"


@pytest.mark.asyncio
async def test_create_scheduled_transaction(client):
    """Test create_scheduled_transaction sends correct data."""
    # Mock successful creation response
    created_txn = {
        "id": "sched-new",
        "date_first": "2025-12-01",
        "date_next": "2025-12-01",
        "frequency": "monthly",
        "amount": -50000,
        "memo": "Internet Bill",
        "flag_color": "blue",
        "account_id": "account-123",
        "payee_name": "ISP Provider",
        "category_id": "cat-456",
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"scheduled_transaction": created_txn}}

        result = await client.create_scheduled_transaction(
            budget_id="budget-123",
            account_id="account-123",
            date_first="2025-12-01",
            frequency="monthly",
            amount=-50.0,
            payee_name="ISP Provider",
            category_id="cat-456",
            memo="Internet Bill",
            flag_color="blue",
        )

        assert result["id"] == "sched-new"
        assert result["frequency"] == "monthly"
        assert result["amount"] == -50.0
        assert result["payee_name"] == "ISP Provider"
        assert result["memo"] == "Internet Bill"
        assert result["flag_color"] == "blue"

        # Verify the API call was made with correct data
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        assert "scheduled_transaction" in call_args.kwargs["json"]
        txn_data = call_args.kwargs["json"]["scheduled_transaction"]
        assert txn_data["amount"] == -50000  # Converted to milliunits
        assert txn_data["frequency"] == "monthly"


@pytest.mark.asyncio
async def test_delete_scheduled_transaction(client):
    """Test delete_scheduled_transaction sends correct request."""
    # Mock successful deletion response
    deleted_txn = {
        "id": "sched-123",
        "deleted": True,
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"scheduled_transaction": deleted_txn}}

        result = await client.delete_scheduled_transaction("budget-123", "sched-123")

        assert result["deleted"]
        assert result["scheduled_transaction"]["id"] == "sched-123"

        # Verify DELETE request was made to correct URL
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        assert "sched-123" in call_args.args[1]


@pytest.mark.asyncio
async def test_get_transaction(client):
    """Test get_transaction returns formatted transaction with subtransactions."""
    # Mock transaction response with subtransactions
    txn_data = {
        "id": "txn-123",
        "date": "2025-10-06",
        "amount": -80000,  # -$80 in milliunits
        "memo": "Shopping",
        "cleared": "cleared",
        "approved": True,
        "account_id": "account-123",
        "account_name": "Checking",
        "payee_id": "payee-1",
        "payee_name": "Target",
        "category_id": None,  # Null for split transactions
        "category_name": None,
        "transfer_account_id": None,
        "subtransactions": [
            {
                "id": "sub-1",
                "amount": -50000,
                "memo": "Groceries",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-123",
                "category_name": "Food",
            },
            {
                "id": "sub-2",
                "amount": -30000,
                "memo": "Household",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-456",
                "category_name": "Household Items",
            },
        ],
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transaction": txn_data}}

        result = await client.get_transaction("budget-123", "txn-123")

        # Check main transaction details
        assert result["id"] == "txn-123"
        assert result["date"] == "2025-10-06"
        assert result["amount"] == -80.0  # Converted from milliunits
        assert result["memo"] == "Shopping"
        assert result["payee_name"] == "Target"
        assert result["category_id"] is None  # Split transactions have null category_id

        # Check subtransactions
        assert result["subtransactions"] is not None
        assert len(result["subtransactions"]) == 2

        # Check first subtransaction
        assert result["subtransactions"][0]["id"] == "sub-1"
        assert result["subtransactions"][0]["amount"] == -50.0
        assert result["subtransactions"][0]["memo"] == "Groceries"
        assert result["subtransactions"][0]["category_name"] == "Food"

        # Check second subtransaction
        assert result["subtransactions"][1]["id"] == "sub-2"
        assert result["subtransactions"][1]["amount"] == -30.0
        assert result["subtransactions"][1]["memo"] == "Household"
        assert result["subtransactions"][1]["category_name"] == "Household Items"

        # Verify the API call was made to correct URL
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        assert "txn-123" in call_args.args[1]


@pytest.mark.asyncio
async def test_get_transaction_without_subtransactions(client):
    """Test get_transaction for regular transactions without splits."""
    # Mock regular transaction response (no subtransactions)
    txn_data = {
        "id": "txn-456",
        "date": "2025-10-05",
        "amount": -25000,
        "memo": "Coffee",
        "cleared": "uncleared",
        "approved": False,
        "account_id": "account-123",
        "account_name": "Checking",
        "payee_id": "payee-2",
        "payee_name": "Cafe",
        "category_id": "cat-789",
        "category_name": "Dining Out",
        "transfer_account_id": None,
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transaction": txn_data}}

        result = await client.get_transaction("budget-123", "txn-456")

        # Check transaction details
        assert result["id"] == "txn-456"
        assert result["amount"] == -25.0
        assert result["category_name"] == "Dining Out"
        assert result["subtransactions"] is None  # No subtransactions for regular transactions


@pytest.mark.asyncio
async def test_create_split_transaction(client):
    """Test create_split_transaction sends correct data and handles response."""
    # Mock successful creation response
    created_txn = {
        "id": "txn-new",
        "date": "2025-10-06",
        "amount": -80000,
        "memo": "Shopping",
        "cleared": "uncleared",
        "approved": False,
        "account_id": "account-123",
        "account_name": "Checking",
        "payee_id": None,
        "payee_name": "Target",
        "category_id": None,  # Null for split transactions
        "category_name": None,
        "subtransactions": [
            {
                "id": "sub-1",
                "amount": -50000,
                "memo": "Food",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-123",
                "category_name": "Groceries",
            },
            {
                "id": "sub-2",
                "amount": -30000,
                "memo": "Supplies",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-456",
                "category_name": "Household",
            },
        ],
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"transaction": created_txn}}

        subtransactions = [
            {"amount": -50.0, "category_id": "cat-123", "memo": "Food"},
            {"amount": -30.0, "category_id": "cat-456", "memo": "Supplies"},
        ]

        result = await client.create_split_transaction(
            budget_id="budget-123",
            account_id="account-123",
            date="2025-10-06",
            amount=-80.0,
            subtransactions=subtransactions,
            payee_name="Target",
            memo="Shopping",
            cleared="uncleared",
            approved=False,
        )

        # Check main transaction
        assert result["id"] == "txn-new"
        assert result["amount"] == -80.0
        assert result["payee_name"] == "Target"
        assert result["category_id"] is None

        # Check subtransactions
        assert len(result["subtransactions"]) == 2
        assert result["subtransactions"][0]["amount"] == -50.0
        assert result["subtransactions"][0]["category_name"] == "Groceries"
        assert result["subtransactions"][1]["amount"] == -30.0
        assert result["subtransactions"][1]["category_name"] == "Household"

        # Verify the API call was made with correct data
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        assert "transaction" in call_args.kwargs["json"]
        txn_data = call_args.kwargs["json"]["transaction"]
        assert txn_data["amount"] == -80000  # Converted to milliunits
        assert txn_data["category_id"] is None  # Must be null for split transactions
        assert len(txn_data["subtransactions"]) == 2
        assert txn_data["subtransactions"][0]["amount"] == -50000
        assert txn_data["subtransactions"][1]["amount"] == -30000


@pytest.mark.asyncio
async def test_prepare_split_for_matching(client):
    """Test prepare_split_for_matching fetches original and creates split."""
    # Mock original transaction
    original_txn = {
        "id": "txn-original",
        "date": "2025-10-06",
        "amount": -80000,
        "memo": "Shopping",
        "cleared": "cleared",
        "approved": True,
        "account_id": "account-123",
        "account_name": "Checking",
        "payee_id": "payee-1",
        "payee_name": "Target",
        "category_id": "cat-999",
        "category_name": "Uncategorized",
        "transfer_account_id": None,
        "subtransactions": None,
    }

    # Mock created split transaction
    created_split = {
        "id": "txn-split",
        "date": "2025-10-06",
        "amount": -80000,
        "memo": "Shopping",
        "cleared": "cleared",
        "approved": False,  # Created as unapproved
        "account_id": "account-123",
        "account_name": "Checking",
        "payee_id": None,
        "payee_name": "Target",
        "category_id": None,
        "category_name": None,
        "subtransactions": [
            {
                "id": "sub-1",
                "amount": -50000,
                "memo": "Food",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-123",
                "category_name": "Groceries",
            },
            {
                "id": "sub-2",
                "amount": -30000,
                "memo": "Supplies",
                "payee_id": None,
                "payee_name": "Target",
                "category_id": "cat-456",
                "category_name": "Household",
            },
        ],
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API responses: first call for get_transaction, second for create_split_transaction
        mock_retry.side_effect = [
            {"data": {"transaction": original_txn}},
            {"data": {"transaction": created_split}},
        ]

        subtransactions = [
            {"amount": -50.0, "category_id": "cat-123", "memo": "Food"},
            {"amount": -30.0, "category_id": "cat-456", "memo": "Supplies"},
        ]

        result = await client.prepare_split_for_matching(
            budget_id="budget-123", transaction_id="txn-original", subtransactions=subtransactions
        )

        # Check original transaction info
        assert result["original_transaction"]["id"] == "txn-original"
        assert result["original_transaction"]["amount"] == -80.0
        assert result["original_transaction"]["payee_name"] == "Target"

        # Check new split transaction
        assert result["new_split_transaction"]["id"] == "txn-split"
        assert result["new_split_transaction"]["approved"] is False  # Unapproved for matching
        assert result["new_split_transaction"]["amount"] == -80.0
        assert len(result["new_split_transaction"]["subtransactions"]) == 2

        # Check instructions are provided
        assert "instructions" in result
        assert "match" in result["instructions"].lower()

        # Verify two API calls were made (get + create)
        assert mock_retry.call_count == 2


@pytest.mark.asyncio
async def test_start_reconciliation(client):
    """Test start_reconciliation returns account data for reconciliation."""
    # Mock account response
    account_data = {
        "id": "account-123",
        "name": "Checking Account",
        "balance": 1500000,  # $1,500.00 in milliunits
        "cleared_balance": 1245670,  # $1,245.67 in milliunits
        "uncleared_balance": 254330,  # $254.33 in milliunits
    }

    # Mock transactions response
    transactions = [
        # Cleared transactions
        {"id": "txn-1", "date": "2025-10-01", "amount": -10000, "cleared": "cleared", "deleted": False},
        {"id": "txn-2", "date": "2025-10-02", "amount": -15000, "cleared": "cleared", "deleted": False},
        {"id": "txn-3", "date": "2025-10-03", "amount": -20000, "cleared": "cleared", "deleted": False},
        # Uncleared transactions
        {"id": "txn-4", "date": "2025-10-04", "amount": -5000, "cleared": "uncleared", "deleted": False},
        {"id": "txn-5", "date": "2025-10-05", "amount": -3000, "cleared": "uncleared", "deleted": False},
        # Already reconciled (should be skipped)
        {"id": "txn-6", "date": "2025-09-30", "amount": -50000, "cleared": "reconciled", "deleted": False},
        # Deleted transaction (should be skipped)
        {"id": "txn-7", "date": "2025-10-06", "amount": -10000, "cleared": "cleared", "deleted": True},
    ]

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API responses: first call for account, second for transactions
        mock_retry.side_effect = [
            {"data": {"account": account_data}},
            {"data": {"transactions": transactions}},
        ]

        result = await client.start_reconciliation("budget-123", "account-123")

        # Check account info
        assert result["account_id"] == "account-123"
        assert result["account_name"] == "Checking Account"
        assert result["cleared_balance"] == 1245.67
        assert result["uncleared_balance"] == 254.33
        assert result["total_balance"] == 1500.0

        # Check transaction counts
        assert result["cleared_transaction_count"] == 3
        assert result["uncleared_transaction_count"] == 2

        # Check cleared transaction IDs
        assert len(result["cleared_transaction_ids"]) == 3
        assert "txn-1" in result["cleared_transaction_ids"]
        assert "txn-2" in result["cleared_transaction_ids"]
        assert "txn-3" in result["cleared_transaction_ids"]
        # Reconciled and deleted should not be in the list
        assert "txn-6" not in result["cleared_transaction_ids"]
        assert "txn-7" not in result["cleared_transaction_ids"]

        # Verify two API calls were made
        assert mock_retry.call_count == 2


@pytest.mark.asyncio
async def test_complete_reconciliation_matches(client):
    """Test complete_reconciliation when balances match."""
    # Mock successful reconciliation
    reconciled_txn = {
        "id": "txn-1",
        "date": "2025-10-01",
        "amount": -10000,
        "cleared": "reconciled",
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API responses for each transaction update
        mock_retry.return_value = {"data": {"transaction": reconciled_txn}}

        cleared_ids = ["txn-1", "txn-2", "txn-3"]
        result = await client.complete_reconciliation(
            budget_id="budget-123",
            account_id="account-123",
            cleared_transaction_ids=cleared_ids,
            matches=True,
        )

        # Check result
        assert result["status"] == "completed"
        assert result["reconciled_count"] == 3
        assert "Successfully reconciled" in result["message"]

        # Verify three API calls were made (one for each transaction)
        assert mock_retry.call_count == 3


@pytest.mark.asyncio
async def test_complete_reconciliation_discrepancy_no_adjustment(client):
    """Test complete_reconciliation when balances don't match, no adjustment."""
    # Mock account response with cleared balance
    account_data = {
        "id": "account-123",
        "name": "Checking Account",
        "cleared_balance": 1245670,  # $1,245.67 in milliunits
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API response
        mock_retry.return_value = {"data": {"account": account_data}}

        result = await client.complete_reconciliation(
            budget_id="budget-123",
            account_id="account-123",
            cleared_transaction_ids=["txn-1", "txn-2"],
            matches=False,
            bank_balance=1250.00,
            create_adjustment=False,
        )

        # Check result
        assert result["status"] == "discrepancy_found"
        assert result["ynab_cleared_balance"] == 1245.67
        assert result["bank_balance"] == 1250.00
        assert result["difference"] == pytest.approx(4.33, rel=0.01)
        assert result["adjustment_created"] is False

        # Verify only one API call was made (to get account balance)
        assert mock_retry.call_count == 1


@pytest.mark.asyncio
async def test_complete_reconciliation_discrepancy_with_adjustment(client):
    """Test complete_reconciliation when balances don't match, with adjustment."""
    # Mock account response
    account_data = {
        "id": "account-123",
        "name": "Checking Account",
        "cleared_balance": 1245670,  # $1,245.67 in milliunits
    }

    # Mock created adjustment transaction
    adjustment_txn = {
        "id": "txn-adjustment",
        "date": "2025-10-15",
        "amount": 4330,  # $4.33 in milliunits
        "payee_name": "Reconciliation Adjustment",
        "memo": "Adjustment to match bank balance of 1250.0",
        "cleared": "cleared",
        "approved": True,
    }

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock API responses: first for account, second for creating adjustment
        mock_retry.side_effect = [
            {"data": {"account": account_data}},
            {"data": {"transaction": adjustment_txn}},
        ]

        result = await client.complete_reconciliation(
            budget_id="budget-123",
            account_id="account-123",
            cleared_transaction_ids=["txn-1", "txn-2"],
            matches=False,
            bank_balance=1250.00,
            create_adjustment=True,
        )

        # Check result
        assert result["status"] == "completed_with_adjustment"
        assert result["ynab_cleared_balance"] == 1245.67
        assert result["bank_balance"] == 1250.00
        assert result["difference"] == pytest.approx(4.33, rel=0.01)
        assert result["adjustment_created"] is True
        assert result["adjustment_transaction"]["id"] == "txn-adjustment"
        assert result["adjustment_transaction"]["amount"] == 4.33
        assert "Created adjustment transaction" in result["message"]

        # Verify two API calls were made (get account + create transaction)
        assert mock_retry.call_count == 2


@pytest.mark.asyncio
async def test_complete_reconciliation_requires_bank_balance_when_no_match(client):
    """Test complete_reconciliation raises error if bank_balance not provided when matches=False."""
    with pytest.raises(Exception, match="bank_balance is required"):
        await client.complete_reconciliation(
            budget_id="budget-123",
            account_id="account-123",
            cleared_transaction_ids=["txn-1"],
            matches=False,
            bank_balance=None,  # Missing required parameter
        )


@pytest.mark.asyncio
async def test_complete_reconciliation_handles_failed_transactions(client):
    """Test complete_reconciliation handles some transactions failing to reconcile."""

    with patch.object(client, "_make_request_with_retry", new_callable=AsyncMock) as mock_retry:
        # Mock: first transaction succeeds, second fails, third succeeds
        mock_retry.side_effect = [
            {"data": {"transaction": {"id": "txn-1", "cleared": "reconciled"}}},
            Exception("API Error"),
            {"data": {"transaction": {"id": "txn-3", "cleared": "reconciled"}}},
        ]

        cleared_ids = ["txn-1", "txn-2", "txn-3"]
        result = await client.complete_reconciliation(
            budget_id="budget-123",
            account_id="account-123",
            cleared_transaction_ids=cleared_ids,
            matches=True,
        )

        # Check result - should have reconciled 2 out of 3
        assert result["status"] == "completed"
        assert result["reconciled_count"] == 2

        # Verify three API calls were attempted
        assert mock_retry.call_count == 3
