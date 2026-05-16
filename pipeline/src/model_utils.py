"""Model utilities: provider detection, cost tracking, and shared setup.

Supports three providers:
- Gemini direct (default for google/ models): uses GEMINI_API_KEY
- OpenRouter (fallback): model names like "google/gemini-2.5-flash" via OPENROUTER_API_KEY
- OpenAI direct: model names prefixed with "openai/" (e.g., "openai/gpt-4o")

Cost tracking (TrackedLanguageModel) is only used for OpenAI models.
OpenRouter has its own billing dashboard.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from collections.abc import Collection
from pathlib import Path

import httpx
from collections.abc import Sequence

from concordia.contrib.language_models.openai.gpt_model import GptLanguageModel
from concordia.language_model import language_model
from concordia.utils import measurements as measurements_lib


def parse_model_string(model_name: str) -> tuple[str, str | None, str]:
    """Parse a model string into (env_var_name, api_base, clean_name).

    - "openai/gpt-4o"                            -> ("OPENAI_API_KEY", None, "gpt-4o")
    - "google/gemini-2.5-flash"                  -> ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash")
    - "openrouter/google/gemini-2.5-flash"       -> ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash")
    - other                                      -> ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", model_name)
    """
    if model_name.startswith("openrouter/"):
        return ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", model_name[len("openrouter/"):])
    if model_name.startswith("openai/"):
        return ("OPENAI_API_KEY", None, model_name[len("openai/"):])
    if model_name.startswith("google/"):
        clean = model_name[len("google/"):]
        return ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/", clean)
    return ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", model_name)


# ---------------------------------------------------------------------------
# Cost tracking (OpenAI only)
# ---------------------------------------------------------------------------

# Prices per 1M tokens (USD) — last updated 2026-04-07
PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":        {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":   {"input": 0.15,  "output": 0.60},
    "gpt-4.1":       {"input": 2.00,  "output": 8.00},
    "gpt-4.1-mini":  {"input": 0.40,  "output": 1.60},
    "gpt-4.1-nano":  {"input": 0.10,  "output": 0.40},
    "o3":            {"input": 2.00,  "output": 8.00},
    "o3-mini":       {"input": 1.10,  "output": 4.40},
    "o4-mini":       {"input": 1.10,  "output": 4.40},
}


def compute_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated cost in USD. Returns 0.0 for unknown models.

    Accepts both prefixed ("openai/gpt-4o") and clean ("gpt-4o") names.
    """
    clean = model_name.removeprefix("openai/")
    prices = PRICING.get(clean)
    if not prices:
        return 0.0
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


COSTS_FILE = Path(__file__).parent.parent / "costs.jsonl"


