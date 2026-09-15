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

# Ceiling on how far down a scenario's turn list the engine walks, so only the
# first MAX_TURNS entries of "turns" are ever sent. It bounds position in the
# list, not the number of utterances spoken. Those are the same number until a
# branch jumps backward and replays turns, and a scenario that loops that way
# is not bounded by this at all; CALL_TIMEOUT is what ends it.
MAX_TURNS = int(os.getenv("MAX_TURNS", "20"))

# Twilio caps a single <Gather> at 60 seconds of speech, so an agent that talks
# past that arrives truncated and the rest bleeds into the next capture. The
# engine can open extra silent gathers to collect the remainder instead of
# speaking over it; this bounds how many it will chain onto one turn.
MAX_CONTINUATIONS = int(os.getenv("MAX_CONTINUATIONS", "2"))

# How long to wait for a call to finish. A verbose agent can hold a single
# gather open for the full 60 second cap, so a scripted scenario runs for many
# minutes. CALL_TIMEOUT is the absolute ceiling; CALL_IDLE_TIMEOUT gives up
# early when no webhook has arrived in that long, which is the real signal
# that a call has died rather than merely being slow.
CALL_TIMEOUT = int(os.getenv("CALL_TIMEOUT", "900"))
CALL_IDLE_TIMEOUT = int(os.getenv("CALL_IDLE_TIMEOUT", "150"))

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

# Scenario generator
# Recon and scenario generation are a different job from judging a transcript,
# so they get their own provider and model. Both fall back to the judge's
# settings, which keeps a single-provider setup working with no extra config.
GENERATOR_PROVIDER = os.getenv("GENERATOR_PROVIDER", JUDGE_PROVIDER).lower()
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", JUDGE_MODEL)
GENERATOR_BASE_URL = os.getenv("GENERATOR_BASE_URL", JUDGE_BASE_URL)

# Scenarios
SCENARIO_DIR = os.getenv(
    "SCENARIO_DIR",
    os.path.join(os.path.dirname(__file__), "scenarios")
)