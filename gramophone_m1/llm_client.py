"""LLM client abstraction for Gramophone M1.

One interface, two backends:

- MockLLM: deterministic cassette backend used by default and by all tests.
  A cassette maps a role ("EXTRACT" / "ANALYZE") to an ordered list of canned
  responses ``{"text": str, "tokens": int}``. Calls consume responses in order
  (cycling deterministically once the list is exhausted) and count tokens.
- GeminiFlashLLM: Google Gemini Flash REST backend. Constructible WITHOUT a key
  (key resolved lazily from the constructor arg or GEMINI_API_KEY at call time),
  so wiring can be tested with no credentials and no network.

Budgets: every ``complete()`` call checks the token budget BEFORE spending. On
exhaustion it raises BudgetExhausted without consuming a cassette response or
spending tokens, so callers can degrade gracefully (fewer outputs, never wrong
ones).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

ROLE_EXTRACT = "EXTRACT"
ROLE_ANALYZE = "ANALYZE"


class BudgetExhausted(RuntimeError):
    """Raised when an LLM call would exceed its token budget (nothing spent)."""


class CassetteExhausted(RuntimeError):
    """Raised when MockLLM has no canned response for the requested role."""


class LLMClient(ABC):
    """Single LLM interface for all Gramophone stages."""

    @abstractmethod
    def complete(self, role: str, prompt: str, budget: int | None = None) -> dict:
        """Run one completion.

        Args:
            role: task role, one of ROLE_EXTRACT / ROLE_ANALYZE.
            prompt: full prompt text for the backend.
            budget: remaining token budget (total, across calls) or None.

        Returns:
            {"text": str, "tokens": int} with the backend's reply.
        """

    @property
    def total_tokens(self) -> int:
        """Tokens spent by this client so far."""
        return 0


class MockLLM(LLMClient):
    """Deterministic cassette-backed LLM for tests and default (offline) runs."""

    def __init__(self, cassette: dict | None = None):
        self.cassette: dict = cassette or {}
        self._cursors: dict[str, int] = {}
        self._spent: int = 0

    @classmethod
    def from_file(cls, path: str) -> "MockLLM":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def total_tokens(self) -> int:
        return self._spent

    def complete(self, role: str, prompt: str, budget: int | None = None) -> dict:
        _ = prompt  # canned backend: prompt is accepted but does not affect output
        resps = self.cassette.get(role) or []
        if not resps:
            raise CassetteExhausted(f"MockLLM: no cassette responses for role {role!r}")
        cursor = self._cursors.get(role, 0)
        resp = resps[cursor % len(resps)]
        tokens = int(resp.get("tokens", 0))
        if budget is not None and self._spent + tokens > budget:
            raise BudgetExhausted(
                f"MockLLM: budget {budget} exceeded (spent={self._spent}, need={tokens})"
            )
        self._cursors[role] = cursor + 1
        self._spent += tokens
        return {"text": resp.get("text", ""), "tokens": tokens}


class GeminiFlashLLM(LLMClient):
    """Google Gemini Flash REST backend (stdlib only, lazy key resolution)."""

    DEFAULT_MODEL = "gemini-3.5-flash-lite"
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # NOTE: no key required here; resolved lazily in complete().
        self._api_key = api_key
        self.model = model or os.environ.get("FLASH_MODEL", self.DEFAULT_MODEL)
        self._spent: int = 0

    @property
    def total_tokens(self) -> int:
        return self._spent

    def _resolve_key(self) -> str | None:
        return self._api_key or os.environ.get("GEMINI_API_KEY")

    def complete(self, role: str, prompt: str, budget: int | None = None) -> dict:
        key = self._resolve_key()
        if not key:
            raise RuntimeError(
                "GeminiFlashLLM: no API key (pass api_key= or set GEMINI_API_KEY)"
            )
        if budget is not None and self._spent >= budget:
            # Fail fast like MockLLM: never spend a paid call on a dead budget.
            raise BudgetExhausted(
                f"GeminiFlashLLM: budget {budget} already exhausted "
                f"(spent={self._spent})"
            )
        body = {
            "contents": [{"parts": [{"text": f"[ROLE {role}]\n{prompt}"}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        url = self.API_URL.format(model=self.model) + "?key=" + key
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        data = None
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                # HTTPError IS a URLError subclass: only transient codes
                # retry; anything else fails fast (raw, as before).
                if e.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                last_err = e
            except urllib.error.URLError as e:
                if attempt == 2:
                    raise
                last_err = e
            time.sleep(2 ** (attempt + 1))  # 2s, then 4s
        if data is None:  # unreachable: the 3rd failure always raises
            raise last_err  # type: ignore[misc]
        try:
            text = data["candidates"][0]["content"]["parts"][0].get("text", "")
        except (KeyError, IndexError, TypeError):
            text = ""
        tokens = int(data.get("usageMetadata", {}).get("totalTokenCount", 0))
        if budget is not None and self._spent + tokens > budget:
            raise BudgetExhausted(
                f"GeminiFlashLLM: budget {budget} exceeded "
                f"(spent={self._spent}, need={tokens})"
            )
        self._spent += tokens
        return {"text": text, "tokens": tokens}


def flash_llm_or_raise() -> GeminiFlashLLM:
    """Build the shared Flash backend for ``--llm flash`` CLIs.

    Raises:
        ValueError: when GEMINI_API_KEY is unset (CLIs map it to exit 2).
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("--llm flash needs GEMINI_API_KEY in the environment")
    return GeminiFlashLLM()
