"""Custom exception classes for YNAB MCP."""

from __future__ import annotations


class YNABError(Exception):
    """Base exception for YNAB MCP errors."""

    pass


class YNABAPIError(YNABError):
    """Raised when YNAB API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        """Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code if available
        """
        super().__init__(message)
        self.status_code = status_code


class YNABValidationError(YNABError):
    """Raised when input validation fails."""

    pass


class YNABRateLimitError(YNABAPIError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None):
        """Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Number of seconds to wait before retrying
        """
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class YNABConnectionError(YNABError):
    """Raised when connection to YNAB API fails."""

    pass
