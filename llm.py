"""
Shared LLM dispatch.

Wraps the two providers yapper talks to behind one call so callers do not have
to care which is configured:

    "anthropic" -> the Anthropic API, using ANTHROPIC_API_KEY
    "local"     -> any OpenAI-compatible server (Ollama, LM Studio)

Both the scenario generator and the analyzer's LLM judge route through here.
"""

from config import ANTHROPIC_API_KEY


class LLMError(RuntimeError):
    """Raised when a provider is misconfigured or a call cannot be completed."""


# Clients are cached per (provider, base_url). Constructing one per call would
# build a fresh connection pool for every scenario in a scan.
_CLIENTS = {}


def check_provider(provider):
    """
    Return None if this provider is usable, otherwise a short reason why not.

    Callers use this at startup so a missing key or package degrades once, up
    front, instead of raising on every call.
    """
    if provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            return "no ANTHROPIC_API_KEY set"
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "the 'anthropic' package is not installed"
        return None

    if provider == "local":
        try:
            from openai import OpenAI  # noqa: F401
        except ImportError:
            return "the 'openai' package is not installed (uv add openai)"
        return None

    return f"unknown provider '{provider}' (expected 'anthropic' or 'local')"


def _client(provider, base_url=None):
    key = (provider, base_url)
    client = _CLIENTS.get(key)
    if client is not None:
        return client

    problem = check_provider(provider)
    if problem:
        raise LLMError(problem)

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    else:
        from openai import OpenAI
        # Local servers don't require a real key, but the SDK insists on one.
        client = OpenAI(base_url=base_url, api_key="local")

    _CLIENTS[key] = client
    return client


def call_model(prompt, model, provider="anthropic", base_url=None,
               max_tokens=4096, json_mode=False):
    """
    Send a single prompt and return the response text.

    json_mode asks servers that support it to guarantee syntactically valid
    JSON. Anthropic has no such switch, so there the caller still has to be
    ready to strip prose; see extract_json below.
    """
    if provider == "anthropic":
        return _call_anthropic(prompt, model, max_tokens)
    if provider == "local":
        return _call_local(prompt, model, base_url, max_tokens, json_mode)
    raise LLMError(f"unknown provider '{provider}' (expected 'anthropic' or 'local')")


def _call_anthropic(prompt, model, max_tokens):
    message = _client("anthropic").messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_local(prompt, model, base_url, max_tokens, json_mode):
    client = _client("local", base_url)

    # "think" is a no-op on a plain instruct model, but suppresses the reasoning
    # pass on toggleable ones (qwen3, deepseek-r1 distills) that would otherwise
    # return an empty message body.
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"think": False},
    )

    if json_mode:
        # Older servers reject response_format, so fall back to a plain call and
        # lean on extract_json instead.
        try:
            response = client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception:
            pass

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def extract_json(text):
    """
    Best-effort extraction of a JSON value from a model response. Tries the
    whole string, then a fenced block, then the outermost braces, since smaller
    models tend to wrap their answer in prose. Returns None if nothing parses.
    """
    import json
    import re

    if not text:
        return None

    cleaned = text.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    if "```json" in cleaned:
        fenced = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        fenced = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        fenced = None

    if fenced:
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
