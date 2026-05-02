from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderOption:
    label: str
    provider: str
    default_model: str
    api_key_env: str | None = None
    api_key_prompt: str = ""
    base_url: str = ""
    openai_compatible: bool = False
    editable_base_url: bool = False
    api_key_optional: bool = False


PROVIDER_OPTIONS: dict[str, ProviderOption] = {
    "openrouter": ProviderOption(
        label="OpenRouter",
        provider="openrouter",
        default_model="openrouter/free",
        api_key_env="OPENROUTER_API_KEY",
        api_key_prompt="OpenRouter API key",
    ),
    "gemini": ProviderOption(
        label="Gemini",
        provider="gemini",
        default_model="gemini-1.5-flash",
        api_key_env="GEMINI_API_KEY",
        api_key_prompt="Gemini API key",
    ),
    "openai": ProviderOption(
        label="OpenAI",
        provider="openai",
        default_model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        api_key_prompt="OpenAI API key",
        base_url="https://api.openai.com/v1",
        openai_compatible=True,
    ),
    "groq": ProviderOption(
        label="Groq",
        provider="groq",
        default_model="llama-3.1-8b-instant",
        api_key_env="GROQ_API_KEY",
        api_key_prompt="Groq API key",
        base_url="https://api.groq.com/openai/v1",
        openai_compatible=True,
    ),
    "together": ProviderOption(
        label="Together AI",
        provider="together",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        api_key_env="TOGETHER_API_KEY",
        api_key_prompt="Together API key",
        base_url="https://api.together.xyz/v1",
        openai_compatible=True,
    ),
    "deepinfra": ProviderOption(
        label="DeepInfra",
        provider="deepinfra",
        default_model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        api_key_env="DEEPINFRA_API_KEY",
        api_key_prompt="DeepInfra API key",
        base_url="https://api.deepinfra.com/v1/openai",
        openai_compatible=True,
    ),
    "fireworks": ProviderOption(
        label="Fireworks AI",
        provider="fireworks",
        default_model="accounts/fireworks/models/llama-v3p1-8b-instruct",
        api_key_env="FIREWORKS_API_KEY",
        api_key_prompt="Fireworks API key",
        base_url="https://api.fireworks.ai/inference/v1",
        openai_compatible=True,
    ),
    "mistral": ProviderOption(
        label="Mistral AI",
        provider="mistral",
        default_model="mistral-small-latest",
        api_key_env="MISTRAL_API_KEY",
        api_key_prompt="Mistral API key",
        base_url="https://api.mistral.ai/v1",
        openai_compatible=True,
    ),
    "xai": ProviderOption(
        label="xAI",
        provider="xai",
        default_model="grok-3-mini",
        api_key_env="XAI_API_KEY",
        api_key_prompt="xAI API key",
        base_url="https://api.x.ai/v1",
        openai_compatible=True,
    ),
    "perplexity": ProviderOption(
        label="Perplexity",
        provider="perplexity",
        default_model="sonar",
        api_key_env="PERPLEXITY_API_KEY",
        api_key_prompt="Perplexity API key",
        base_url="https://api.perplexity.ai",
        openai_compatible=True,
    ),
    "deepseek": ProviderOption(
        label="DeepSeek",
        provider="deepseek",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        api_key_prompt="DeepSeek API key",
        base_url="https://api.deepseek.com",
        openai_compatible=True,
    ),
    "cerebras": ProviderOption(
        label="Cerebras",
        provider="cerebras",
        default_model="llama-3.3-70b",
        api_key_env="CEREBRAS_API_KEY",
        api_key_prompt="Cerebras API key",
        base_url="https://api.cerebras.ai/v1",
        openai_compatible=True,
    ),
    "openai_compatible": ProviderOption(
        label="OpenAI-compatible local",
        provider="openai_compatible",
        default_model="local-model",
        api_key_env="OPENAI_API_KEY",
        api_key_prompt="API key local/OpenAI-compatible (boleh kosong)",
        base_url="http://127.0.0.1:1234/v1",
        openai_compatible=True,
        editable_base_url=True,
        api_key_optional=True,
    ),
    "custom": ProviderOption(
        label="Custom OpenAI-compatible",
        provider="custom",
        default_model="custom-model",
        api_key_env="CUSTOM_PROVIDER_API_KEY",
        api_key_prompt="API key custom provider (boleh kosong jika endpoint tidak perlu)",
        base_url="https://api.example.com/v1",
        openai_compatible=True,
        editable_base_url=True,
        api_key_optional=True,
    ),
}

