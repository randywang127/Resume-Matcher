"""LLM client abstraction — supports Gemini, Anthropic, and OpenAI."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from resume_matcher.config import get_settings

logger = logging.getLogger(__name__)

# Maximum retries for transient failures
_MAX_RETRIES = 3
_RETRY_BACKOFF = [1, 3, 5]  # seconds


class LLMClient:
    """Unified interface for LLM API calls.

    Usage:
        client = LLMClient()
        text = client.complete("You are an ATS expert.", "Rewrite this resume...")
        data = client.complete_json("You are an ATS expert.", "Return JSON...", schema={...})
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.provider = settings.llm_provider
        self.model = settings.resolved_model
        self.api_key = settings.resolved_api_key
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.timeout = settings.llm_timeout

        if not self.api_key:
            raise ValueError(
                f"No API key configured for provider '{self.provider}'. "
                f"Set {self.provider.upper()}_API_KEY in your .env file."
            )

    # ── Public API ─────────────────────────────────────────────────

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt to the LLM and return the text response."""
        return self._call_with_retry(system_prompt, user_prompt, json_mode=False)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> dict:
        """Send a prompt and parse the response as JSON.

        Args:
            system_prompt: System instructions.
            user_prompt: User message.
            schema: Optional JSON schema hint (included in prompt for guidance).

        Returns:
            Parsed JSON dict.

        Raises:
            ValueError: If the response cannot be parsed as JSON after retries.
        """
        if schema:
            user_prompt += f"\n\nReturn your response as JSON matching this schema:\n```json\n{json.dumps(schema, indent=2)}\n```"

        raw = self._call_with_retry(system_prompt, user_prompt, json_mode=True)
        return self._parse_json(raw)

    # ── Provider dispatch ──────────────────────────────────────────

    def _call_with_retry(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> str:
        """Call the LLM with retry logic for transient failures."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                start = time.time()
                result = self._dispatch(system_prompt, user_prompt, json_mode)
                elapsed = time.time() - start
                logger.info(
                    "LLM call [%s/%s] completed in %.1fs (%d chars)",
                    self.provider,
                    self.model,
                    elapsed,
                    len(result),
                )
                return result
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(
                        "LLM call failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    time.sleep(wait)

        raise RuntimeError(
            f"LLM call failed after {_MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    def _dispatch(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> str:
        """Route to the correct provider."""
        if self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt, json_mode)
        elif self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt, json_mode)
        elif self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt, json_mode)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    # ── Gemini ─────────────────────────────────────────────────────

    def _call_gemini(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> str:
        from google import genai

        client = genai.Client(api_key=self.api_key)

        config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if json_mode:
            config["response_mime_type"] = "application/json"
        if system_prompt:
            config["system_instruction"] = system_prompt

        response = client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=config,
        )
        return response.text or ""

    # ── Anthropic ──────────────────────────────────────────────────

    def _call_anthropic(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        prompt = user_prompt
        if json_mode:
            prompt += "\n\nRespond with valid JSON only. No markdown fences."

        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    # ── OpenAI ─────────────────────────────────────────────────────

    def _call_openai(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    # ── JSON parsing ───────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Parse JSON from LLM response, handling markdown fences."""
        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response is not valid JSON: {exc}\nRaw response:\n{text[:500]}"
            ) from exc


# ── Module-level singleton ─────────────────────────────────────


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create the singleton LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
