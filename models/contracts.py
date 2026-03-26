from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class RouteDecision:
    persona: str
    intent: str
    chat_type: str
    route_kind: str
    source_label: str
    use_live: bool
    use_web: bool
    use_events: bool
    use_database: bool
    use_reply: bool
    use_workspace: bool
    guardrails: Tuple[str, ...]
    request_kind: str = "chat"
    allowed_sources: Tuple[str, ...] = ()
    forbidden_sources: Tuple[str, ...] = ()
    required_tools: Tuple[str, ...] = ()
    answer_contract: str = ""


@dataclass(frozen=True)
class ContextBundle:
    summary_text: str = ""
    facts_text: str = ""
    event_context: str = ""
    database_context: str = ""
    reply_context: str = ""
    discussion_context: str = ""
    self_model_text: str = ""
    autobiographical_text: str = ""
    skill_memory_text: str = ""
    world_state_text: str = ""
    drive_state_text: str = ""
    user_memory_text: str = ""
    relation_memory_text: str = ""
    chat_memory_text: str = ""
    summary_memory_text: str = ""
    web_context: str = ""
    route_summary: str = ""
    guardrail_note: str = ""


@dataclass(frozen=True)
class SelfCheckReport:
    outcome: str
    answer: str
    flags: Tuple[str, ...]
    observed_basis: Tuple[str, ...] = ()
    uncertain_points: Tuple[str, ...] = ()
    mode: str = "insufficient"
    route: str = ""
    sources: Tuple[str, ...] = ()
    tools_used: Tuple[str, ...] = ()
    memory_used: Tuple[str, ...] = ()
    confidence: float = 0.0
    freshness: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ExternalResearchTask:
    kind: str
    label: str
    payload: str = ""


@dataclass(frozen=True)
class RequestRoutePolicy:
    request_kind: str
    allowed_sources: Tuple[str, ...]
    forbidden_sources: Tuple[str, ...]
    required_tools: Tuple[str, ...]
    refusal_condition: str
    answer_contract: str


@dataclass(frozen=True)
class LiveProviderRecord:
    provider: str
    category: str
    data: str = ""
    timestamp: int = 0
    freshness: str = ""
    status: str = "ok"
    reliability: float = 0.0
    normalized: bool = False


@dataclass(frozen=True)
class AttachmentBundle:
    attachment_type: str
    extracted_text: str = ""
    structured_features: str = ""
    source_message_link: str = ""
    relevance_score: float = 0.0
    used_in_response: bool = False


ROUTER_POLICY_MATRIX: Dict[str, RequestRoutePolicy] = {
    "chat": RequestRoutePolicy(
        request_kind="chat",
        allowed_sources=("chat_history", "chat_memory", "summary_memory"),
        forbidden_sources=("runtime_probe", "live_provider"),
        required_tools=(),
        refusal_condition="если вопрос требует свежих данных или runtime-проверки, нельзя отвечать как обычный chat",
        answer_contract="короткий conversational ответ без ложных claim'ов",
    ),
    "chat_local_context": RequestRoutePolicy(
        request_kind="chat_local_context",
        allowed_sources=("chat_events", "reply_context", "user_memory", "relation_memory", "chat_memory", "summary_memory"),
        forbidden_sources=("live_provider", "generic_web_search"),
        required_tools=("local_chat_context",),
        refusal_condition="если локальный контекст слабый или не подтверждён, вернуть insufficient",
        answer_contract="локальный chat-grounded ответ с явной опорой на память/события",
    ),
    "project": RequestRoutePolicy(
        request_kind="project",
        allowed_sources=("workspace", "project_files", "logs", "world_state"),
        forbidden_sources=("live_provider", "generic_web_search"),
        required_tools=("workspace_route",),
        refusal_condition="если workspace route недоступен, не имитировать analysis",
        answer_contract="инженерный ответ по проекту только из локального runtime/context",
    ),
    "runtime": RequestRoutePolicy(
        request_kind="runtime",
        allowed_sources=("runtime_probe", "world_state", "logs"),
        forbidden_sources=("generic_chat", "generic_web_search"),
        required_tools=("direct_runtime_probe",),
        refusal_condition="если local probe не выполнен, вернуть insufficient вместо пересказа модели",
        answer_contract="подтверждённый runtime-статус с probe/tool grounding",
    ),
    "live": RequestRoutePolicy(
        request_kind="live",
        allowed_sources=("live_provider",),
        forbidden_sources=("generic_chat_inference",),
        required_tools=("live_route",),
        refusal_condition="если provider stale/failed и fallback не помог, вернуть insufficient",
        answer_contract="свежий ответ со source и freshness",
    ),
    "owner_admin": RequestRoutePolicy(
        request_kind="owner_admin",
        allowed_sources=("owner_commands", "runtime_probe", "workspace", "diagnostics"),
        forbidden_sources=("unverified_claims",),
        required_tools=("owner_permission_check",),
        refusal_condition="если permission или tool route недоступен, отказать явно",
        answer_contract="строгий owner-ops ответ с operational trace",
    ),
}

