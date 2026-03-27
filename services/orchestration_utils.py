from typing import Any, Callable, List, Sequence


def validate_route_decision(decision: Any, allowed_route_kinds: Sequence[str]) -> None:
    if decision.route_kind not in allowed_route_kinds:
        raise ValueError(f"unsupported route_kind: {decision.route_kind}")
    if decision.use_live != decision.route_kind.startswith("live_"):
        raise ValueError(f"route/live contract mismatch: {decision.route_kind}")
    if decision.use_workspace != (decision.route_kind == "codex_workspace"):
        raise ValueError(f"route/workspace contract mismatch: {decision.route_kind}")
    if decision.use_web and decision.use_live:
        raise ValueError(f"route/web+live contract mismatch: {decision.route_kind}")
    if "runtime-verification" in decision.guardrails and decision.use_web:
        raise ValueError(f"route/runtime+web contract mismatch: {decision.route_kind}")
    if not (decision.source_label or "").strip():
        raise ValueError(f"empty source_label: {decision.route_kind}")


def build_route_summary_text(route_info: Any) -> str:
    active_layers: List[str] = []
    if route_info.use_reply:
        active_layers.append("reply-context")
    if route_info.use_events:
        active_layers.append("event-context")
    if route_info.use_database:
        active_layers.append("database-context")
    if route_info.use_web:
        active_layers.append("web-context")
    if route_info.use_live:
        active_layers.append(f"live:{route_info.route_kind.replace('live_', '')}")
    if "runtime-verification" in route_info.guardrails:
        active_layers.append("runtime-check")
    if not active_layers:
        active_layers.append("history+summary+facts")
    return (
        f"intent={route_info.intent}; persona={route_info.persona}; "
        f"chat_type={route_info.chat_type}; "
        f"route={route_info.route_kind}; "
        f"workspace_mode={'yes' if route_info.use_workspace else 'no'}; "
        f"active_layers={', '.join(active_layers)}; "
        f"guardrails={', '.join(route_info.guardrails[:8])}"
    )


def build_guardrail_note(route_info: Any) -> str:
    lines = [
        "- перед финальным ответом проверь, что ответ опирается только на доступные контекстные слои и источники",
        "- не заявляй о выполненных действиях, если действие не было реально выполнено маршрутом или инструментом",
        "- различай observed / inferred / uncertain и не скрывай, где был только вывод, а не прямое наблюдение",
        "- не описывай внутренние переживания, сознание или эмоции как реальное состояние системы",
    ]
    if "respect-enterprise-mode" in route_info.guardrails:
        lines.append("- если пользователь зовёт Enterprise, держи инженерный режим ответа и не сваливайся в общий бытовой тон Jarvis")
    if route_info.use_live or route_info.use_web:
        lines.append("- если данные могли устареть или не подтверждаются уверенно, прямо скажи это")
        lines.append("- не выдавай косвенные сниппеты за окончательно подтверждённый факт")
    if "cite-source" in route_info.guardrails:
        lines.append("- для live-data запросов обязательно оставляй явный маркер источника и свежести ответа")
    if route_info.use_events or route_info.use_database or route_info.use_reply:
        lines.append("- не придумывай детали вне chat history, memory facts, reply context, archived events и database context")
    if "runtime-verification" in route_info.guardrails:
        lines.append("- для RAM, CPU, диска, uptime и других метрик среды опирайся только на реальную runtime-проверку; если её не было, честно скажи, что состояние не подтверждено")
        lines.append("- не подменяй проверку среды общими рассуждениями, устаревшими примерами или советом выполнить команду так, будто ответ уже подтверждён")
    if "heightened-uncertainty" in route_info.guardrails:
        lines.append("- в этом ответе системная неопределённость повышена: держи формулировки консервативными и не сглаживай uncertainty")
    if "runtime-risk-attention" in route_info.guardrails:
        lines.append("- сейчас повышен runtime-risk: если не хватает прямого подтверждения, лучше честно ограничить вывод и сослаться на observed state")
    if "doc-sync-attention" in route_info.guardrails:
        lines.append("- есть сигнал doc/runtime drift: не делай вид, что документация точно соответствует состоянию без проверки")
    if "stale-memory-attention" in route_info.guardrails:
        lines.append("- локальная память могла устареть: приоритет у свежих events и recent relation context")
    lines.append("- если ограничение реально мешает выполнить запрос, коротко обозначь его и сразу предложи следующий рабочий шаг")
    return "\n".join(lines)


