#!/usr/bin/env python3
"""This module provides a Gradio chat interface for an AI email assistant."""
import datetime

try:
    from logging_config import setup_logging

    logger = setup_logging(__name__)
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

import gradio as gr
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.prompts import PromptTemplate

import additional_mcp
import mcp_calendar
import mcp_gmail

# pylint: disable=unused-import
from models import gemini, init_llm, ollama, openai

logger.info("assistant module initialized")


# flake8: noqa: F401
llm = init_llm()  # gemini  # ollama or gemini, or any other model you want to use

print("LLM initialized in Agent Executor:", llm)

AI_SYSTEM_PROMPT = """
You are helpful AI assistant that helps with managing mails, docs, calendar, and other tasks.
You are able to use tools to answer questions and perform actions.
When you are asked to perform an action, you should use the appropriate tool to perform the action.
# Custom rules:
When you are asked to plan a day, you should create events (kind of tasks) for the owner in their calendar for today
or requested date. Estimate the duration of the tasks based on the description and context, create events with the
appropriate duration. For example is the task is about "Create a new report", the duration might be 1 hour. In this
case create an event with the duration of 1 hour and appropriate description in reasonable working hours.
If the task is about "Buy groceries", the duration might be 1 hour. In this case create an event with the duration
of 1 hour and appropriate description in reasonable non-working hours.
If user asks just to show the plan for today or requested date, you should NOT create events, you should only show the
events that are already created in the calendar and other actions from context.

# IMPORTANT: When you cannot find what the user requested, you must use the "Ask User" tool to:
1. Explain what you found (or didn't find)
2. Ask for clarification or next steps

Never end your response without taking an action.

Example when no slots are found:
Thought: I found no available slots in the requested time range. I should inform the user and ask for alternatives.
Action: Ask User
Action Input: "I couldn't find any available 20-minute slots between 10:00-17:00 tomorrow for both you and
someone@example.com. The earliest available slots are between 07:00-09:20. Would you like me to:
1) Search for slots at different times, 2) Look on a different day, or 3) Book one of the morning slots?"
Observation: [User will provide their preference]

Example when you need more information:
Thought: The user wants to schedule a meeting but didn't specify the duration.
Action: Ask User
Action Input: "How long should the meeting be? Common durations are 30 minutes, 1 hour, or 90 minutes."
Observation: [User will provide duration]

Always use the "Ask User" tool when you need to communicate findings and get direction from the user.

# Tools:
You have access to the following tools:
1. **get_emails_tool**: Search for emails in Gmail.
    Input: {}
    Output: The list of available tools.
2. **send_email_tool**: Send an email.
    Input: {"query": "in:inbox subject:meeting"}
    Input: {"query": "from:user in:inbox", count: 50, page: 1, full_body: True}
    Input: {"query": "to:me", count: 50}
    Output: The list of emails matching the query with snippets or full text.
3. **get_today_date**: Get today's date in YYYY-MM-DD format.
    Input: {}
    Output: The current date in YYYY-MM-DD format.
4. **get_calendar_events**: Get calendar events.
    Input: {"query": "in:inbox subject:meeting"}
    Output: The list of calendar events matching the query.
5. **create_calendar_event**: Create a calendar event in the calendar.
    Input: {
        "event": "event_name", 
        "description": "event_description", 
        "start": "2025-09-09T10:00:00", 
        "end": "2025-09-09T11:00:00",
        "calendar_id": "calendar_id"
    }
    Output: The created calendar event.
6. **update_calendar_event**: Update a calendar event in the calendar.
    Input: {
        "event": "event_name", 
        "description": "event_description", 
        "start": "2025-09-09T10:00:00", 
        "end": "2025-09-09T11:00:00",
        "calendar_id": "calendar_id"
    }
    Output: The updated calendar event.
7. **delete_calendar_event**: Delete a calendar event.
    Input: {"event": "event_name"}
    Output: The deleted calendar event.
8. **find_meeting_slots**: Find meeting slots for the attendees.
    Input: {
        "attendees": ["attendee1@e.com", "attendee2@e.com"], 
        "duration_minutes": 30,
        "date_start": "2025-09-09",
        "date_end": "2025-09-11",
        "preferred_time_start": "09:00",
        "preferred_time_end": "17:00",
        "earliest_hour": 7,
        "latest_hour": 20,
        "max_suggestions": 10
    }
    Output: The list of meeting slots.
9. **get_free_busy**: Get free/busy information for the calendars.
    Input: {
        "time_min": "2025-09-09T10:00:00", 
        "time_max": "2025-09-09T20:00:00",
        "calendars": ["calendar_id1", "calendar_id2"], 
        "timezone": "UTC"
        }
    Output: The free/busy information.
10. **ask_user**: Ask the user a question when you need clarification or additional information.
    Input: Your question as a string.
    Output: The question for the user.

"""

