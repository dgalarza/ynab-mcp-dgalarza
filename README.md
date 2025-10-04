# YNAB MCP Server

MCP server for YNAB (You Need A Budget) integration, enabling AI assistants to help manage your budget.

## Setup

1. Install dependencies:
```bash
pip install -e .
```

2. Get your YNAB Personal Access Token:
   - Go to https://app.ynab.com/settings/developer
   - Create a new Personal Access Token
   - Copy the token

3. Create `.env` file:
```bash
cp .env.example .env
```

4. Add your token to `.env`:
```
YNAB_ACCESS_TOKEN=your_token_here
```

## Running the Server

```bash
python -m ynab_mcp.server
```

## Available Tools

- `get_categories` - Get all categories for a budget
- `get_budget_summary` - Get budget summary for a specific month

More tools coming soon!