def classify_answer_outcome(answer: str) -> str:
    lowered = (answer or "").lower()
    if not lowered:
        return "empty"
    if "не удалось" in lowered or "ошибка" in lowered or "выключен" in lowered:
        return "error"
    if "не подтверж" in lowered or "не уверен" in lowered or "предполож" in lowered:
        return "uncertain"
    return "ok"


def has_freshness_marker(text: str, freshness_markers: Sequence[str]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in freshness_markers)


def apply_self_check_contract(
    answer: str,
    route_decision: Any,
    *,
    normalize_whitespace_func: Callable[[str], str],
    freshness_markers: Sequence[str],
    has_freshness_marker_func: Callable[[str, Sequence[str]], bool],
    classify_answer_outcome_func: Callable[[str], str],
    self_check_factory: Callable[..., Any],
) -> Any:
    cleaned = normalize_whitespace_func(answer)
    flags: List[str] = []
    final_answer = cleaned
    observed_basis: List[str] = []
    uncertain_points: List[str] = []
    if not cleaned:
        return self_check_factory(
            outcome="empty",
            answer="Пустой ответ. Переформулируй запрос.",
            flags=("empty-answer",),
            observed_basis=(),
            uncertain_points=("empty-answer",),
        )

    if route_decision.use_live or route_decision.use_web:
        observed_basis.append("external-sources")
        lowered = cleaned.lower()
        if "источник:" not in lowered and "http" not in lowered:
            final_answer = final_answer + f"\n\nИсточник: {route_decision.source_label}."
            flags.append("added-source-marker")
            lowered = final_answer.lower()
        if route_decision.use_live and not has_freshness_marker_func(lowered, freshness_markers):
            final_answer = final_answer + "\nАктуальность: live-проверка на момент запроса."
            flags.append("added-freshness-marker")
            lowered = final_answer.lower()
        if route_decision.route_kind == "live_current_fact" and "подтверждение:" not in lowered and "не подтверж" not in lowered:
            final_answer = final_answer + "\n\nПроверка: это вывод по найденным внешним источникам, а не абсолютная гарантия факта."
            flags.append("added-current-fact-disclaimer")
            uncertain_points.append("current-fact-is-inferred")
            lowered = final_answer.lower()

    if "no-system-actions" in route_decision.guardrails and route_decision.persona != "enterprise":
        lowered = final_answer.lower()
        action_markers = ("создал", "удалил", "установил", "запустил", "перезапустил", "выполнил")
        if any(marker in lowered for marker in action_markers):
            final_answer += "\n\nПроверка: этот маршрут не подтверждает выполнение системных действий."
            flags.append("added-no-action-disclaimer")
            uncertain_points.append("action-claim-without-tool-proof")

    if "runtime-verification" in route_decision.guardrails and not route_decision.use_workspace:
        lowered = final_answer.lower()
        if all(marker not in lowered for marker in ("не подтверж", "не удалось", "ограничен", "недоступ", "нельзя проверить")):
            final_answer += "\n\nПроверка: этот маршрут не подтверждает реальные метрики среды. Для точных RAM/CPU/disk/uptime данных нужен runtime/workspace маршрут."
            flags.append("added-runtime-verification-disclaimer")
            uncertain_points.append("runtime-not-verified")
    if route_decision.use_workspace:
        observed_basis.append("workspace-runtime")
    if route_decision.use_events or route_decision.use_database or route_decision.use_reply:
        observed_basis.append("local-memory")
    if "heightened-uncertainty" in route_decision.guardrails:
        uncertain_points.append("system-uncertainty-pressure-high")
    if "runtime-risk-attention" in route_decision.guardrails:
        uncertain_points.append("runtime-risk-pressure-high")

    return self_check_factory(
        outcome=classify_answer_outcome_func(final_answer),
        answer=final_answer,
        flags=tuple(flags),
        observed_basis=tuple(dict.fromkeys(observed_basis)),
        uncertain_points=tuple(dict.fromkeys(uncertain_points)),
    )
