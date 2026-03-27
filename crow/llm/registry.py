"""Model registry — resolves model names to providers and API keys."""

from dataclasses import dataclass

from crow.config.settings import Settings


@dataclass
class ModelInfo:
    provider: str  # "anthropic" or "openai"
    model: str     # model name to pass to the API
    api_key: str   # resolved API key


# Model name prefix → provider
PROVIDER_PREFIXES = {
    "claude-": "anthropic",
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
}


def resolve_model(model_name: str, settings: Settings) -> ModelInfo:
    """Resolve a model name to provider + API key."""
    provider = _detect_provider(model_name)

    if provider == "anthropic":
        return ModelInfo(
            provider="anthropic",
            model=model_name,
            api_key=settings.anthropic_api_key,
        )
    elif provider == "openai":
        return ModelInfo(
            provider="openai",
            model=model_name,
            api_key=settings.openai_api_key,
        )
    else:
        # Default to anthropic
        return ModelInfo(
            provider="anthropic",
            model=model_name,
            api_key=settings.anthropic_api_key,
        )


def _detect_provider(model_name: str) -> str:
    for prefix, provider in PROVIDER_PREFIXES.items():
        if model_name.startswith(prefix):
            return provider
    return "anthropic"
