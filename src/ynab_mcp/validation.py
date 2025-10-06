"""Input validation utilities for YNAB MCP."""

from datetime import datetime
from typing import Optional
from .exceptions import YNABValidationError


def validate_date(date_str: str, param_name: str = "date") -> str:
    """Validate and normalize date string in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate
        param_name: Name of the parameter for error messages

    Returns:
        Validated date string

    Raises:
        YNABValidationError: If date format is invalid
    """
    if not date_str:
        raise YNABValidationError(f"{param_name} cannot be empty")

    if not isinstance(date_str, str):
        raise YNABValidationError(f"{param_name} must be a string")

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError as e:
        raise YNABValidationError(
            f"Invalid {param_name} format. Expected YYYY-MM-DD, got '{date_str}'"
        ) from e


def validate_budget_id(budget_id: str) -> str:
    """Validate budget ID.

    Args:
        budget_id: Budget ID to validate

    Returns:
        Validated and stripped budget ID

    Raises:
        YNABValidationError: If budget_id is invalid
    """
    if not budget_id or not isinstance(budget_id, str):
        raise YNABValidationError("budget_id must be a non-empty string")

    budget_id = budget_id.strip()

    if not budget_id:
        raise YNABValidationError("budget_id cannot be empty or whitespace")

    return budget_id


def validate_amount(amount: float, param_name: str = "amount") -> float:
    """Validate amount parameter.

    Args:
        amount: Amount to validate
        param_name: Name of the parameter for error messages

    Returns:
        Validated amount

    Raises:
        YNABValidationError: If amount is invalid
    """
    if not isinstance(amount, (int, float)):
        raise YNABValidationError(f"{param_name} must be a number")

    return float(amount)


def validate_pagination(
    limit: Optional[int] = None,
    page: Optional[int] = None,
    max_limit: int = 500,
    default_limit: int = 100,
) -> tuple[int, int]:
    """Validate and normalize pagination parameters.

    Args:
        limit: Number of items per page
        page: Page number (1-indexed)
        max_limit: Maximum allowed limit
        default_limit: Default limit if not specified

    Returns:
        Tuple of (validated_limit, validated_page)

    Raises:
        YNABValidationError: If pagination parameters are invalid
    """
    # Validate and normalize limit
    if limit is None:
        validated_limit = default_limit
    else:
        if not isinstance(limit, int) or limit <= 0:
            raise YNABValidationError("limit must be a positive integer")
        validated_limit = min(limit, max_limit)

    # Validate and normalize page
    if page is None:
        validated_page = 1
    else:
        if not isinstance(page, int) or page < 1:
            raise YNABValidationError("page must be a positive integer (1-indexed)")
        validated_page = page

    return validated_limit, validated_page


def validate_frequency(frequency: str) -> str:
    """Validate scheduled transaction frequency.

    Args:
        frequency: Frequency string to validate

    Returns:
        Validated frequency string

    Raises:
        YNABValidationError: If frequency is invalid
    """
    valid_frequencies = {
        "never",
        "daily",
        "weekly",
        "everyOtherWeek",
        "twiceAMonth",
        "every4Weeks",
        "monthly",
        "everyOtherMonth",
        "every3Months",
        "every4Months",
        "twiceAYear",
        "yearly",
        "everyOtherYear",
    }

    if not frequency or not isinstance(frequency, str):
        raise YNABValidationError("frequency must be a non-empty string")

    if frequency not in valid_frequencies:
        raise YNABValidationError(
            f"Invalid frequency '{frequency}'. Must be one of: {', '.join(sorted(valid_frequencies))}"
        )

    return frequency


def validate_cleared_status(cleared: str) -> str:
    """Validate transaction cleared status.

    Args:
        cleared: Cleared status to validate

    Returns:
        Validated cleared status

    Raises:
        YNABValidationError: If cleared status is invalid
    """
    valid_statuses = {"cleared", "uncleared", "reconciled"}

    if not cleared or not isinstance(cleared, str):
        raise YNABValidationError("cleared status must be a non-empty string")

    if cleared not in valid_statuses:
        raise YNABValidationError(
            f"Invalid cleared status '{cleared}'. Must be one of: {', '.join(sorted(valid_statuses))}"
        )

    return cleared
