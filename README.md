# Yapper
**v0.1.0**

A security testing tool for voice-based AI agents, with sample scenarios mapped to the OWASP Top 10 for LLM Applications (2025).

AI voice agents are replacing human operators across industries - answering phones, handling intake, and routing requests. While prompt injection testing tools exist for text-based chatbots, voice AI agents have received less security scrutiny. Yapper closes that gap by placing real phone calls to voice AI agents, running attack scenarios, and analyzing the responses for signs of successful exploitation.

## How It Works

Yapper places outbound calls via Twilio, speaks attack utterances using text-to-speech, captures the agent's responses via speech recognition, and analyzes the transcripts using pattern matching and an LLM judge (Claude by default, or a local model via Ollama).

Each attack scenario is defined in a YAML file with a sequence of utterances and detection rules. Yapper steps through the scenario turn by turn, then evaluates whether the agent was compromised.

## Attack Categories

Sample scenarios included are mapped to the OWASP Top 10 for LLM Applications:

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
- For the LLM judge (optional; skip with `--no-judge`): either an Anthropic API key (default), or [Ollama](https://ollama.com/) to run the judge locally — see [Running the LLM judge locally with Ollama](#running-the-llm-judge-locally-with-ollama)

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
git clone https://github.com/NotWeelee/yapper.git
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
JUDGE_MODEL=claude-sonnet-4-6

# Optional - run the LLM judge locally with Ollama instead of the Anthropic API
# (see "Running the LLM judge locally with Ollama" below)
# JUDGE_PROVIDER=local
# JUDGE_BASE_URL=http://localhost:11434/v1
```

### Setting up ngrok

Before running Yapper, start ngrok in a separate terminal:

```bash
ngrok http 5000
```

ngrok will display a forwarding URL like `https://a1b2c3d4.ngrok-free.app`. Copy this URL into your `.env` file as `WEBHOOK_BASE_URL`.

ngrok must stay running for the duration of the scan. On the free tier, the URL changes every time you restart ngrok, so you'll need to update your `.env` accordingly.

ngrok also provides a web inspector at `http://localhost:4040` where you can see every request Twilio makes to your webhook in real time (useful for debugging).

## Running the LLM judge locally with Ollama

By default Yapper's LLM judge uses the Anthropic API. For privacy-sensitive or offline testing, you can point the judge at a local Ollama server instead — no transcripts leave your machine.

### Setup

1. Add the OpenAI SDK (Ollama speaks the OpenAI API format). This is installed automatically by `uv sync`, but if you're adding it to an existing checkout:

   ```bash
   uv add openai
   ```

2. Install Ollama: https://ollama.com/download

3. Pull a judge model (see recommendations below):

   ```bash
   ollama pull llama3.1
   ```

4. Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1` by default, and the daemon starts automatically after install. Verify it's up:

   ```bash
   ollama list
   ```

5. Set these in your `.env`:

   ```
   JUDGE_PROVIDER=local
   JUDGE_BASE_URL=http://localhost:11434/v1
   JUDGE_MODEL=llama3.1
   ```

### Choosing a judge model

The judge does a classification task — read a transcript, return `{finding, confidence, reasoning}` as JSON. That job wants a plain **instruction-tuned model**, not a reasoning ("thinking") model. Thinking models route their answer through a separate reasoning channel, which can leave the response body empty and produce a "Failed to parse judge response" result. Instruct models return the answer directly, so they're the reliable choice here.

Recommended default: **`llama3.1`** (8B, ~4.9 GB). It's the most widely used model on Ollama, has no thinking mode to manage, and fits an 8 GB GPU with room for context.

Tested instruct models with no thinking to worry about:

| Model | Size | Fits |
|---|---|---|
| `llama3.1` | ~4.9 GB | 8 GB GPU (e.g. RTX 3060 Ti) |
| `llama3.2:3b` | ~2 GB | any laptop / fast iteration |
| `mistral:7b` | ~4.1 GB | 8 GB GPU |
| `qwen2.5:7b` | ~4.7 GB | 8 GB GPU (best non-English) |
| `phi-4` | ~9 GB | 16 GB GPU |

### Notes

- **Change `JUDGE_MODEL`.** Leaving it at a Claude model name fails against Ollama, since that model isn't loaded there. The value must match a model you've pulled (check with `ollama list`).
- **Watch the `:latest` tag on hybrid families.** Some families (e.g. `qwen3`, `qwen3.5`, `gemma4`) ship with thinking *on* by default, so pulling a bare `qwen3` can hand you a reasoning model and the empty-response problem above. Pin an explicit non-thinking tag like `qwen2.5:7b` instead.
- **Reasoning models can still work if you disable thinking.** Yapper sends `think: false` to the local model, which suppresses the reasoning pass on toggleable models like Qwen3 and DeepSeek-R1 distills. (GPT-OSS is the exception — it uses reasoning *levels* `low`/`medium`/`high` rather than an on/off switch.) A non-thinking instruct model is still the lower-variance choice.
- `ANTHROPIC_API_KEY` is not required when `JUDGE_PROVIDER=local`.
- Small models sometimes wrap JSON in prose or code fences; the judge parser strips fences and falls back to extracting the first `{...}` block. Very small models (<7B) may still produce unreliable verdicts — an 8B instruct model is a reasonable baseline.
- To switch back to Anthropic, set `JUDGE_PROVIDER=anthropic` (or remove the variable).

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
 
- Adaptive LLM-powered scenarios
- Branching scenario logic (adaptive multi-turn attacks based on agent responses)
- External STT provider usage
- Concurrent calls for faster yapping

## License

MIT
