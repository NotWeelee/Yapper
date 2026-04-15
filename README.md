# Yapper
**v0.1.0**

A security testing tool for voice-based AI agents, mapped to the OWASP Top 10 for LLM Applications (2025).

AI voice agents are replacing human operators across industries — answering phones, handling intake, routing requests. While prompt injection testing tools exist for text-based chatbots, voice AI agents have received significantly less security scrutiny. Yapper closes that gap by placing real phone calls to voice AI agents, running scripted attack scenarios, and analyzing the responses for signs of successful exploitation.

## How It Works

Yapper places outbound calls via Twilio, speaks attack utterances using text-to-speech, captures the agent's responses via speech recognition, and analyzes the transcripts using pattern matching and an LLM judge (Claude).

Each attack scenario is defined in a YAML file with a sequence of utterances and detection rules. Yapper steps through the scenario turn by turn, then evaluates whether the agent was compromised.

## Attack Categories

Scenarios are mapped to the OWASP Top 10 for LLM Applications:

| Category | OWASP ID | Scenarios | Description |
|---|---|---|---|
| Prompt Injection | LLM01 | 4 | Instruction override, canary injection, multi-turn escalation, context manipulation |
| Sensitive Information Disclosure | LLM02 | 4 | Other caller data, internal systems, tech stack, contact/routing info |
| Excessive Agency | LLM06 | 4 | Unauthorized actions, action manipulation, scope escalation, no verification |
| System Prompt Leakage | LLM07 | 4 | Direct extraction, social engineering, indirect extraction, injection to reveal |
| Misinformation | LLM09 | 4 | False premise acceptance, fabricated authority, confident speculation, contradictory info |

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Twilio account with a phone number
- [ngrok](https://ngrok.com/) (for local development)
- An Anthropic API key (optional, for LLM judge analysis)

## Installation

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install ngrok

```bash
# macOS
brew install ngrok

# Linux / WSL
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com bookworm main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update \
  && sudo apt install ngrok
```

Then add your ngrok auth token (from https://dashboard.ngrok.com/get-started/your-authtoken):

```bash
ngrok config add-authtoken YOUR_TOKEN_HERE
```

### Clone and set up Yapper

```bash
git clone https://github.com/yourusername/yapper.git
cd yapper
uv sync
```

## Configuration

Create a `.env` file in the project root:

```
# Required
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+15551234567
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok-free.app

# Required for LLM judge (optional if using --no-judge)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# Optional (defaults shown)
WEBHOOK_PORT=5000
SPEECH_TIMEOUT=4
SPEECH_LANGUAGE=en-US
MAX_TURNS=20
JUDGE_MODEL=claude-sonnet-4-20250514
```

### Setting up ngrok

Before running Yapper, start ngrok in a separate terminal:

```bash
ngrok http 5000
```

ngrok will display a forwarding URL like `https://a1b2c3d4.ngrok-free.app`. Copy this URL into your `.env` file as `WEBHOOK_BASE_URL`.

ngrok must stay running for the duration of the scan. On the free tier, the URL changes every time you restart ngrok, so you'll need to update your `.env` accordingly.

ngrok also provides a web inspector at `http://localhost:4040` where you can see every request Twilio makes to your webhook in real time (useful for debugging).

## Usage

```bash
# List all available scenarios
uv run python yapper.py --list-scenarios

# Run all scenarios against a target
uv run python yapper.py --target +15559876543 --all

# Run a specific scenario
uv run python yapper.py --target +15559876543 --scenario prompt_injection_canary

# Run all scenarios in a category
uv run python yapper.py --target +15559876543 --category LLM01_prompt_injection

# Run without the LLM judge (pattern matching only)
uv run python yapper.py --target +15559876543 --all --no-judge

# Verbose output with full transcripts
uv run python yapper.py --target +15559876543 --all --verbose

# Save JSON report
uv run python yapper.py --target +15559876543 --all --output report.json
```

## Writing Custom Scenarios

Create a YAML file in the `scenarios/` directory:

```yaml
name: my_custom_scenario
category: LLM01_prompt_injection
owasp_id: LLM01
severity: high
description: >
  Description of what this scenario tests.

turns:
  - send: "First utterance to the agent"
  - send: "Second utterance, building on the first"
  - send: "The main payload"

detect:
  keywords:
    - "word that indicates success"
  patterns:
    - "(?i)regex pattern to match"
  llm_judge:
    prompt: >
      Review the following transcript. Did the agent do X?
      Respond with a JSON object:
      {"finding": true/false, "confidence": 0-10, "reasoning": "..."}
    finding_threshold: 7
```

### Template Variables

- `{{last_response}}` — the agent's most recent response
- `{{turn_count}}` — number of turns sent so far

## Future Work
 
- Audio-level attacks (adversarial waveforms, STT manipulation)
- Branching scenario logic (adaptive multi-turn attacks based on agent responses)
- OpenAI TTS for more natural-sounding attack utterances
- Concurrent calls for faster scanning

## License

MIT