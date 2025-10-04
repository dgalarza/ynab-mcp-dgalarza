# YNAB MCP Server Implementation Plan

## Architecture
- **Framework**: FastMCP (Python) for rapid MCP server development
- **YNAB Integration**: Official `ynab` Python SDK (via pip)
- **Authentication**: Personal Access Token stored in environment variable

## MCP Tools to Implement

### 1. Transaction Management Tools
- `get_unapproved_transactions(budget_id, since_date)` - List unapproved transactions with filtering
- `approve_transaction(budget_id, transaction_id)` - Mark single transaction as approved
- `categorize_transaction(budget_id, transaction_id, category_id)` - Update transaction category
- `bulk_categorize_transactions(budget_id, transaction_updates)` - Categorize multiple transactions at once

### 2. Budget Adjustment Tools
- `get_month_budget(budget_id, month)` - Get current month's category budgets
- `update_category_budget(budget_id, month, category_id, budgeted_amount)` - Adjust budget for specific category/month
- `bulk_update_budgets(budget_id, month, category_updates)` - Update multiple categories for a month

### 3. Analysis & Insights Tools
- `analyze_spending_trends(budget_id, category_id, start_date, end_date)` - Historical spending analysis by category
- `get_yearly_spending_summary(budget_id, year, category_id)` - Annual spending totals per category
- `recommend_budget_amounts(budget_id, category_id, analysis_period)` - ML-based budget recommendations using historical averages
- `compare_periods(budget_id, category_id, period1, period2)` - Compare spending between time periods

### 4. Data Retrieval Tools
- `get_categories(budget_id)` - List all categories for budget planning
- `get_budget_summary(budget_id, month)` - Overview of budget vs actual spending

## Implementation Steps
1. Set up FastMCP project structure with dependencies (fastmcp, ynab)
2. Implement YNAB API client wrapper with authentication
3. Build core transaction tools (identify, approve, categorize)
4. Build budget management tools (get, update budgets)
5. Implement analytics engine for historical trend analysis
6. Create recommendation logic using statistical analysis
7. Add comprehensive error handling and rate limit management
8. Test with your actual YNAB data
9. Document tool usage and create example workflows

## Key Technical Details
- Rate limit: 200 requests/hour per access token
- Use delta requests (`last_knowledge_of_server`) for efficient syncing
- Dates in ISO 8601 format (YYYY-MM-DD)
- Currency in "milliunits" (multiply by 1000)
- Filter transactions with `type=unapproved` parameter
- PATCH endpoint for category budget updates: `/budgets/{budget_id}/months/{month}/categories/{category_id}`

## Project Goals
1. Identify unapproved transactions
2. Categorize transactions
3. Adjust budget for the month based on historical data
4. Make recommendations for future budgeting needs
5. Analyze trends (e.g., "In 2024 I spent $X on utilities. Budget $Y per month in 2025.")
