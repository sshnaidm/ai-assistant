"""Shared utilities for parsing inputs and common helpers across MCP tools."""

import ast
import json


def parse_input(input_str: str) -> dict:
    """
    Parse the input string into a dictionary.
    Handles JSON strings or literal Python dict syntax safely.
    """
    if not isinstance(input_str, str):
        if isinstance(input_str, dict):
            return input_str
        return {}
    input_str = input_str.strip()
    if not input_str:
        return {}
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(
                input_str.replace("null", "None").replace("true", "True").replace("false", "False")
            )
        except Exception:
            return {}
