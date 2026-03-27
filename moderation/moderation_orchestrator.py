from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from moderation.anti_abuse import AntiAbuseAdapter
from moderation.appeals import AppealsAdapter
from moderation.moderation_models import (
    ModerationAction,
    ModerationContext,
    ModerationDecision,
    ModerationDiagnostics,
    ModerationOutcome,
    ModerationPolicy,
)
from moderation.modlog import ModlogAdapter
from moderation.policy import ModerationTextPolicy
from moderation.sanctions import SanctionsAdapter
from moderation.warnings import WarningAdapter
from services.auto_moderation import AutoModerationDecision, detect_auto_moderation_decision


@dataclass
class ModerationOrchestrator:
    anti_abuse: AntiAbuseAdapter
    sanctions: SanctionsAdapter
    warnings: WarningAdapter
    appeals: AppealsAdapter
    modlog: ModlogAdapter
    text_policy: ModerationTextPolicy
    policy: ModerationPolicy
    contains_profanity_func: Callable[[str], bool]

    def detect_auto_moderation(
        self,
        *,
        context: ModerationContext,
        message: dict,
        bot_username: str,
        trigger_name: str,
    ) -> ModerationOutcome:
        legacy_decision = detect_auto_moderation_decision(
            message=message,
            raw_text=context.text,
            recent_texts=list(context.recent_texts),
            chat_title=context.chat_title,
            bot_username=bot_username,
            trigger_name=trigger_name,
            contains_profanity_func=self.contains_profanity_func,
        )
        if legacy_decision is None:
            return ModerationOutcome(
                decision=None,
                diagnostics=ModerationDiagnostics(source="auto_moderation", notes=("no_trigger",)),
                compatibility_used=True,
            )
        score = self.anti_abuse.analyze_message(context.text, [], None)
        action = ModerationAction(
            action=legacy_decision.action,
            reason=legacy_decision.reason,
            public_reason=legacy_decision.public_reason,
            duration_seconds=max(int(legacy_decision.mute_seconds or 0), int(legacy_decision.ban_seconds or 0)),
            delete_message=bool(legacy_decision.delete_message),
            add_warning=bool(legacy_decision.add_warning),
            next_step=legacy_decision.suggested_owner_action or "",
        )
        decision = ModerationDecision(
            code=legacy_decision.code,
            action=action,
            severity=legacy_decision.severity,
            score=score,
        )
        return ModerationOutcome(
            decision=decision,
            diagnostics=ModerationDiagnostics(source="auto_moderation", notes=(legacy_decision.code,)),
            compatibility_used=True,
            legacy_auto_decision=legacy_decision,
        )

    def legacy_auto_decision(self, outcome: ModerationOutcome) -> Optional[AutoModerationDecision]:
        payload = outcome.legacy_auto_decision
        return payload if isinstance(payload, AutoModerationDecision) else None
