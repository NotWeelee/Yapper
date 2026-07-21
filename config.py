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
SPEECH_TIMEOUT = os.getenv("SPEECH_TIMEOUT", "3")
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "deepgram_nova-3")
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "en-US")
MAX_TURNS = int(os.getenv("MAX_TURNS", "20"))

# LLM Judge
# Provider selects where the judge runs:
#   "anthropic" (default) -> Anthropic API, uses ANTHROPIC_API_KEY
#   "local"               -> any OpenAI-compatible local server (Ollama, LM Studio)
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "anthropic").lower()
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-4-6")

# Base URL for the local OpenAI-compatible server (only used when JUDGE_PROVIDER=local)
#   Ollama:    http://localhost:11434/v1
#   LM Studio: http://localhost:1234/v1
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "http://localhost:11434/v1")

# Anthropic (used when JUDGE_PROVIDER=anthropic)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Scenarios
SCENARIO_DIR = os.getenv(
    "SCENARIO_DIR",
    os.path.join(os.path.dirname(__file__), "scenarios")
)