"""Centralized logging configuration for the MCP Gmail project."""

import logging
import os

# Get log level from environment (single source of truth)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NUMERIC_LEVEL = getattr(logging, LOG_LEVEL, logging.INFO)

# Single log file for the entire project
LOG_FILE = "assistant_agent.log"

# Standard format for all logs
LOG_FORMAT = "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"

# Our application modules
APP_MODULES = ("gmail", "mcp_gmail", "mcp_calendar", "assistant", "logging_config", "__main__")

# Third-party loggers to suppress (only show warnings)
NOISY_LOGGERS = [
    "PIL",
    "asyncio",
    "urllib3",
    "httpcore",
    "httpx",
    "gradio",
    "matplotlib",
    "websockets",
    "starlette",
    "fastapi",
    "uvicorn",
]


# pylint: disable=too-few-public-methods
class ConsoleFilter(logging.Filter):
    """Filter to only show logs from our application modules."""

    def filter(self, record):
        return record.name.startswith(APP_MODULES) or record.name == "root"


def setup_logging(name: str = None) -> logging.Logger:
    """
    Set up logging for a module with consistent configuration.

    Args:
        name: Logger name (usually __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name) if name else logging.getLogger()

    # Skip if already configured
    if logger.handlers:
        return logger

    logger.setLevel(NUMERIC_LEVEL)

    # Single formatter for consistency
    formatter = logging.Formatter(LOG_FORMAT)

    # File handler - captures everything
    file_handler = logging.FileHandler(LOG_FILE, mode="a")
    file_handler.setLevel(NUMERIC_LEVEL)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler - filtered for clean output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(NUMERIC_LEVEL)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(ConsoleFilter())
    logger.addHandler(console_handler)

    # Prevent propagation to avoid duplicates
    logger.propagate = False

    return logger


# Configure root logger once at module import
_root_logger = logging.getLogger()
_root_logger.setLevel(NUMERIC_LEVEL)

# Clear any existing handlers
_root_logger.handlers = []

# Add handlers to root logger
_formatter = logging.Formatter(LOG_FORMAT)

_file_handler = logging.FileHandler(LOG_FILE, mode="a")
_file_handler.setLevel(NUMERIC_LEVEL)
_file_handler.setFormatter(_formatter)
_root_logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(NUMERIC_LEVEL)
_console_handler.setFormatter(_formatter)
_console_handler.addFilter(ConsoleFilter())
_root_logger.addHandler(_console_handler)

# Silence noisy third-party loggers
for _logger_name in NOISY_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)

# Log configuration once
logging.getLogger(__name__).info(f"Logging configured - Level: {LOG_LEVEL}")
