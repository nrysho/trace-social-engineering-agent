"""one chat() over any openai-compatible endpoint.

- try providers in priority order (openai, then qwen), so a dead key or a refusal never stops a run
- apply qwen's reasoning-model rules: reasoning_effort, more max_tokens, strip leading newlines
- log every refusal to runs/refusals.log so a scoring run never dies silently

shared client: recon, writer and evaluator all call chat().
"""
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config

REFUSAL_LOG = Path(__file__).resolve().parents[1] / "runs" / "refusals.log"
TIMEOUT = 120  # the amd api can take up to 90s, so give it headroom

# openings that mean the model declined rather than answered. a heuristic, not exact.
REFUSAL_HINTS = ("i can't", "i cannot", "i'm sorry", "i am sorry", "i won't", "cannot assist", "can't help")


def _looks_like_refusal(text):
    low = text.strip().lower()
    return not low or any(h in low[:80] for h in REFUSAL_HINTS)


def _log_refusal(provider, text):
    REFUSAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with REFUSAL_LOG.open("a") as f:
        f.write(f"{stamp}\t{provider}\t{text[:300]!r}\n")


def _one_call(provider, messages, response_format):
    body = {"model": provider.model, "messages": messages}
    if provider.is_reasoning:
        body["max_tokens"] = 3000  # reasoning models spend tokens thinking before the answer
        body["reasoning_effort"] = "low"
    else:
        body["max_tokens"] = 2000
    if response_format:
        body["response_format"] = response_format  # e.g. openai json_schema for structured output
    r = requests.post(
        f"{provider.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json=body,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"] or ""
    return content.lstrip("\n")  # qwen can emit leading newlines before the real answer


def chat(messages, response_format=None):
    # walk providers until one answers without refusing; raise if they all fail
    errors = []
    for provider in config.llm_providers():
        try:
            text = _one_call(provider, messages, response_format)
        except requests.RequestException as e:
            errors.append(f"{provider.name}: {e}")
            continue
        if _looks_like_refusal(text):
            _log_refusal(provider.name, text)
            errors.append(f"{provider.name}: refusal")
            continue
        return text
    raise RuntimeError("all llm providers failed:\n" + "\n".join(errors))
