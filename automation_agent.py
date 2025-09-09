#!/usr/bin/env python3
"""Non-interactive, one-shot agent runner.

Builds a minimal ReAct agent profile (no ask_user), enforces literal JSON tool inputs,
uses safe defaults, runs once with the provided prompt, prints the result, and exits.
"""

import argparse
import os
import sys

try:
    from logging_config import setup_logging

    logger = setup_logging(__name__)
except ImportError:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.prompts import PromptTemplate

import mcp_calendar
import mcp_gmail

# pylint: disable=unused-import
from models import gemini, init_llm, ollama, openai  # noqa: F401

llm = init_llm()  # or switch to ollama or openai if desired


def build_tools_non_interactive():
    """Return the tool list excluding any interactive tools (e.g., ask_user)."""
    return [
        Tool(
            name="get_emails_tool", func=mcp_gmail.get_emails_tool.fn, description=mcp_gmail.get_emails_tool.description
        ),
        Tool(
            name="send_email_tool", func=mcp_gmail.send_email_tool.fn, description=mcp_gmail.send_email_tool.description
        ),
        Tool(name="get_today_date", func=mcp_gmail.get_today_date.fn, description=mcp_gmail.get_today_date.description),
        Tool(
            name="get_calendar_events",
            func=mcp_calendar.get_events_tool.fn,
            description=mcp_calendar.get_events_tool.description,
        ),
        Tool(
            name="create_calendar_event",
            func=mcp_calendar.create_event_tool.fn,
            description=mcp_calendar.create_event_tool.description,
        ),
        Tool(
            name="update_calendar_event",
            func=mcp_calendar.update_event_tool.fn,
            description=mcp_calendar.update_event_tool.description,
        ),
        Tool(
            name="delete_calendar_event",
            func=mcp_calendar.delete_event_tool.fn,
            description=mcp_calendar.delete_event_tool.description,
        ),
        Tool(
            name="find_meeting_slots",
            func=mcp_calendar.find_meeting_slots_tool.fn,
            description=mcp_calendar.find_meeting_slots_tool.description,
        ),
        Tool(
            name="get_free_busy",
            func=mcp_calendar.get_free_busy_tool.fn,
            description=mcp_calendar.get_free_busy_tool.description,
        ),
    ]


AUTOMATION_PROMPT = PromptTemplate.from_template(
    """
You are an automation agent that must complete the task in a non-interactive run.

You have access to the following tools:
{tools}

Tool names: {tool_names}

When answering, follow this exact format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

NON-INTERACTIVE RULES:
1) Do NOT ask the user anything and do NOT attempt to call interactive tools.
2) Tool inputs MUST be literal JSON with concrete values only. Never include code, expressions,
   or dynamic concatenation (no datetime.now(), no timedelta(), no "+", no f-strings).
3) If you need dates (e.g., yesterday), call get_today_date first, then compute the target date internally
   and send a literal final string in Action Input.
4) Use safe defaults when information is missing:
   - Email sending: prefer draft_mode=true unless the user explicitly asks to send.
   - Meeting duration: default 30 minutes.
5) Keep steps minimal. If you cannot proceed due to missing critical info, provide a Final Answer
   explaining what is missing.

Question: {input}
{agent_scratchpad}
"""
)


def run_once(prompt_text: str, max_iterations: int = 10, timeout_seconds: int = 180, verbose: bool = True) -> int:
    """Run the agent once with the given prompt and return exit code."""
    tools = build_tools_non_interactive()

    agent = create_react_agent(llm, tools, AUTOMATION_PROMPT)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=max_iterations,
        max_execution_time=timeout_seconds,
        early_stopping_method="force",
        return_intermediate_steps=False,
    )

    try:
        logger.info("Running non-interactive agent once...")
        result = agent_executor.invoke({"input": prompt_text, "chat_history": ""})
        if isinstance(result, dict) and "output" in result:
            print(result["output"])  # noqa: T201
        else:
            print(str(result))  # noqa: T201
        return 0
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(f"Agent run failed: {exc}", exc_info=True)
        print(f"ERROR: {exc}")  # noqa: T201
        return 1


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Run the non-interactive automation agent once and exit")
    parser.add_argument("--prompt", required=True, help="The prompt to execute")
    parser.add_argument("--max-iterations", type=int, default=int(os.getenv("AGENT_MAX_ITER", "4")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("AGENT_TIMEOUT", "180")))
    parser.add_argument("--quiet", action="store_true", help="Reduce agent verbosity")
    args = parser.parse_args()

    exit_code = run_once(
        prompt_text=args.prompt,
        max_iterations=int(args.max_iterations),
        timeout_seconds=int(args.timeout),
        verbose=not args.quiet,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
