from __future__ import annotations

from dataclasses import dataclass

from moderation.moderation_models import ModerationAction, ModerationPolicy


@dataclass(frozen=True)
class ModerationTextPolicy:
    """Short formal moderator-facing phrasing."""

    def format_public_notice(self, target_label: str, action: ModerationAction) -> str:
        base = f"JARVIS: {target_label} — {action.public_reason}."
        if action.action == "warn":
            return f"{base} Выдано предупреждение."
        if action.action == "mute":
            duration = f" Срок: {self._format_duration(action.duration_seconds)}." if action.duration_seconds > 0 else ""
            return f"{base} Выдан мут.{duration}"
        if action.action == "ban":
            duration = f" Срок: {self._format_duration(action.duration_seconds)}." if action.duration_seconds > 0 else ""
            return f"{base} Выдан бан.{duration}"
        return base

    def warn_escalation_action(self, warning_count: int, policy: ModerationPolicy) -> str:
        return "mute" if warning_count >= max(1, policy.warn_limit) else "warn"

    def _format_duration(self, seconds: int) -> str:
        if seconds <= 0:
            return "без срока"
        minutes = max(1, seconds // 60)
        if minutes < 60:
            return f"{minutes} мин"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} ч"
        return f"{hours // 24} д"
