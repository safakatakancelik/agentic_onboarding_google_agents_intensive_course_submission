"""
Helper utilities for interacting with Supabase edge functions.
"""

import os
from typing import Any, Dict, Optional

import requests


SUPABASE_ONBOARD_USER_URL = os.getenv("SUPABASE_ONBOARD_USER_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def create_user(user_data: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    """
    Call the Supabase `create-user` edge function with the provided registration payload.

    Args:
        user_data: Dictionary containing the full registration payload collected from the
            onboarding form / agent.
        timeout: Optional request timeout in seconds.
    
    Example `user_data`:
    {'name': 'Adam', 
    'username': 'AdamNov17', 
    'email': 'appleeateradam@gmail.com', 
    'occupation': 'wanderer'
    }        
        

    Returns:
        A dictionary containing:
            - success (bool): Whether the request succeeded.
            - data (dict): Parsed JSON or raw text wrapped in a dict.
            - error (str, optional): Error message if the request failed.
            - status_code (int): HTTP status code of the response.
    """
    # Basic validation – ensure the payload is a non-empty dictionary
    if not isinstance(user_data, dict) or not user_data:
        return {
            "success": False,
            "error": "`user_data` must be a non-empty dictionary",
            "status_code": 400,
        }

    try:
        headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            SUPABASE_ONBOARD_USER_URL,
            json=user_data,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "success": False,
            "error": f"Supabase request failed: {exc}",
            "status_code": 502,
        }

    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    return {
        "success": True,
        "data": data,
        "status_code": 200,
    }

