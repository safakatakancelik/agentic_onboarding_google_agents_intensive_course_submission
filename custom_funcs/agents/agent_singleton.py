"""Singleton access to the Google-ADK runner for the Flask app.

This keeps a single `Runner` instance (with its `InMemorySessionService`) in
memory for the lifetime of the Flask process so the short-lived in-memory
conversation history is shared across HTTP requests.
"""
from __future__ import annotations

import asyncio
from typing import Final
from google.genai import types
from google.adk.events import Event
from uuid import uuid4

# Import the already-configured runner from agent.py.  This triggers agent.py
# once, creating the root_agent, session_service and runner objects.
from .agent import runner, session_service  # noqa: E402

# ---------------------------------------------------------------------------
# Persistent event loop
# ---------------------------------------------------------------------------
# Creating a single event loop that remains open for the lifetime of the Flask
# process prevents "Event loop is closed" errors that occur when asyncio.run()
# closes a loop while background tasks are still pending.
_LOOP: asyncio.AbstractEventLoop = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)

__all__ = ["ask_agent"]



async def _ask_async(prompt: str, session_id: str) -> list[str]:
    """Async helper that forwards the prompt to the ADK runner using given session id."""
    
    WELCOME_TEXT = "Hello! I'm here to help you complete your onboarding. Ready to start?"

    # Ensure the session exists in the database before running
    try:
        await session_service.create_session(
            app_name=runner.app_name,
            user_id=session_id,
            session_id=session_id
        )

    except Exception:
        # Session likely already exists, which is fine
        pass


    # Create a Content object for the user message
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    # Use run_async directly, passing session_id as user_id to ensure isolation
    response_iterator = runner.run_async(new_message=message, session_id=session_id, user_id=session_id)

    collected_text = []
    async for event in response_iterator:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    collected_text.append(part.text)
    
    if collected_text:
        return collected_text
    
    # Fallback if no valid text found
    return ["Sorry, my functions needs polishing, can you please repeat?"]


def ask_agent(prompt: str, session_id: str) -> list[str]:
    """Synchronous wrapper executed inside Flask using the persistent loop.

    Args:
        prompt: User message.
        session_id: Unique identifier for the user's chat session (e.g. per-browser).
    """
    return _LOOP.run_until_complete(_ask_async(prompt, session_id))
