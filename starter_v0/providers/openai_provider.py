from __future__ import annotations

import json
import os
from typing import Any

from providers.base import ModelResponse, ToolCall


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=self.base_url)
            resp = client.chat.completions.create(**kwargs)
        except ImportError:
            # Fallback for environments where the `openai` SDK's `chat` submodule
            # cannot be imported (e.g. its native `jiter` extension is blocked by
            # a local Windows Application Control / WDAC policy — this raises
            # ImportError lazily, on first access to `client.chat`, not on
            # `from openai import OpenAI` itself). Calls the same OpenAI Chat
            # Completions HTTP endpoint directly with `requests`, so behavior is
            # otherwise identical to the SDK path above.
            return self._complete_via_http(api_key, kwargs)

        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)

    def _complete_via_http(self, api_key: str, kwargs: dict[str, Any]) -> ModelResponse:
        import requests

        resp = requests.post(
            (self.base_url or "https://api.openai.com/v1") + "/chat/completions",
            json=kwargs,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        calls: list[ToolCall] = []
        for call in msg.get("tool_calls") or []:
            args = json.loads(call["function"].get("arguments") or "{}")
            calls.append(ToolCall(name=call["function"]["name"], args=args))
        return ModelResponse(text=msg.get("content"), tool_calls=calls, raw=data)
