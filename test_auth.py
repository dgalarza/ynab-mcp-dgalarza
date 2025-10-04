"""Quick test script to verify YNAB authentication."""

import asyncio
import os
from dotenv import load_dotenv
from src.ynab_mcp.ynab_client import YNABClient

load_dotenv()

async def test_auth():
    """Test YNAB authentication and fetch budgets."""
    try:
        client = YNABClient(os.getenv("YNAB_ACCESS_TOKEN"))
        print("✓ YNAB client initialized successfully")

        budgets = await client.get_budgets()
        print(f"\n✓ Authentication successful!")
        print(f"\nFound {len(budgets)} budget(s):")
        for budget in budgets:
            print(f"  - {budget['name']} (ID: {budget['id']})")

        return True
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_auth())
