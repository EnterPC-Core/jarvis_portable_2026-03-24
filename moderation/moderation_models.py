from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class AntiAbuseScore:
    multiplier: float
    penalty: int
    flag: str = ""
    cooldown_remaining_seconds: int = 0


@dataclass(frozen=True)
class ModerationContext:
    chat_id: int
    user_id: int
    chat_type: str
    chat_title: str = ""
    message_id: Optional[int] = None
    text: str = ""
    recent_texts: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModerationAction:
    action: str
    reason: str
    public_reason: str
    duration_seconds: int = 0
    delete_message: bool = False
    add_warning: bool = False
    next_step: str = ""


@dataclass(frozen=True)
class ModerationDecision:
    code: str
    action: ModerationAction
    severity: str = "medium"
    score: Optional[AntiAbuseScore] = None


@dataclass(frozen=True)
class WarningRecord:
    chat_id: int
    user_id: int
    count: int
    reason: str
    expires_at: Optional[int] = None


@dataclass(frozen=True)
class SanctionRecord:
    chat_id: int
    user_id: int
    action: str
    reason: str
    points_delta: int
    expires_at: Optional[int] = None
    status: str = "active"


@dataclass(frozen=True)
class AppealRecord:
    appeal_id: int
    user_id: int
    status: str
    message: str
    source_action: str = ""


@dataclass(frozen=True)
class AppealDecision:
    appeal_id: int
    approved: bool
    resolution: str
    moderator_id: Optional[int] = None


@dataclass(frozen=True)
class ModerationDiagnostics:
    source: str
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModerationPolicy:
    warn_limit: int = 3
    appeal_cooldown_seconds: int = 6 * 3600
    duplicate_similarity_threshold: float = 0.96
    burst_window_seconds: int = 20


@dataclass(frozen=True)
class ModerationOutcome:
    decision: Optional[ModerationDecision]
    diagnostics: ModerationDiagnostics
    compatibility_used: bool = True
    legacy_auto_decision: object | None = None