def log_cost(
    task: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    call_count: int,
    cost_usd: float,
    **extra: object,
) -> None:
    """Append a cost entry to pipeline/costs.jsonl."""
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "task": task,
        "model": model_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "calls": call_count,
        "cost_usd": cost_usd,
        **extra,
    }
    with open(COSTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


class TrackedLanguageModel(GptLanguageModel):
    """GptLanguageModel subclass that captures token usage per call.

    Only used for OpenAI direct models where we need cost tracking.
    Overrides _sample_text() to extract response.usage before returning.
    """

    def __init__(
        self,
        model_name: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        measurements: measurements_lib.Measurements | None = None,
        channel: str = language_model.DEFAULT_STATS_CHANNEL,
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            measurements=measurements,
            channel=channel,
        )
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

    def _sample_text(
        self,
        prompt: str,
        reasoning_effort: str,
        verbosity: str,
        *,
        max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
        terminators: Collection[str] = language_model.DEFAULT_TERMINATORS,
        temperature: float = 1.0,
        top_p: float = language_model.DEFAULT_TOP_P,
        timeout: float = language_model.DEFAULT_TIMEOUT_SECONDS,
        seed: int | None = None,
    ) -> str:
        del terminators, top_p

        messages = [
            {
                "role": "system",
                "content": (
                    "You always continue sentences provided "
                    "by the user and you never repeat what "
                    "the user already said."
                ),
            },
            {
                "role": "user",
                "content": "Question: Is Jake a turtle?\nAnswer: Jake is ",
            },
            {"role": "assistant", "content": "not a turtle."},
            {
                "role": "user",
                "content": (
                    "Question: What is Priya doing right now?\nAnswer: "
                    "Priya is currently "
                ),
            },
            {"role": "assistant", "content": "sleeping."},
            {"role": "user", "content": prompt},
        ]

        # reasoning_effort/verbosity only supported by reasoning models (o-series)
        kwargs = dict(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=timeout,
            seed=seed,
        )
        if self._model_name.startswith("o"):
            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["verbosity"] = verbosity
        response = self._client.chat.completions.create(**kwargs)

        # Track token usage
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens or 0
            self.total_output_tokens += response.usage.completion_tokens or 0
        self.call_count += 1

        if self._measurements is not None:
            self._measurements.publish_datum(
                self._channel,
                {"raw_text_length": len(response.choices[0].message.content)},
            )

        return response.choices[0].message.content


_GEMINI_NATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_MULTIPLE_CHOICE_ATTEMPTS = 20


class GeminiLanguageModel(language_model.LanguageModel):
    """Language model that calls Gemini's native API via x-goog-api-key auth.

    Bypasses the OpenAI-compatible endpoint because new-style API keys
    (prefix "AQ.") aren't accepted there.
    """

    def __init__(
        self,
        model_name: str,
        *,
        api_key: str,
        api_base: str | None = None,
        measurements: measurements_lib.Measurements | None = None,
        channel: str = language_model.DEFAULT_STATS_CHANNEL,
    ):
        del api_base
        self._model_name = model_name
        self._api_key = api_key
        self._measurements = measurements
        self._channel = channel

    # Raise timeout above Concordia default (60s) — long-context Gemini calls
    # regularly exceed 60s and an uncaught ReadTimeout silently kills the run.
    _LONG_TIMEOUT = 300.0

    def _generate(self, prompt: str, *, max_tokens: int, temperature: float, timeout: float) -> str:
        url = f"{_GEMINI_NATIVE_BASE}/{self._model_name}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                # Gemini 2.5 defaults thinking=ON. Burns thinking tokens
                # before every reply (~3x latency). Disable.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        effective_timeout = max(float(timeout), self._LONG_TIMEOUT)
        try:
            r = httpx.post(
                url,
                headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
                json=payload,
                timeout=effective_timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"[GeminiLanguageModel] API error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            raise
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if self._measurements is not None:
            self._measurements.publish_datum(self._channel, {"raw_text_length": len(text)})
        return text

    def sample_text(
        self,
        prompt: str,
        *,
        max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
        terminators: Collection[str] = language_model.DEFAULT_TERMINATORS,
        temperature: float = 1.0,
        top_p: float = language_model.DEFAULT_TOP_P,
        top_k: int = language_model.DEFAULT_TOP_K,
        timeout: float = language_model.DEFAULT_TIMEOUT_SECONDS,
        seed: int | None = None,
    ) -> str:
        del terminators, top_p, top_k, seed
        return self._generate(prompt, max_tokens=max_tokens, temperature=temperature, timeout=timeout)

    def sample_choice(
        self,
        prompt: str,
        responses: Sequence[str],
        *,
        seed: int | None = None,
    ) -> tuple[int, str, dict[str, float]]:
        del seed
        augmented = (
            prompt
            + "\nRespond EXACTLY with one of the following strings:\n"
            + "\n".join(responses)
            + "."
        )
        answer = ""
        for attempts in range(_MAX_MULTIPLE_CHOICE_ATTEMPTS):
            answer = self._generate(augmented, max_tokens=language_model.DEFAULT_MAX_TOKENS, temperature=1.0, timeout=language_model.DEFAULT_TIMEOUT_SECONDS)
            clean = answer.strip().rstrip(".").strip()
            try:
                idx = responses.index(clean)
            except ValueError:
                try:
                    idx = [r.lower() for r in responses].index(clean.lower())
                except ValueError:
                    continue
            if self._measurements is not None:
                self._measurements.publish_datum(self._channel, {"choices_calls": attempts})
            return idx, responses[idx], {}
        raise language_model.InvalidResponseError(
            f"Too many multiple choice attempts. Last: {answer}"
        )


def setup_model(model_name: str) -> GptLanguageModel:
    """Create an LLM from a model string.

    Returns TrackedLanguageModel for openai/ models, GeminiLanguageModel for
    google/ models, plain GptLanguageModel otherwise (OpenRouter).
    """
    env_var, api_base, clean_name = parse_model_string(model_name)
    api_key = os.environ.get(env_var)
    if not api_key:
        print(f"ERROR: {env_var} not found in environment")
        sys.exit(1)

    if model_name.startswith("openai/"):
        return TrackedLanguageModel(
            model_name=clean_name,
            api_key=api_key,
            api_base=api_base,
        )
    # openrouter/ prefix bypasses Gemini-native routing and uses OpenRouter
    # via the plain GptLanguageModel (OpenAI-compatible) client.
    if model_name.startswith("google/") and not model_name.startswith("openrouter/"):
        return GeminiLanguageModel(
            model_name=clean_name,
            api_key=api_key,
            api_base=api_base,
        )
    return GptLanguageModel(
        model_name=clean_name,
        api_key=api_key,
        api_base=api_base,
    )


# ---------------------------------------------------------------------------
# Code generation helpers (for instantiate.py)
# ---------------------------------------------------------------------------

def tracked_model_class_code() -> str:
    """Return TrackedLanguageModel + PRICING + compute_cost as inline Python code.

    Used by instantiate.py to embed in generated scripts that run as
    subprocesses and can't import from pipeline/src/.
    """
    return '''
# --- Cost tracking (OpenAI only) ---
class TrackedLanguageModel(GptLanguageModel):
    """GptLanguageModel subclass that captures token usage per call."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0

    def _sample_text(self, prompt, reasoning_effort, verbosity, *,
                     max_tokens=5000, terminators=(), temperature=1.0,
                     top_p=0.95, timeout=60, seed=None):
        del terminators, top_p
        messages = [
            {"role": "system", "content": "You always continue sentences provided by the user and you never repeat what the user already said."},
            {"role": "user", "content": "Question: Is Jake a turtle?\\nAnswer: Jake is "},
            {"role": "assistant", "content": "not a turtle."},
            {"role": "user", "content": "Question: What is Priya doing right now?\\nAnswer: Priya is currently "},
            {"role": "assistant", "content": "sleeping."},
            {"role": "user", "content": prompt},
        ]
        kwargs = dict(
            model=self._model_name, messages=messages,
            temperature=temperature, max_completion_tokens=max_tokens,
            timeout=timeout, seed=seed,
        )
        if self._model_name.startswith("o"):
            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["verbosity"] = verbosity
        response = self._client.chat.completions.create(**kwargs)
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens or 0
            self.total_output_tokens += response.usage.completion_tokens or 0
        self.call_count += 1
        if self._measurements is not None:
            self._measurements.publish_datum(
                self._channel,
                {"raw_text_length": len(response.choices[0].message.content)},
            )
        return response.choices[0].message.content


PRICING = {
    "gpt-4o":       {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":  {"input": 0.15,  "output": 0.60},
    "gpt-4.1":      {"input": 2.00,  "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40,  "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10,  "output": 0.40},
    "o3":           {"input": 2.00,  "output": 8.00},
    "o3-mini":      {"input": 1.10,  "output": 4.40},
    "o4-mini":      {"input": 1.10,  "output": 4.40},
}


def compute_cost(model_name, input_tokens, output_tokens):
    """Compute estimated cost in USD."""
    clean = model_name.replace("openai/", "", 1) if model_name.startswith("openai/") else model_name
    prices = PRICING.get(clean)
    if not prices:
        return 0.0
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
'''


def gemini_model_class_code() -> str:
    """Return GeminiLanguageModel class as inline Python code.

    Embedded in generated benchmark scripts so google/* models call Gemini's
    native endpoint (with x-goog-api-key header). Bypasses the OpenAI-compatible
    endpoint which (a) rejects the `seed` parameter Concordia always sends and
    (b) doesn't accept new-style "AQ." prefixed Gemini API keys.
    """
    return '''
# --- Gemini native-API language model (drops seed, uses x-goog-api-key) ---
import httpx as _httpx

class GeminiLanguageModel(language_model.LanguageModel):
    """LanguageModel that calls Gemini's native generateContent endpoint."""

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"
    _MAX_MC_ATTEMPTS = 20

    def __init__(self, model_name, *, api_key=None, api_base=None, measurements=None, channel=language_model.DEFAULT_STATS_CHANNEL):
        del api_base
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._measurements = measurements
        self._channel = channel

    # Raise timeout above Concordia default (60s) since long-context Gemini calls
    # can take longer, and any uncaught ReadTimeout kills the sim silently.
    _LONG_TIMEOUT = 300.0

    def _generate(self, prompt, *, max_tokens, temperature, timeout):
        url = f"{self._BASE}/{self._model_name}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        effective_timeout = max(float(timeout), self._LONG_TIMEOUT)
        try:
            r = _httpx.post(
                url,
                headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
                json=payload,
                timeout=effective_timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            import sys as _sys
            print(f"[GeminiLanguageModel] API error: {type(exc).__name__}: {exc}", file=_sys.stderr, flush=True)
            raise
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if self._measurements is not None:
            self._measurements.publish_datum(self._channel, {"raw_text_length": len(text)})
        return text

    def sample_text(self, prompt, *, max_tokens=language_model.DEFAULT_MAX_TOKENS,
                    terminators=language_model.DEFAULT_TERMINATORS, temperature=1.0,
                    top_p=language_model.DEFAULT_TOP_P, top_k=language_model.DEFAULT_TOP_K,
                    timeout=language_model.DEFAULT_TIMEOUT_SECONDS, seed=None):
        del terminators, top_p, top_k, seed
        return self._generate(prompt, max_tokens=max_tokens, temperature=temperature, timeout=timeout)

    def sample_choice(self, prompt, responses, *, seed=None):
        del seed
        augmented = prompt + "\\nRespond EXACTLY with one of the following strings:\\n" + "\\n".join(responses) + "."
        answer = ""
        for attempts in range(self._MAX_MC_ATTEMPTS):
            answer = self._generate(augmented, max_tokens=language_model.DEFAULT_MAX_TOKENS, temperature=1.0, timeout=language_model.DEFAULT_TIMEOUT_SECONDS)
            clean = answer.strip().rstrip(".").strip()
            try:
                idx = responses.index(clean)
            except ValueError:
                try:
                    idx = [r.lower() for r in responses].index(clean.lower())
                except ValueError:
                    continue
            if self._measurements is not None:
                self._measurements.publish_datum(self._channel, {"choices_calls": attempts})
            return idx, responses[idx], {}
        raise language_model.InvalidResponseError(f"Too many multiple choice attempts. Last: {answer}")
'''
