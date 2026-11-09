import os
from contextvars import ContextVar

import litellm
from cachetools import TTLCache

from app.core.config import (GATEWAY_CACHE_TTL, GATEWAY_RETRY_LIMIT,
                             MODEL_ANSWER, MODEL_CLASSIFY, MODEL_REASONING)
from app.core.logger import logger

# each tier falls back to the next-cheaper Groq model on rate limits, never to another provider
TIER_CHAINS = {
    "answer": [MODEL_ANSWER, MODEL_REASONING, MODEL_CLASSIFY],
    "reasoning": [MODEL_REASONING, MODEL_CLASSIFY],
    "classify": [MODEL_CLASSIFY],
}

_response_cache = TTLCache(maxsize=256, ttl=GATEWAY_CACHE_TTL)

PROVIDER_ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
DEFAULT_PROVIDER_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-5-5",
    "gemini": "gemini-3.8-flash",
}
_request_model_config = ContextVar("request_model_config", default=None)


def set_request_model_config(provider, model, api_key):
    """Apply user-selected provider credentials to this request only."""
    return _request_model_config.set({
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "user_key": bool(api_key),
    })


def reset_request_model_config(token):
    _request_model_config.reset(token)


class GatewayMessage:
    def __init__(self, content, model_used, fallback_used, degraded, tokens_used, finish_reason=None):
        self.content = content
        self.model_used = model_used
        self.fallback_used = fallback_used
        self.degraded = degraded
        self.finish_reason = finish_reason
        self.response_metadata = {"token_usage": {"total_tokens": tokens_used}}


def _call_model(provider, model_id, prompt, retries, api_key=None, generation_options=None):
    last_error = None
    for _ in range(retries + 1):
        try:
            return litellm.completion(
                model=f"{provider}/{model_id}",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                api_key=api_key,
                timeout=60,
                **(generation_options or {}),
            )
        except litellm.RateLimitError as e:
            raise e
        except Exception as e:
            last_error = e
    raise last_error


class Gateway:
    def __init__(self, tier):
        self.tier = tier

    def invoke(self, prompt, generation_options=None):
        request_config = _request_model_config.get()
        legacy_mode = request_config is None
        if request_config is None:
            provider = "groq"
            chain = TIER_CHAINS[self.tier]
            api_key = os.getenv(PROVIDER_ENV_KEYS[provider])
            user_key = False
        else:
            provider = request_config["provider"]
            model = request_config["model"] or DEFAULT_PROVIDER_MODELS[provider]
            chain = [model]
            api_key = request_config["api_key"] or os.getenv(PROVIDER_ENV_KEYS[provider])
            user_key = request_config["user_key"]

        if not api_key and not legacy_mode:
            return GatewayMessage(
                f"Add a {provider.title()} API key in Settings to use AI chat.",
                None, False, "provider_api_key_missing", 0
            )

        last_failure = None
        for i, model_id in enumerate(chain):
            try:
                options = {'generation_options': generation_options} if generation_options else {}
                response = _call_model(provider, model_id, prompt, retries=GATEWAY_RETRY_LIMIT, api_key=api_key, **options)
                tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
                content = response.choices[0].message.content
                cache_key = f"{provider}:{model_id}:{prompt}"
                if not user_key and not generation_options:
                    _response_cache[cache_key] = content
                model_used = model_id if legacy_mode else f"{provider}/{model_id}"
                return GatewayMessage(content, model_used, i > 0, None, tokens, getattr(response.choices[0], 'finish_reason', None))
            except litellm.RateLimitError:
                last_failure = "rate_limited"
                logger.info(f"model_gateway: {provider}/{model_id} rate limited, dropping a tier")
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                last_failure = "auth_rejected" if status_code in (401, 403) else (
                    "request_rejected" if status_code in (400, 404) else "provider_unavailable"
                )
                # Provider exceptions can contain request details. Never log the exception text,
                # because this request may be using a customer's API key.
                logger.error(f"model_gateway: {provider}/{model_id} failed ({type(e).__name__})")

        cache_key = f"{provider}:{chain[0]}:{prompt}"
        cached = None if user_key or generation_options else _response_cache.get(cache_key)
        if cached is not None:
            return GatewayMessage(cached, "cache", True, "model_gateway_cache_fallback", 0)

        failure_messages = {
            "auth_rejected": ("The provider rejected the API key. Check the key in AI Provider Settings.", "provider_auth_rejected"),
            "request_rejected": ("The provider rejected this model or request. Check the Model ID in AI Provider Settings.", "provider_request_rejected"),
            "rate_limited": ("The provider rate limit was reached. Wait a moment or check your provider plan.", "provider_rate_limited"),
            "provider_unavailable": ("The AI provider is unavailable right now. Check your key and try again.", "provider_unavailable"),
        }
        if last_failure:
            content, degraded = failure_messages[last_failure]
            return GatewayMessage(content, None, True, degraded, 0)

        return GatewayMessage(
            "I'm temporarily unable to reach the language model. Please try again shortly.",
            None, True, "model_gateway_exhausted", 0
        )


def get_llm(tier="answer"):
    return Gateway(tier)
