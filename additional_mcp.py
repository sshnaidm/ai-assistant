"""Additional FastMCP tools (generic utilities), e.g., Ask User."""

import logging
import os
from typing import Any

from fastmcp import FastMCP

# Independent logging for this module
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NUMERIC_LEVEL = getattr(logging, LOG_LEVEL, logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(NUMERIC_LEVEL)
logger.handlers = []

file_handler = logging.FileHandler("additional_mcp.log", mode="a")
file_handler.setLevel(NUMERIC_LEVEL)
file_fmt = logging.Formatter("%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
file_handler.setFormatter(file_fmt)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(NUMERIC_LEVEL)
console_fmt = logging.Formatter("%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
console_handler.setFormatter(console_fmt)
logger.addHandler(console_handler)

logger.propagate = False

logger.info(f"additional_mcp logging configured - Level: {LOG_LEVEL}")


logger.info("Initializing FastMCP server 'additional_tools'")
mcp = FastMCP(
    name="additional_tools",
    instructions=("Utility tools to support interactive workflows (e.g., asking the user for clarification)."),
)


@mcp.tool(
    name="Ask User",
    description=(
        "Ask the user a question when you need clarification or additional information. " "Input: question string."
    ),
)
def ask_user_tool(question: Any) -> str:
    """Ask the user for clarification or additional information."""
    logger.info(f"Asking user: {question}")
    return f"Question: {question}"


if __name__ == "__main__":
    logger.info("Starting additional FastMCP server...")
    mcp.run()
