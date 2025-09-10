#!/usr/bin/env python3
"""Expose ADK agent(s) for discovery by `adk web` and `adk run`.

This module re-exports the agent from `my_adk.py` under the conventional names
expected by ADK web:
- root_agent: single primary agent
- agents: optional list of agents
"""

from adk_assistant.adk_assistant_agent import _build_adk_agent as _build  # type: ignore

# Initialize once at import so discovery works without additional setup
root_agent = _build()
agent = root_agent
agents = [root_agent]
