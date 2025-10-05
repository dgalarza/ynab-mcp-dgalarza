# YNAB MCP Server

MCP server for YNAB (You Need A Budget) integration, enabling AI assistants to help manage your budget.

## Setup

1. Install dependencies with `uv`:
```bash
uv sync
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
uv run python -m ynab_mcp
```

## Installing in Claude Code

Add to your Claude Code configuration:

```bash
claude mcp add ynab -- uv --directory /path/to/ynab-mcp run python -m ynab_mcp
```

Or add to `.claude.json` manually in the `mcpServers` section:

```json
{
  "ynab": {
    "type": "stdio",
    "command": "uv",
    "args": ["--directory", "/home/your-user/Code/ynab-mcp", "run", "python", "-m", "ynab_mcp"],
    "env": {}
  }
}
```

## Available Tools

### Category & Budget Management
- `get_categories` - Get all categories for a budget
- `get_budget_summary` - Get budget summary for a specific month
- `update_category_budget` - Update the budgeted amount for a category in a specific month
- `move_category_funds` - Move funds from one category to another

### Transaction Management
- `get_transactions` - Get transactions with optional filtering by date, account, or category
- `create_transaction` - Create a new transaction
- `update_transaction` - Update an existing transaction
- `get_unapproved_transactions` - Get all unapproved transactions that need review

More tools coming soon per the implementation plan in `PLAN.md`!
