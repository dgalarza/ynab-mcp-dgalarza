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
