"""shared config: keys and llm providers.

- load keys from .env (same loader as smoke_test.py)
- define the llm providers in priority order: openai first, qwen (radeon) fallback

used by anything that calls the model (recon, writer, evaluator), not just recon.
"""
from dataclasses import dataclass
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # repo-root .env

# openai-compatible chat endpoints. both speak /chat/completions, so one client fits both.
OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4.1-mini"  # cheap, reliable structured json, runs on the eu credits
RADEON_BASE = "https://radeon-global.anruicloud.com/api/v1"
RADEON_MODEL = "Qwen3.8-27B"  # team's amd token-factory model, used as fallback


@dataclass
class LlmProvider:
    name: str
    base_url: str
    model: str
    api_key: str
    is_reasoning: bool  # qwen needs reasoning_effort + more room to answer


def load_env(path=ENV_PATH):
    # read KEY=value lines, skip blanks and comments, strip surrounding quotes
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def llm_providers(env=None):
    # the providers we hold a key for, in the order we try them
    env = env if env is not None else load_env()
    out = []
    if env.get("OPENAI_API_KEY"):
        out.append(LlmProvider("openai", OPENAI_BASE, OPENAI_MODEL, env["OPENAI_API_KEY"], False))
    if env.get("RADEON_API_KEY"):
        out.append(LlmProvider("qwen", RADEON_BASE, RADEON_MODEL, env["RADEON_API_KEY"], True))
    if not out:
        raise RuntimeError("no llm key found: set OPENAI_API_KEY or RADEON_API_KEY in .env")
    return out
