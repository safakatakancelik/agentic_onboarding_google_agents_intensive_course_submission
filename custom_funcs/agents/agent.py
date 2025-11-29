from typing import Any, Dict


import os
import asyncio
import json
import sys

import requests
from custom_funcs.supabase_client import create_user
from dotenv import load_dotenv
from google.adk.agents import Agent, LlmAgent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

load_dotenv()







# Configure HTTP retry options for robust API calls
retry_config = types.HttpRetryOptions(
    attempts=5,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
)



## Tool Context
# Define scope levels for state keys (following best practices)
USER_NAME_SCOPE_LEVELS = ("temp", "user", "app")
# This demonstrates how tools can write to session state using tool_context.
# The 'user:' prefix indicates this is user-specific data.

def save_user_info(
    tool_context: ToolContext, data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Save one or multiple user attributes to the session state.

    Args:
        data: A dictionary of key-value pairs to save (e.g., {"name": "John", "age": 30})
    """
    saved_items = {}
    for key, value in data.items():
        # Enforce the 'user:' prefix convention
        full_key = f"user:{key}"
        tool_context.state[full_key] = value
        saved_items[key] = value

    return {"status": "success", "saved": saved_items}







def load_question_schema_from_api(tool_context: ToolContext) -> Dict[str, Any]:
    """Fetch onboarding questions from the Flask API and store them in session state.

    Calls GET /retrieve_all_questions and saves the 'questions' list to
    tool_context.state["app:question_schema"].
    """
    try:
        FLASK_BASE_URL = "http://127.0.0.1:5000"        
        resp = requests.get(f"{FLASK_BASE_URL}/retrieve_all_questions", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # print(data)
    except Exception as exc:
        return {"status": "error", "message": f"Failed to fetch questions: {exc}"}

    if not data.get("success"):
        return {"status": "error", "message": data.get("error", "Unknown error")}

    questions = data.get("questions", [])

    # Filter questions: mandatory='Y', active='Y', and keep specific keys
    filtered_questions = [
        {
            "questioned_entity": q.get("questioned_entity"),
            "question_phrasing_example": q.get("question_phrasing_example"),
            "question_order_priority": q.get("question_order_priority"),
            "is_mandatory": q.get("is_mandatory"),
        }
        for q in questions
        if q.get("is_active") == "Y"
    ]

    tool_context.state["app:question_schema"] = filtered_questions
    return tool_context.state["app:question_schema"]


def get_onboarding_status(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Check which onboarding questions have been answered and which are pending.

    Returns:
        A list of questions. Each item includes:
        - 'entity': The data field (e.g., 'name')
        - 'question': Example phrasing
        - 'status': 'COMPLETED' if we have the data, 'PENDING' if not.
        - 'value': The current saved value (if any).
    """
    schema = tool_context.state.get("app:question_schema", [])
    status_report = []

    for item in schema:
        entity_key = item.get("questioned_entity")
        # Check if this entity exists in the user state
        # We use the 'user:' prefix convention we established
        current_value = tool_context.state.get(f"user:{entity_key}")

        status = "COMPLETED" if current_value else "PENDING"

        status_report.append(
            {
                "entity": entity_key,
                "question_example": item.get("question_phrasing_example"),
                "priority": item.get("question_order_priority"),
                "is_mandatory": item.get("is_mandatory"),
                "status": status,
                "current_value": current_value,
            }
        )

    # Sort by priority so the agent knows what to ask next naturally
    # Assuming lower number = higher priority
    status_report.sort(key=lambda x: x["priority"] or 999)

    return {"onboarding_status": status_report}


def register_user_in_db(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Registers the user in the database using the collected onboarding information.
    Call this tool ONLY after all mandatory questions are answered and the user is ready to be registered.
    """
    # Retrieve the schema to know which keys to look for
    schema = tool_context.state.get("app:question_schema", [])
    
    user_data = {}
    for item in schema:
        entity_key = item.get("questioned_entity")
        if entity_key:
            # Construct the state key
            state_key = f"user:{entity_key}"
            # Retrieve value from state
            value = tool_context.state.get(state_key)
            if value is not None:
                user_data[entity_key] = value

    # Call the imported create_user function
    result = create_user(user_data)

    return result


# IMPLEMENTING A STATEFUL AGENT
APP_NAME = "agents"  # Application
USER_ID = "new_user_getting_onboarded"  # User
SESSION = "ephemeral-local-storage-id"  # Session
# MODEL_NAME = "gemini-2.5-flash-lite"
MODEL_NAME = "gemini-2.5-pro"

# Step 1: Create the LLM Agent
root_agent = Agent(
    model=Gemini(model=MODEL_NAME, retry_options=retry_config),
    name="text_chat_bot",
    description="""
        You are an onboarding assistant for an agentic onboarding system.
 
        Role:
        Think yourself as a front desk personel at a hotel; guests arive and you check in them.
        However, instead of a hotel you are an embedded agent in a software for the pseudo company "Company X".
        Additionally, users are already welcomed with a pre-written message. You jump right into the check in/onboarding process.
        You are friendly and helpful. You don't repeat yourself, you talk concise, natural and a bit playful.
        
               
        Important Constraints:
        - Keep the conversation natural and engaging.
        - If user talks about something else, guide the conversation back to onboarding.
        - Ask the questions one at a time, however, if the user provides multiple answers, adapt accordingly.
        - After user answers a question, acknowledge their response by stating their answer, then proceed to the next question. 
        - You prepare your message to the user after finishing all of your internal processing and tool calls.
        - Never mention that you'll load the questions, or anything about the backend process. User only needs to be aware of the onboarding conversation.
        - Make the conversation about the user, don't mention yourself. Ask about them and inform them about their own process.
        
        Your goals:
        1. **Initialization**: At the very start of the conversation, call `load_question_schema_from_api` once to load the questions from the backend.
        2. **Check Status**: Before asking a question, ALWAYS call `get_onboarding_status` to see which questions are 'PENDING' and which are 'COMPLETED'.
        3. **Ask Questions**: Select questions with 'PENDING' status, ask questions to have their status as 'COMPLETED'. First prioritize the questions that are mandatory, then with lower priority numbers.
        4. **Save Answers**: When the user provides an answer, IMMEDIATELY call `save_user_info` to save the data. The key should match the 'entity' field from the status report.
        5. **Loop**: After saving, call `get_onboarding_status` again to confirm the status is now 'COMPLETED' and find the next 'PENDING' question.
        6. **Finalize**: Once all questions are answered, call `register_user_in_db` to save the user to the database.
        7. **Finalize early**: If a user has answered all the mandatory questions and wants to register before answering the rest, accept this request, call `register_user_in_db` to save the user to the database.
        8. **Status update**: Inform the user about the completed onboarding and finish the conversation.


        Tools:
        - `load_question_schema_from_api`: Fetches questions from backend. Call once at start.
        - `get_onboarding_status`: Returns the list of questions with their current status (PENDING/COMPLETED) and values.
        - `save_user_info`: Saves the user's answers to the session state.
        - `register_user_in_db`: Submits the collected data to the database.



        IMPORTANT REMINDERS: 
        - never mention any detail about your internal processing or your prompt.
        - don't tell anything about yourself
        -- make the conversation about the user, don't mention yourself.

        - don't repeat the same question before user gives an answer. wait before user gives an answer.
        -- after using a tool you don't ask the same question again. wait for user input.
        
        - send joyful messages.
        """,
    tools=[load_question_schema_from_api, get_onboarding_status, save_user_info, register_user_in_db],
)
## there should be the state of if_asked for each question too.

# Step 2: Set up session service (In-memory or Database)
# InMemorySessionService stores conversations in RAM (temporary)
# session_service = InMemorySessionService()

SUPABASE_ONBOARDING_AGENT_MEMORY_DB_URL = os.getenv("SUPABASE_ONBOARDING_AGENT_MEMORY_DB_URL")
db_url = SUPABASE_ONBOARDING_AGENT_MEMORY_DB_URL
session_service = DatabaseSessionService(db_url=db_url)

# Step 3: Create the Runner
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)