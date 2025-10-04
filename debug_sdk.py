"""Debug script to understand ynab_sdk response format."""

import os
from dotenv import load_dotenv
from ynab_sdk import YNAB

load_dotenv()

client = YNAB(os.getenv("YNAB_ACCESS_TOKEN"))
response = client.budgets.get_budgets()

print("Response type:", type(response))
print("Response:", response)
print("\nResponse attributes:", dir(response))
