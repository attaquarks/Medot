"""Fetch the live model list from a provider (BYOK discovery).

One function, one branch per provider family. Raises ValueError with a
plain-language message the desktop can show as-is.
"""
from __future__ import annotations

import httpx

PROVIDERS = ("openai_compatible", "ollama", "anthropic", "google")

DEFAULT_BASES = {
    "openai_compatible": "https://api.openai.com/v1",
    "ollama": "http://127.0.0.1:11434",
    "anthropic": "https://api.anthropic.com",
    "google": "https://generativelanguage.googleapis.com",
}


def _fail(action: str, status: int) -> ValueError:
    if status in (401, 403):
        return ValueError(f"{action}: the key was rejected ({status}) — check it and try again")
    return ValueError(f"{action}: the provider answered {status} — check the URL")


async def discover_models(provider: str, base_url: str | None, api_key: str) -> list[str]:
    """Return the model ids/names a key can actually use, sorted."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    base = (base_url or "").rstrip("/") or DEFAULT_BASES[provider]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as http:
            if provider == "openai_compatible":
                response = await http.get(
                    f"{base}/models", headers={"Authorization": f"Bearer {api_key}"}
                )
                if response.status_code >= 400:
                    raise _fail("fetching models", response.status_code)
                items = response.json().get("data") or []
                models = [str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")]
            elif provider == "ollama":
                response = await http.get(f"{base}/api/tags")
                if response.status_code >= 400:
                    raise _fail("fetching models", response.status_code)
                items = response.json().get("models") or []
                models = [str(item["name"]) for item in items if isinstance(item, dict) and item.get("name")]
            elif provider == "anthropic":
                response = await http.get(
                    f"{base}/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
                if response.status_code >= 400:
                    raise _fail("fetching models", response.status_code)
                items = response.json().get("data") or []
                models = [str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")]
            else:  # google
                response = await http.get(f"{base}/v1beta/models", params={"key": api_key})
                if response.status_code >= 400:
                    raise _fail("fetching models", response.status_code)
                items = response.json().get("models") or []
                models = [
                    str(item["name"]).removeprefix("models/")
                    for item in items
                    if isinstance(item, dict) and item.get("name")
                ]
    except httpx.HTTPError as exc:
        raise ValueError(f"couldn't reach the provider at {base} ({type(exc).__name__}) — check the URL") from None
    return sorted(set(models))


# --- LiteLLM model-string mapping (the engine path, doc 11 §5) ----------------

def litellm_target(provider: str, model: str, api_base: str | None) -> tuple[str, str | None]:
    """(model_string, api_base) litellm.acompletion expects for this profile."""
    if provider == "openai_compatible":
        return f"openai/{model}", api_base or DEFAULT_BASES[provider]
    if provider == "ollama":
        return f"ollama_chat/{model}", api_base or DEFAULT_BASES[provider]
    if provider == "anthropic":
        return f"anthropic/{model}", None
    if provider == "google":
        return f"gemini/{model}", None
    raise ValueError(f"unknown provider {provider!r}")
