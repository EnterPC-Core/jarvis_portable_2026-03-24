from __future__ import annotations

from dataclasses import dataclass

from prompts.enterprise import ENTERPRISE_PROMPT
from prompts.jarvis import JARVIS_PROMPT


@dataclass(frozen=True)
class RuntimePromptProfile:
    name: str
    system_prompt: str
    identity_label: str


RUNTIME_PROFILES = {
    "jarvis": RuntimePromptProfile(
        name="jarvis",
        system_prompt=JARVIS_PROMPT,
        identity_label="Jarvis",
    ),
    "enterprise": RuntimePromptProfile(
        name="enterprise",
        system_prompt=ENTERPRISE_PROMPT,
        identity_label="Enterprise",
    ),
}

LEGACY_PROFILE_ALIASES = {
    "chat": "jarvis",
    "code": "jarvis",
    "strict": "jarvis",
}
