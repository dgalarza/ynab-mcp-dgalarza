"""Tests for YNAB client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
    assert client.access_token == "test_token"
    assert client.api_base_url == "https://api.ynab.com/v1"


def test_client_initialization_fails_without_token():
    """Test client raises error without access token."""
    with pytest.raises(ValueError, match="YNAB_ACCESS_TOKEN environment variable must be set"):
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
    assert result[0]["categories"][0]["hidden"] == True


@pytest.mark.asyncio
async def test_milliunits_conversion():
    """Test milliunits conversion for various amounts."""
    client = YNABClient("test_token")

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock API response with null fields
        mock_response = MagicMock()
        mock_response.json.return_value = {
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
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = await client.search_transactions("budget-123", "groceries")

        # Should find the transaction with "groceries" in memo
        assert result["count"] == 1
        assert result["transactions"][0]["id"] == "txn-2"


@pytest.mark.asyncio
async def test_pagination_calculations(client):
    """Test pagination metadata calculations."""
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock 250 transactions
        transactions = [
            {
                "id": f"txn-{i}",
                "date": "2025-10-01",
                "amount": -1000,
            }
            for i in range(250)
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        # Get page 1 with limit 100
        result = await client.get_transactions("budget-123", limit=100, page=1)

        assert result["pagination"]["page"] == 1
        assert result["pagination"]["per_page"] == 100
        assert result["pagination"]["total_count"] == 250
        assert result["pagination"]["total_pages"] == 3
        assert result["pagination"]["has_next_page"] == True
        assert result["pagination"]["has_prev_page"] == False
        assert len(result["transactions"]) == 100

        # Get page 3 (last page)
        result = await client.get_transactions("budget-123", limit=100, page=3)

        assert result["pagination"]["page"] == 3
        assert result["pagination"]["has_next_page"] == False
        assert result["pagination"]["has_prev_page"] == True
        assert len(result["transactions"]) == 50  # Remaining transactions


@pytest.mark.asyncio
async def test_get_category_spending_summary(client):
    """Test get_category_spending_summary aggregates correctly."""
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = await client.compare_spending_by_year("budget-123", "cat-123", 2023, 3, include_graph=False)

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock transactions with gap year
        transactions = [
            {"id": "txn-1", "date": "2023-03-15", "amount": -10000, "category_id": "cat-123"},
            # 2024 has no transactions
            {"id": "txn-2", "date": "2025-01-20", "amount": -10000, "category_id": "cat-123"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = await client.compare_spending_by_year("budget-123", "cat-123", 2023, 3, include_graph=False)

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock transactions over 2 months
        transactions = [
            {"id": "txn-1", "date": "2025-01-15", "amount": -10000, "category_id": "cat-123"},
            {"id": "txn-2", "date": "2025-02-10", "amount": -20000, "category_id": "cat-123"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock transactions over 2 years
        transactions = [
            {"id": "txn-1", "date": "2023-03-15", "amount": -50000, "category_id": "cat-123"},
            {"id": "txn-2", "date": "2024-02-10", "amount": -75000, "category_id": "cat-123"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"transactions": transactions}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = await client.compare_spending_by_year("budget-123", "cat-123", 2023, 2, include_graph=True)

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock scheduled transactions response
        scheduled_txns = [
            {
                "id": "sched-1",
                "date_first": "2025-11-01",
                "date_next": "2025-11-01",
                "frequency": "monthly",
                "amount": -100000,  # $100 in milliunits
                "memo": "Rent",
                "flag_color": "red",
                "account_id": "account-123",
                "account_name": "Checking",
                "payee_id": "payee-1",
                "payee_name": "Landlord",
                "category_id": "cat-123",
                "category_name": "Rent/Mortgage",
                "deleted": False,
            },
            {
                "id": "sched-2",
                "date_first": "2025-11-15",
                "date_next": "2025-11-15",
                "frequency": "everyOtherWeek",
                "amount": 200000,  # $200 paycheck
                "memo": "Paycheck",
                "flag_color": None,
                "account_id": "account-123",
                "account_name": "Checking",
                "payee_id": "payee-2",
                "payee_name": "Employer",
                "category_id": None,
                "category_name": None,
                "deleted": False,
            }
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"scheduled_transactions": scheduled_txns}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

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
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"scheduled_transaction": created_txn}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.post.return_value = mock_response
        mock_client.return_value = mock_client_instance

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
        mock_client_instance.__aenter__.return_value.post.assert_called_once()
        call_args = mock_client_instance.__aenter__.return_value.post.call_args
        assert "scheduled_transaction" in call_args.kwargs["json"]
        txn_data = call_args.kwargs["json"]["scheduled_transaction"]
        assert txn_data["amount"] == -50000  # Converted to milliunits
        assert txn_data["frequency"] == "monthly"


@pytest.mark.asyncio
async def test_delete_scheduled_transaction(client):
    """Test delete_scheduled_transaction sends correct request."""
    with patch("src.ynab_mcp.ynab_client.httpx.AsyncClient") as mock_client:
        # Mock successful deletion response
        deleted_txn = {
            "id": "sched-123",
            "deleted": True,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"scheduled_transaction": deleted_txn}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.delete.return_value = mock_response
        mock_client.return_value = mock_client_instance

        result = await client.delete_scheduled_transaction("budget-123", "sched-123")

        assert result["deleted"] == True
        assert result["scheduled_transaction"]["id"] == "sched-123"

        # Verify DELETE request was made to correct URL
        mock_client_instance.__aenter__.return_value.delete.assert_called_once()
        call_args = mock_client_instance.__aenter__.return_value.delete.call_args
        assert "scheduled_transactions/sched-123" in call_args.args[0]
