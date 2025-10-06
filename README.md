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

### Health & Diagnostics
- `health_check` - Check server health and YNAB API connectivity

### Account Management
- `get_accounts` - Get all accounts for a budget

### Category & Budget Management
- `get_category` - Get a single category with full details including goal information
- `get_categories` - Get all categories for a budget (lightweight list)
- `get_budget_summary` - Get budget summary for a specific month
- `update_category` - Update category properties (name, note, group, or goal target)
- `update_category_budget` - Update the budgeted amount for a category in a specific month
- `move_category_funds` - Move funds from one category to another

### Transaction Management
- `get_transactions` - Get transactions with pagination and filtering (date range, account, category, limit, page)
- `search_transactions` - Search transactions by text in payee name or memo
- `create_transaction` - Create a new transaction
- `update_transaction` - Update an existing transaction
- `get_unapproved_transactions` - Get all unapproved transactions that need review

### Scheduled Transactions
- `get_scheduled_transactions` - List all scheduled transactions
- `create_scheduled_transaction` - Create future/recurring transactions
- `delete_scheduled_transaction` - Delete scheduled transactions

### Analytics & Reporting
- `get_category_spending_summary` - Get spending summary with optional terminal graph visualization
- `compare_spending_by_year` - Year-over-year spending comparison with optional graph

## Features

### Robust Error Handling
- Custom exception classes for different error types
- Automatic retry logic with exponential backoff
- Rate limit detection and handling (respects Retry-After headers)
- Comprehensive logging (configurable via `LOG_LEVEL` environment variable)

### Performance & Reliability
- HTTP connection pooling for better performance
- Input validation on all parameters
- Timeout configuration (30s default)
- Milliunits conversion handled automatically

### Analytics & Visualization
- Server-side spending aggregation to reduce context usage
- Optional terminal-based graph visualization using termgraph
- Year-over-year spending comparisons
- Monthly spending summaries

## Configuration

### Environment Variables
- `YNAB_ACCESS_TOKEN` (required) - Your YNAB Personal Access Token
- `LOG_LEVEL` (optional) - Logging level (DEBUG, INFO, WARNING, ERROR, default: INFO)

## Troubleshooting

### MCP Server Not Connecting
1. Run the health check tool: `health_check`
2. Check that `YNAB_ACCESS_TOKEN` is set in your `.env` file
3. Verify the token is valid at https://app.ynab.com/settings/developer
4. Check logs with `LOG_LEVEL=DEBUG`

### Rate Limit Errors
The YNAB API has a rate limit of 200 requests per hour. The server automatically:
- Detects 429 (rate limit) responses
- Retries with exponential backoff
- Respects `Retry-After` headers

If you consistently hit rate limits, consider:
- Using analytics tools (`get_category_spending_summary`, `compare_spending_by_year`) instead of fetching all transactions
- Reducing the frequency of requests
- Caching results when possible

### Large Response Sizes
For queries spanning long time periods, use:
- `get_category_spending_summary` - Returns aggregated summary instead of all transactions
- `compare_spending_by_year` - Returns year-over-year totals instead of individual transactions
- Pagination with `get_transactions` (use `limit` and `page` parameters)

## Development

### Running Tests

Install dev dependencies:
```bash
uv sync --extra dev
```

Run tests:
```bash
uv run pytest tests/ -v
```

### Code Quality

The codebase includes:
- Input validation on all parameters
- Custom exception classes for proper error handling
- Comprehensive logging
- Type hints with `from __future__ import annotations`
- Connection pooling for HTTP requests
- Automatic retry logic for transient failures
