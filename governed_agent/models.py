"""Model backends for the governed harness.

Three backends, one interface:

- ScriptedModel: deterministic, scripted responses. Runs with no keys,
  no GPU, no network. This is what the tests and the eval suite use.
- OllamaModel: a local model over plain HTTP (no SDK). Requires Ollama
  running locally with the named model pulled.
- CloudModel: one cloud model through an OpenAI-compatible chat
  completions endpoint, configured by environment variables. Never
  used unless GOVERNED_AGENT_API_KEY is set.

Every call returns a ModelResponse with the raw text plus an estimated
token count (words + code tokens, documented as an estimate) and the
latency of the call, so evals can report cost/latency/tokens for any
backend without backend-specific accounting.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


def estimate_tokens(text: str) -> int:
    """Rough token estimate (whitespace tokens + punctuation splits).

    Documented as an estimate, not a tokenizer count. Used for
    cost/latency reporting with the demo and local models, where no
    provider token count exists.
    """
    if not text:
        return 0
    return max(1, len(text.split()))


@dataclass
class ModelResponse:
    """One model call's result, with accounting attached."""

    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str = ""
    raw: dict | None = None

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out


class ModelBackend:
    """Interface every backend implements."""

    name: str = "base"

    def complete(self, messages: list[dict], **kwargs) -> ModelResponse:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"backend": self.name}


class ScriptedModel(ModelBackend):
    """Deterministic scripted model.

    `script` maps a call index (0, 1, 2, ...) to the exact text the
    model returns on that call. A `default` response is used once the
    script runs out. A `seed` selects a variant script, so the same
    task can be run with different seeded behaviours (used for pass@k
    in the eval suite).

    The scripted model never calls the network and never varies
    between runs with the same seed: same input, same output.
    """

    name = "scripted"

    def __init__(
        self,
        script: list[str] | None = None,
        default: str | None = None,
        seed: int = 0,
        variants: dict[int, list[str]] | None = None,
        model_id: str = "scripted-demo-v1",
    ):
        self.script = list(script or [])
        self.default = default or '{"done": true, "result": "no further action"}'
        self.seed = seed
        self.variants = variants or {}
        self.model_id = model_id
        self.calls = 0

    def _active_script(self) -> list[str]:
        if self.seed in self.variants:
            return list(self.variants[self.seed])
        return self.script

    def complete(self, messages: list[dict], **kwargs) -> ModelResponse:
        start = time.monotonic()
        script = self._active_script()
        idx = self.calls
        self.calls += 1
        text = script[idx] if idx < len(script) else self.default
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        return ModelResponse(
            text=text,
            tokens_in=estimate_tokens(prompt_text),
            tokens_out=estimate_tokens(text),
            latency_ms=(time.monotonic() - start) * 1000,
            model=self.model_id,
        )

    def describe(self) -> dict:
        return {"backend": self.name, "model": self.model_id, "seed": self.seed}


class OllamaModel(ModelBackend):
    """Local model via Ollama's plain HTTP API (no SDK).

    Requires Ollama running (default http://localhost:11434) with the
    model pulled, e.g. `ollama pull llama3.1:8b`. Raises a clear error
    if Ollama is not reachable, so a missing local model is never
    mistaken for a harness failure.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1:8b",
        host: str | None = None,
        timeout_s: float = 120.0,
    ):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout_s = timeout_s

    def complete(self, messages: list[dict], **kwargs) -> ModelResponse:
        start = time.monotonic()
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": kwargs.get("temperature", 0)},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama is not reachable at {self.host} "
                f"(is Ollama running? `ollama pull {self.model}`): {exc}"
            ) from exc
        text = payload.get("message", {}).get("content", "")
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        return ModelResponse(
            text=text,
            tokens_in=payload.get("prompt_eval_count") or estimate_tokens(prompt_text),
            tokens_out=payload.get("eval_count") or estimate_tokens(text),
            latency_ms=(time.monotonic() - start) * 1000,
            model=self.model,
            raw=payload,
        )

    def describe(self) -> dict:
        return {"backend": self.name, "model": self.model, "host": self.host}


class CloudModel(ModelBackend):
    """One cloud model via an OpenAI-compatible chat completions API.

    Configured entirely by environment, never by code:

    - GOVERNED_AGENT_API_KEY: required. Without it, complete() raises
      a clear error; the model is never silently used.
    - GOVERNED_AGENT_API_BASE: default https://api.openai.com/v1.
    - GOVERNED_AGENT_MODEL: default gpt-4o-mini.
    - GOVERNED_AGENT_PRICE_PER_1K: optional "in,out" USD per 1k tokens
      for cost reporting (e.g. "0.00015,0.0006").

    Cost reporting uses the provider's token counts when present and
    the price above when set; otherwise cost is reported as unknown,
    never invented.
    """

    name = "cloud"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("GOVERNED_AGENT_API_KEY", "")
        self.api_base = (api_base or os.environ.get("GOVERNED_AGENT_API_BASE", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("GOVERNED_AGENT_MODEL", "gpt-4o-mini")
        price = os.environ.get("GOVERNED_AGENT_PRICE_PER_1K", "")
        self.price_in, self.price_out = self._parse_price(price)

    @staticmethod
    def _parse_price(raw: str) -> tuple[float | None, float | None]:
        try:
            a, b = raw.split(",")
            return float(a), float(b)
        except Exception:
            return None, None

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float | None:
        if self.price_in is None or self.price_out is None:
            return None
        return (tokens_in / 1000) * self.price_in + (tokens_out / 1000) * self.price_out

    def complete(self, messages: list[dict], **kwargs) -> ModelResponse:
        if not self.api_key:
            raise RuntimeError(
                "No cloud API key: set GOVERNED_AGENT_API_KEY to use the "
                "cloud model backend. The demo and Ollama backends need no key."
            )
        start = time.monotonic()
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0),
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=kwargs.get("timeout_s", 120.0)) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Cloud model request failed ({exc.code}): {detail}") from exc
        choice = (payload.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "") or ""
        usage = payload.get("usage") or {}
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        return ModelResponse(
            text=text,
            tokens_in=usage.get("prompt_tokens") or estimate_tokens(prompt_text),
            tokens_out=usage.get("completion_tokens") or estimate_tokens(text),
            latency_ms=(time.monotonic() - start) * 1000,
            model=self.model,
            raw=payload,
        )

    def describe(self) -> dict:
        return {"backend": self.name, "model": self.model, "api_base": self.api_base}
