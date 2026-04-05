from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMConfigError(RuntimeError):
    """Raised when the topic generation LLM is not configured."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM returns an invalid or unusable response."""


class TopicGenerationLLM(Protocol):
    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class OpenAICompatibleTopicLLM:
    """Simple JSON-only client for OpenAI-compatible chat APIs."""

    api_key: str
    model: str
    base_url: str
    timeout_seconds: int = 90
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "OpenAICompatibleTopicLLM":
        api_key = os.getenv("AGENT_ARENA_LLM_API_KEY", "").strip()
        model = os.getenv("AGENT_ARENA_LLM_MODEL", "").strip()
        base_url = os.getenv(
            "AGENT_ARENA_LLM_BASE_URL",
            "https://api.openai.com/v1",
        ).rstrip("/")
        timeout_seconds = int(os.getenv("AGENT_ARENA_LLM_TIMEOUT_SECONDS", "90"))
        temperature = float(os.getenv("AGENT_ARENA_LLM_TEMPERATURE", "0.2"))

        if not api_key:
            raise LLMConfigError("Missing AGENT_ARENA_LLM_API_KEY.")
        if not model:
            raise LLMConfigError("Missing AGENT_ARENA_LLM_MODEL.")

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        system_prompt
                        + "\n\nReturn JSON only. Do not wrap the answer in markdown."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        }
        request = Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMResponseError(
                f"{schema_name} request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise LLMResponseError(
                f"{schema_name} request could not reach the configured LLM endpoint."
            ) from exc

        parsed = json.loads(raw_payload)
        text = _extract_message_text(parsed)
        try:
            return json.loads(_extract_json_object(text))
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"{schema_name} response did not contain valid JSON."
            ) from exc


def _extract_message_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("LLM response did not include choices.")

    message = choices[0].get("message", {})
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)

    raise LLMResponseError("LLM response did not include text content.")


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMResponseError("LLM response did not include a JSON object.")
    return text[start : end + 1]
