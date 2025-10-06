"""YNAB MCP Server - MCP server for YNAB integration."""

from __future__ import annotations

from .ynab_client import YNABClient
from .server import main
from .exceptions import (
    YNABError,
    YNABAPIError,
    YNABValidationError,
    YNABRateLimitError,
    YNABConnectionError,
)

__version__ = "0.1.0"
__all__ = [
    "YNABClient",
    "main",
    "YNABError",
    "YNABAPIError",
    "YNABValidationError",
    "YNABRateLimitError",
    "YNABConnectionError",
]