# Access the underlying functions from the FunctionTool objects
# The @mcp.tool decorator wraps functions in FunctionTool objects
# We need to access the actual function using the .fn attribute
tools = [
    Tool(
        name="list_gmail_tools", func=mcp_gmail.list_gmail_tools.fn, description=mcp_gmail.list_gmail_tools.description
    ),
    Tool(
        name="list_calendar_tools",
        func=mcp_calendar.list_calendar_tools.fn,
        description=mcp_calendar.list_calendar_tools.description,
    ),
    Tool(name="get_emails_tool", func=mcp_gmail.get_emails_tool.fn, description=mcp_gmail.get_emails_tool.description),
    Tool(name="send_email_tool", func=mcp_gmail.send_email_tool.fn, description=mcp_gmail.send_email_tool.description),
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
    Tool(
        name="ask_user",
        func=additional_mcp.ask_user_tool.fn,
        description=additional_mcp.ask_user_tool.description,
        return_direct=True,
    ),
]

# Use ReAct agent instead of OpenAI functions agent
# prompt = hub.pull("hwchase17/react")

prompt = PromptTemplate.from_template(
    """
You are a helpful email assistant that can search Gmail, manage calendar events, and provide summaries.

You have access to the following tools:
{tools}

Tool names: {tool_names}

Previous conversation history:
{chat_history}

When answering questions, follow this format EXACTLY:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

IMPORTANT RULES:
1. Always follow the Thought/Action/Action Input/Observation format until you have a complete answer.

2. When you have a complete answer, end with:
   Thought: I now know the final answer
   Final Answer: [your complete response]

3. CONTEXT AWARENESS: Always consider the conversation history to understand:
   - What task is in progress
   - What the user is trying to accomplish
   - Whether the current input is a continuation or refinement of a previous request

4. BE PROACTIVE: When the user provides new information or constraints:
   - Take appropriate actions to help complete their goal
   - Don't just explain what you found - continue working toward the solution
   - Use reasonable defaults when information is missing (and mention what defaults you used)

5. ONLY provide a Final Answer when:
   - The task is complete
   - You need critical information that prevents any progress
   - The user explicitly asks for information without requesting an action

6. If you need clarification from the user, use the ask_user tool.
   Do not produce a Final Answer in that case; take Action: ask_user with your question.

Remember the context from our previous conversation when answering.

Question: {input}
{agent_scratchpad}
"""
)

# Create the ReAct agent (compatible with Gemini)
agent = create_react_agent(llm, tools, prompt)

# agent = create_openai_functions_agent(llm, tools, prompt)
# Create the Agent Executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=6,  # Allow a couple more steps when clarifying
    max_execution_time=180,  # Limit execution time to 180 seconds
    # early_stopping_method="generate",  # Changed to "generate" for better final answer handling
    early_stopping_method="force",
    return_intermediate_steps=True,  # This helps with debugging
)


def chat(message, history):
    """
    Chat function for the agent executor.
    Args:
        message (str): The message to send to the agent.
        history (list): The history of the conversation.
    Returns:
        str: The response from the agent.
    """
    try:
        start = datetime.datetime.now()
        print(f"DEBUG: Starting calculation at {start}")
        print(f"DEBUG: Received history with {len(history) if history else 0} messages")

        # Convert gradio history to a formatted string for the prompt
        chat_history_str = ""
        if history:
            for h in history:
                if h["role"] == "user":
                    chat_history_str += f"Human: {h['content']}\n"
                elif h["role"] == "assistant":
                    chat_history_str += f"Assistant: {h['content']}\n"
            chat_history_str = chat_history_str.strip()
            print(f"DEBUG: Formatted chat history:\n{chat_history_str[:200]}...")  # Show first 200 chars
        else:
            chat_history_str = "No previous conversation."
            print("DEBUG: No previous conversation history")

        # Prepare input for the agent
        agent_input = {"input": message, "chat_history": chat_history_str}
        print(f"DEBUG: Agent input prepared with message: {message[:100]}...")

        # Get the response directly
        response = agent_executor.invoke(agent_input)

        # Extract the final output
        if isinstance(response, dict) and "output" in response:
            final_answer = response["output"]
        else:
            final_answer = str(response)
        print(f"DEBUG: Response: {response}")
        end = datetime.datetime.now()
        total = round((end - start).total_seconds(), 2)
        yield final_answer + f"\n\nTotal time: {total} seconds"

    except (ValueError, TypeError) as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"DEBUG: Exception occurred: {e}")
        yield error_msg


with gr.Blocks() as demo:

    gr.ChatInterface(
        chat,
        type="messages",
        save_history=True,
    )

demo.launch(server_port=5000)
