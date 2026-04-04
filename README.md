# Yapper

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
- A Twilio account with a phone number
- ngrok (for local development)
- An Anthropic API key (optional, for LLM judge analysis)

## Installation

```bash
git clone https://github.com/youruser/yapper.git
cd yapper
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+15551234567
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok-free.app
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
```

Start ngrok before running:

```bash
ngrok http 5000
```

Copy the ngrok URL into your `.env` as `WEBHOOK_BASE_URL`.

## Usage

```bash
# List all available scenarios
python yapper.py --list-scenarios

# Run all scenarios against a target
python yapper.py --target +15559876543 --all

# Run a specific scenario
python yapper.py --target +15559876543 --scenario prompt_injection_canary

# Run all scenarios in a category
python yapper.py --target +15559876543 --category LLM01_prompt_injection

# Run without the LLM judge (pattern matching only)
python yapper.py --target +15559876543 --all --no-judge

# Verbose output with full transcripts
python yapper.py --target +15559876543 --all --verbose

# Save JSON report
python yapper.py --target +15559876543 --all --output report.json
```

## Architecture

```
yapper.py            CLI entry point
config.py            Settings and credentials from environment
scenario_loader.py   Loads and validates YAML scenario files
engine.py            Conversation state machine and turn management
webhook.py           Flask server handling Twilio callbacks
caller.py            Initiates outbound calls via Twilio
analyzer.py          Post-call analysis (pattern matching + LLM judge)
reporter.py          Terminal summary and JSON report output
scenarios/           YAML attack scenario definitions
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

## Limitations

- Telephony only — operates over phone calls via Twilio
- STT dependent — analysis quality depends on Twilio's speech recognition accuracy
- Sequential — runs one scenario per call, one call at a time
- No audio-level attacks — operates at the transcript level, not the audio waveform level

## Responsible Use

This tool is intended for authorized security testing and research only. Always obtain explicit written permission before testing any system you do not own. Unauthorized use of this tool may violate applicable laws.

## License

MIT
