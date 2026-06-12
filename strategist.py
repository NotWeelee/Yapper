"""
Strategist - LLM-powered adaptive utterance generation.

Given a scenario's strategy (objective, persona, guidelines) and
the conversation transcript so far, generates the next utterance
to speak to the target voice agent.
"""

import json
import anthropic
from config import ANTHROPIC_API_KEY, JUDGE_MODEL


client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def generate_utterance(strategy, transcript, turn_number):
    """
    Generate the next utterance based on the scenario strategy
    and conversation so far.

    Args:
        strategy: dict with objective, persona, guidelines, max_turns
        transcript: list of transcript entries so far
        turn_number: current turn number (0-indexed)

    Returns:
        str: the next utterance to speak
    """
    max_turns = strategy.get("max_turns", 6)
    turns_remaining = max_turns - turn_number

    # Build the conversation history for context
    history = ""
    if transcript:
        for entry in transcript:
            role = "AGENT" if entry["role"] == "agent" else "YOU"
            history += f"  [{role}] {entry['content']}\n"
    else:
        history = "  (No conversation yet — this is the first turn.)\n"

    # Build guidelines string
    guidelines = strategy.get("guidelines", [])
    guidelines_text = "\n".join(f"- {g}" for g in guidelines)

    prompt = f"""You are generating the next utterance for a voice call to an AI agent.
You must respond with ONLY the utterance text — no quotes, no explanation,
no prefix, no JSON. Just the raw words to be spoken.

OBJECTIVE:
{strategy['objective']}

YOUR PERSONA:
{strategy['persona']}

GUIDELINES:
{guidelines_text}

CONVERSATION SO FAR:
{history}
TURN: {turn_number + 1} of {max_turns} ({turns_remaining} remaining)

Based on the conversation so far, generate your next utterance.
Keep it natural and conversational — this will be spoken aloud via
text-to-speech over a phone call. Keep it under 3 sentences.
If this is the first turn and the agent hasn't spoken yet, say
something appropriate to initiate the call.
If this is one of the final turns, be more direct about the objective.
Respond with ONLY the utterance."""

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    utterance = response.content[0].text.strip()

    # Strip any quotes the model might have wrapped around it
    if utterance.startswith('"') and utterance.endswith('"'):
        utterance = utterance[1:-1]
    if utterance.startswith("'") and utterance.endswith("'"):
        utterance = utterance[1:-1]

    return utterance