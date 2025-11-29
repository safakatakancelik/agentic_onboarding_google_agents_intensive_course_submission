"""
Flask application for the onboarding system.
Supports both chatbot-based and legacy form-based onboarding.
"""

from flask import Flask, render_template, request, jsonify, session
from config import (
    Config,
    APP_TITLE,
    ONBOARDING_HEADER,
    ONBOARDING_DESCRIPTION,
    CHATBOT_MODE_LABEL,
    LEGACY_MODE_LABEL
)

from custom_funcs.read_sheet import read_sheet_retrieve_questions
# Import the ADK runner helper that talks to Gemini
from custom_funcs.agents.agent_singleton import ask_agent
from uuid import uuid4
from custom_funcs.supabase_client import create_user
from typing import List, Dict, Set, Any

# ---------------- Global helpers ----------------

def _load_questions() -> List[Dict[str, Any]]:
    """Load questions once at app startup for quick validation."""
    response = read_sheet_retrieve_questions()
    if response.get('status') != 'success':
        return []

    values = response.get('values', [])
    if not values or len(values) < 2:
        return []

    headers = values[0]
    questions: List[Dict[str, Any]] = []
    for row in values[1:]:
        if not row:
            continue
        question = {headers[i]: row[i] if i < len(row) else '' for i in range(len(headers))}
        questions.append(question)
    return questions

# end of global helpers ----------------------------------------------------


app = Flask(__name__)
app.config.from_object(Config)


@app.route('/retrieve_all_questions', methods=['GET', 'POST'])
def retrieve_all_questions_route():
    """
    Route to fetch questions from the admin panel. Currently Google Sheet serves the admin panel purpose.
    Can be called manually or used as a tool by agents.
    """
    response = read_sheet_retrieve_questions()

    if response.get('status') != 'success':
        error_msg = response.get('error_message', 'Unknown error occurred')
        return jsonify({
            'success': False,
            'error': f"There's currently an issue loading questions: {error_msg}"
        }), 500
    
    values = response.get('values', [])
    
    if not values or len(values) < 2:  # Need at least header row + 1 data row
        return jsonify({
            'success': False,
            'error': "There's currently an issue loading questions. Please try again later or contact support."
        }), 500
    
    # First row contains headers
    headers = values[0]
    
    # Convert rows to question dictionaries
    questions = []
    for row in values[1:]:  # Skip header row
        if not row:  # Skip empty rows
            continue
        
        # Create a dictionary mapping headers to values
        question = {}
        for i, header in enumerate(headers):
            # Use empty string if row doesn't have enough columns
            value = row[i] if i < len(row) else ''
            question[header] = value
        
        questions.append(question)
    
    if questions:
        return jsonify({
            'success': True,
            'message': f'Successfully loaded {len(questions)} questions',
            'questions': questions,
            'questions_count': len(questions)
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': "There's currently an issue loading questions. Please try again later or contact support."
        }), 500


@app.route('/')
def index():
    """Main onboarding page – defaults to chatbot view."""
    # Load questions with home page startup
    questions = _load_questions()
    # Persist questions for this user session so subsequent API calls can reuse them
    session['questions'] = questions

    # Force a new chat session ID on every visit to the home page
    session['chat_session_id'] = str(uuid4())


    if not questions:
        error_message = "There's currently an issue loading questions. Please try again later or contact support."
    else:
        error_message = None

    return render_template(
        'index.html',
        app_title=APP_TITLE,
        header=ONBOARDING_HEADER,
        description=ONBOARDING_DESCRIPTION,
        questions=questions,
        chatbot_mode_label=CHATBOT_MODE_LABEL,
        legacy_mode_label=LEGACY_MODE_LABEL,
        error_message=error_message
    )


@app.route('/api/agent_chat', methods=['POST'])
def agent_chat():
    """Endpoint used by the frontend to chat with the ADK agent.

    Expected request JSON  {"message": "..."}
    Response mirrors the legacy format so that the front-end code remains unchanged:
        {"success": true, "response": "..."}
    """
    data = request.get_json() or {}
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({'success': False, 'error': 'message field required'}), 400

    # Ensure each browser/user gets a unique ADK session id stored in the Flask
    # cookie-based session. This prevents users from sharing the same Gemini
    # conversation context.
    chat_session_id = session.get('chat_session_id')
    if chat_session_id is None:
        chat_session_id = str(uuid4())
        session['chat_session_id'] = chat_session_id

    try:
        reply = ask_agent(user_message, chat_session_id)
    except Exception as exc:
        app.logger.exception("Agent failure")
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({'success': True, 'response': reply}), 200


# ---------------- REGISTRATION ----------------

# Validation helper
def _validate_registration_payload(payload: Dict[str, Any], questions: List[Dict[str, Any]]):
    """Return (is_valid: bool, error_message: str)."""
    if not questions:
        # If questions failed to load, skip validation to avoid blocking registrations
        return True, ""

    accepted_fields: Set[str] = {q.get('questioned_entity') for q in questions if q.get('questioned_entity')}
    required_fields: Set[str] = {
        q.get('questioned_entity')
        for q in questions
        if q.get('questioned_entity') and q.get('is_mandatory', '').upper() == 'Y'
    }

    # Check for required fields
    missing = required_fields - payload.keys()
    if missing:
        return False, f"Missing required fields: {', '.join(sorted(missing))}"

    # Check for unexpected fields
    unexpected = set(payload.keys()) - accepted_fields
    if unexpected:
        return False, f"Unexpected fields detected: {', '.join(sorted(unexpected))}"

    return True, ""


@app.route('/api/register', methods=['POST'])
def register():
    """
    Endpoint to handle user registration submissions.
    Forwards the registration to the downstream onboarding provider.
    """
    data = request.get_json() or {}
    app.logger.debug("Registration request received: %s", data)

    # Retrieve questions from session or fall back to fresh load
    questions = session.get('questions') or _load_questions()

    # Dynamic validation against current questions
    is_valid, error_msg = _validate_registration_payload(data, questions)
    if not is_valid:
        return jsonify({"success": False, "error": error_msg}), 400

    # Forward the entire payload to Supabase
    # print(data)
    result = create_user(data)

    return jsonify(result), result.get('status_code', 500)





if __name__ == '__main__':
    app.run(debug=False, port=5000)

