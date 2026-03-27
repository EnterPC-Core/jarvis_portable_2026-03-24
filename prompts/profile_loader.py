from __future__ import annotations

from prompts.runtime_profiles import LEGACY_PROFILE_ALIASES, RUNTIME_PROFILES, RuntimePromptProfile


def normalize_prompt_profile_name(raw_mode: str | None, default: str = "jarvis") -> str:
    candidate = (raw_mode or default).strip().lower()
    candidate = LEGACY_PROFILE_ALIASES.get(candidate, candidate)
    if candidate in RUNTIME_PROFILES:
        return candidate
    return default


def load_runtime_profile(raw_mode: str | None, default: str = "jarvis") -> RuntimePromptProfile:
    normalized = normalize_prompt_profile_name(raw_mode, default=default)
    return RUNTIME_PROFILES[normalized]
