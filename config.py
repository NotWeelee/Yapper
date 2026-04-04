import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Webhook
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")  # ngrok URL

# Call settings
SPEECH_TIMEOUT = int(os.getenv("SPEECH_TIMEOUT", "4"))
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "en-US")
MAX_TURNS = int(os.getenv("MAX_TURNS", "20"))

# LLM Judge (Anthropic)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-4-20250514")

# Scenarios
SCENARIO_DIR = os.getenv(
    "SCENARIO_DIR",
    os.path.join(os.path.dirname(__file__), "scenarios")
)