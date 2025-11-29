"""
Central configuration for the onboarding system.
App settings and labels are defined here.
Questions are managed separately in questions.py
"""
import os

# App settings
APP_TITLE = "Onboarding System"
ONBOARDING_HEADER = "Welcome to the Onboarding Process"
ONBOARDING_DESCRIPTION = "Please choose a mode to get started."

# Mode labels
CHATBOT_MODE_LABEL = "Agentic"
LEGACY_MODE_LABEL = "Form"



class Config:
    """
    Flask configuration class.
    Reads from environment variables, defaults to safe values for local dev.
    """
    # 1. SECRET_KEY: Critical for session security
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # 2. DEBUG: Casts the env var string 'False'/'0' to a boolean
    # If FLASK_DEBUG is missing, it defaults to False (Production safe)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1']