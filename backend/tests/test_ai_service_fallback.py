"""
Tests for AIService._generate_with_fallback -- the consolidated
fallback-between-providers primitive used by every AI-generation method in
ai_service.py (and by LeagueManagementService).

These use mocked SDK clients (no real network calls / API keys required) so
they can run in CI. The rate-limit tests build real openai.RateLimitError /
anthropic.RateLimitError instances with the same shape the SDKs raise on a
genuine 429, so the assertions exercise the actual isinstance() checks in
_generate_with_fallback rather than a generic Exception.
"""

import httpx
import openai
import anthropic
import pytest
from unittest.mock import AsyncMock

from app.services.ai_service import AIService, AIProvider


def _rate_limit_error(sdk_module, message: str = "Rate limit reached"):
    """Build a real RateLimitError with a genuine 429 httpx.Response, the
    same shape the openai/anthropic SDKs raise when a request is actually
    rate-limited."""
    request = httpx.Request("POST", "https://api.example.com/v1/messages")
    response = httpx.Response(status_code=429, request=request, json={"error": {"message": message}})
    return sdk_module.RateLimitError(message, response=response, body=None)


def _make_chat_completion(text: str):
    """Minimal stand-in for an OpenAI ChatCompletion response."""
    message = type("Message", (), {"content": text})()
    choice = type("Choice", (), {"message": message})()
    return type("ChatCompletion", (), {"choices": [choice]})()


def _make_anthropic_message(text: str):
    """Minimal stand-in for an Anthropic Message response."""
    block = type("TextBlock", (), {"text": text})()
    return type("Message", (), {"content": [block]})()


@pytest.fixture
def service() -> AIService:
    """An AIService with both provider clients mocked out -- bypasses
    __init__'s real client construction (and the need for real API keys) by
    building the instance then attaching AsyncMock clients directly."""
    svc = AIService.__new__(AIService)
    svc.openai_client = AsyncMock()
    svc.anthropic_client = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_rate_limit_on_primary_falls_back_to_secondary(service: AIService):
    """A 429 from the primary provider should trigger an immediate fallback
    to the secondary, whose successful result is returned -- not the
    failure sentinel."""
    service.openai_client.chat.completions.create.side_effect = _rate_limit_error(openai)
    service.anthropic_client.messages.create.return_value = _make_anthropic_message("fallback analysis text")

    result = await service._generate_with_fallback("prompt", primary=AIProvider.OPENAI)

    assert result == "fallback analysis text"
    assert not result.startswith(AIService.FAILURE_PREFIX)
    service.openai_client.chat.completions.create.assert_awaited_once()
    service.anthropic_client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_on_anthropic_primary_falls_back_to_openai(service: AIService):
    """Same as above with the providers swapped, to prove the rate-limit
    detection isn't hardcoded to a single provider."""
    service.anthropic_client.messages.create.side_effect = _rate_limit_error(anthropic)
    service.openai_client.chat.completions.create.return_value = _make_chat_completion("openai fallback text")

    result = await service._generate_with_fallback("prompt", primary=AIProvider.ANTHROPIC)

    assert result == "openai fallback text"
    assert not result.startswith(AIService.FAILURE_PREFIX)


@pytest.mark.asyncio
async def test_non_rate_limit_error_also_falls_back(service: AIService):
    """A non-rate-limit failure (auth, network, malformed response, ...)
    should still fall back -- matching the app's prior broad-except
    behavior, just centralized."""
    service.openai_client.chat.completions.create.side_effect = openai.AuthenticationError(
        "Incorrect API key",
        response=httpx.Response(
            status_code=401,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        ),
        body=None,
    )
    service.anthropic_client.messages.create.return_value = _make_anthropic_message("fallback after auth failure")

    result = await service._generate_with_fallback("prompt", primary=AIProvider.OPENAI)

    assert result == "fallback after auth failure"


@pytest.mark.asyncio
async def test_both_providers_fail_returns_honest_combined_error(service: AIService):
    """When every configured provider genuinely fails, the caller gets a
    single honest error string naming both providers and why each failed --
    never a fabricated success, and never silently losing one of the two
    failure reasons."""
    service.openai_client.chat.completions.create.side_effect = _rate_limit_error(openai, "openai limit hit")
    service.anthropic_client.messages.create.side_effect = RuntimeError("anthropic is down")

    result = await service._generate_with_fallback("prompt", primary=AIProvider.OPENAI)

    assert result.startswith(AIService.FAILURE_PREFIX)
    assert "openai" in result and "rate-limited" in result
    assert "anthropic" in result and "anthropic is down" in result


@pytest.mark.asyncio
async def test_unconfigured_secondary_is_reported_not_silently_skipped(service: AIService):
    """If the secondary provider was never configured (no client), that is
    distinguishable in the combined error from an actual API failure."""
    service.anthropic_client = None
    service.openai_client.chat.completions.create.side_effect = _rate_limit_error(openai)

    result = await service._generate_with_fallback("prompt", primary=AIProvider.OPENAI)

    assert result.startswith(AIService.FAILURE_PREFIX)
    assert "anthropic: not configured" in result


@pytest.mark.asyncio
async def test_fast_vs_deep_model_tier_selection(service: AIService):
    """prefer_fast_model must route to the FAST_* constants; the default
    must route to the DEEP_* constants -- this is the model-selection half
    of the consolidation, not just the fallback half."""
    service.openai_client.chat.completions.create.return_value = _make_chat_completion("ok")

    await service._generate_with_fallback("prompt", prefer_fast_model=True)
    fast_kwargs = service.openai_client.chat.completions.create.call_args.kwargs
    assert fast_kwargs["model"] == AIService.FAST_OPENAI_MODEL

    service.openai_client.chat.completions.create.reset_mock()
    await service._generate_with_fallback("prompt", prefer_fast_model=False)
    deep_kwargs = service.openai_client.chat.completions.create.call_args.kwargs
    assert deep_kwargs["model"] == AIService.DEEP_OPENAI_MODEL


@pytest.mark.asyncio
async def test_openai_request_omits_unsupported_gpt5_params(service: AIService):
    """GPT-5-family models reject `temperature` and `max_tokens` outright
    (confirmed live against the real API while building this) -- lock in
    that the request never regresses to sending them."""
    service.openai_client.chat.completions.create.return_value = _make_chat_completion("ok")

    await service._generate_with_fallback("prompt")

    kwargs = service.openai_client.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "max_tokens" not in kwargs
    assert "max_completion_tokens" in kwargs


@pytest.mark.asyncio
async def test_anthropic_request_omits_unsupported_temperature(service: AIService):
    """Current-generation Claude models (and the SDK itself, as of the
    version pinned in requirements.txt) reject `temperature` -- lock in
    that the request never regresses to sending it."""
    service.openai_client = None
    service.anthropic_client.messages.create.return_value = _make_anthropic_message("ok")

    await service._generate_with_fallback("prompt", primary=AIProvider.ANTHROPIC)

    kwargs = service.anthropic_client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
