"""LLM client wrapping the Anthropic SDK.

Adapted from TrendingHunter pattern with async support.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

import anthropic

from storyteller.log import get_logger

_T = TypeVar("_T")
log = get_logger("llm")

_RETRYABLE = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APITimeoutError)


def _parse_sections(text: str) -> dict[str, str]:
    """Parse markdown ## headers into sections."""
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return {"content": text.strip()}
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _retry_call(fn: Callable[[], _T], max_retries: int = 3) -> _T:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                log.warning("Retry %d/%d after %ds: %s", attempt + 1, max_retries, delay, exc)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def create_client_from_config(config) -> LLMClient:
    """Create LLMClient from an LLMConfig instance."""
    return LLMClient(
        model=config.model,
        max_tokens=config.max_tokens,
        api_key=config.api_key,
        base_url=config.base_url,
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling code blocks."""
    text = text.strip()
    # Remove code block markers
    if "```" in text:
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON found in response ({len(text)} chars)")


class LLMClient:
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
        timeout: float = 120.0,
        api_key: str = "",
        base_url: str = "",
    ) -> None:
        kwargs: dict[str, object] = {"timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            # Strip trailing /v1/messages if user accidentally included it
            base_url = re.sub(r"/v1/messages/?$", "", base_url.rstrip("/"))
            kwargs["base_url"] = base_url
        # Prevent SDK from using ANTHROPIC_AUTH_TOKEN env var as Bearer token
        _saved_auth = os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        try:
            self._client = anthropic.Anthropic(**kwargs)
        finally:
            if _saved_auth is not None:
                os.environ["ANTHROPIC_AUTH_TOKEN"] = _saved_auth
        self._model = model
        self._max_tokens = max_tokens
        _key = self._client.api_key or ""
        log.info("LLMClient init: model=%s base_url=%s api_key=...%s",
                 model, getattr(self._client, "base_url", ""), _key[-4:] if _key else "(empty)")

    @property
    def model(self) -> str:
        return self._model

    def call(self, system: str, user: str) -> str:
        """Simple text call, returns raw text."""
        log.info("LLM call: model=%s", self._model)

        def _do_call() -> object:
            return self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

        response = _retry_call(_do_call)
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        log.info(
            "LLM response: input=%d output=%d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return text

    def call_json(self, system: str, user: str) -> dict[str, Any]:
        """Call and parse JSON from response. Handles code blocks and partial output."""
        log.info("LLM call_json: model=%s", self._model)
        text = self.call(system, user)
        return _extract_json(text)

    def call_structured(self, system: str, user: str) -> tuple[dict[str, str], dict[str, int]]:
        """Call and parse into sections."""
        log.info("LLM call_structured: model=%s", self._model)

        def _do_call() -> object:
            return self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

        response = _retry_call(_do_call)
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        sections = _parse_sections(text)
        tokens = {
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
        }
        log.info("LLM response: input=%d output=%d", tokens["input"], tokens["output"])
        return sections, tokens

    def call_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict[str, Any]], str],
        max_rounds: int = 5,
    ) -> str:
        """Agentic tool-use loop, returns final text."""
        log.info("LLM call_with_tools: model=%s tools=%s", self._model, [t["name"] for t in tools])

        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        total_input = 0
        total_output = 0

        for round_num in range(max_rounds):
            log.debug("Tool round %d/%d", round_num + 1, max_rounds)

            def _do_call() -> object:
                return self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system,
                    messages=messages,
                    tools=tools,
                )

            response = _retry_call(_do_call)
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            if response.stop_reason == "end_turn":
                text = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                log.info(
                    "LLM done: input=%d output=%d rounds=%d",
                    total_input, total_output, round_num + 1,
                )
                return text

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    log.info("Tool call: %s(%s)", block.name, block.input)
                    result = tool_handler(block.name, block.input)
                    log.debug("Tool result length: %d chars", len(result))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Exhausted rounds, force final response
        log.warning("Tool loop exhausted after %d rounds", max_rounds)
        messages.append({
            "role": "user",
            "content": "Stop using tools. Write the final response now based on everything you've gathered.",
        })

        def _do_final() -> object:
            return self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            )

        final_response = _retry_call(_do_final)
        total_input += final_response.usage.input_tokens
        total_output += final_response.usage.output_tokens

        text = "".join(
            block.text for block in final_response.content if hasattr(block, "text")
        )
        log.info("LLM final: input=%d output=%d", total_input, total_output)
        return text