PROVIDER_ALIASES = {
    "openai-compatible": "openai_compatible",
    "local": "openai_compatible",
    "custom_openai_compatible": "custom",
    "custom-openai-compatible": "custom",
}

PROVIDER_LABELS = [option.label for option in PROVIDER_OPTIONS.values()]
OPENAI_COMPATIBLE_PROVIDERS = {
    provider for provider, option in PROVIDER_OPTIONS.items() if option.openai_compatible
}

OPENROUTER_FALLBACK_MODEL_CHOICES: tuple[tuple[str, str], ...] = (
    ("OpenRouter Free Router", "openrouter/free"),
    ("OpenRouter Auto Router", "openrouter/auto"),
    ("Qwen: Qwen3 Coder 480B A35B (free)", "qwen/qwen3-coder:free"),
    ("OpenAI: gpt-oss-120b (free)", "openai/gpt-oss-120b:free"),
    ("OpenAI: gpt-oss-20b (free)", "openai/gpt-oss-20b:free"),
    ("Meta: Llama 3.3 70B Instruct (free)", "meta-llama/llama-3.3-70b-instruct:free"),
    ("Google: Gemini 2.5 Flash", "google/gemini-2.5-flash"),
    ("OpenAI: GPT-5 Mini", "openai/gpt-5-mini"),
    ("OpenAI: GPT-4o-mini", "openai/gpt-4o-mini"),
    ("Anthropic: Claude Haiku 4.5", "anthropic/claude-haiku-4.5"),
    ("Meta: Llama 4 Maverick", "meta-llama/llama-4-maverick"),
    ("DeepSeek: DeepSeek V3.2", "deepseek/deepseek-v3.2"),
    ("DeepSeek: R1", "deepseek/deepseek-r1"),
    ("Qwen: Qwen3 235B A22B Instruct 2507", "qwen/qwen3-235b-a22b-2507"),
    ("xAI: Grok 4.1 Fast", "x-ai/grok-4.1-fast"),
    ("Mistral: Mistral Large 3 2512", "mistralai/mistral-large-2512"),
    ("MoonshotAI: Kimi K2 0711", "moonshotai/kimi-k2"),
    ("Perplexity: Sonar", "perplexity/sonar"),
)

OPENROUTER_CURATED_MODEL_IDS: tuple[str, ...] = (
    "openrouter/free",
    "openrouter/auto",
    "qwen/qwen3-coder:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.0-flash-001",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-3-haiku",
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "qwen/qwen3-235b-a22b-2507",
    "qwen/qwen3-coder",
    "qwen/qwen3-vl-235b-a22b-instruct",
    "x-ai/grok-4.1-fast",
    "x-ai/grok-4-fast",
    "x-ai/grok-code-fast-1",
    "mistralai/mistral-large-2512",
    "mistralai/mistral-small-3.2-24b-instruct",
    "mistralai/codestral-2508",
    "moonshotai/kimi-k2",
    "perplexity/sonar",
    "openai/gpt-5.4",
    "~anthropic/claude-sonnet-latest",
    "~google/gemini-pro-latest",
)

OPENROUTER_FLAGSHIP_MODEL_IDS = {
    "openai/gpt-5.4",
    "~anthropic/claude-sonnet-latest",
    "~google/gemini-pro-latest",
}


def normalize_provider_name(provider: str) -> str:
    value = provider.strip().lower()
    return PROVIDER_ALIASES.get(value, value)


def get_provider_option(provider: str) -> ProviderOption:
    normalized = normalize_provider_name(provider)
    try:
        return PROVIDER_OPTIONS[normalized]
    except KeyError as exc:
        raise ValueError(f"Provider tidak dikenal: {provider}") from exc


def provider_from_label(label: str) -> str:
    for provider, option in PROVIDER_OPTIONS.items():
        if option.label == label:
            return provider
    return "openrouter"
