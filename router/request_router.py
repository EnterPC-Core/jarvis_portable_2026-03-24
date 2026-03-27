import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, List, Optional, Set, Tuple

from models.contracts import ROUTER_POLICY_MATRIX, RouteDecision


RUNTIME_QUERY_MARKERS = (
    "статус", "status", "runtime", "health", "процесс", "heartbeat", "лог", "логи",
    "cpu", "ram", "mem", "memory", "диск", "disk", "сеть", "network", "проц", "ресурс",
    "uptime", "перезапуск", "restart", "systemctl", "journal", "supervisor", "pid",
)
RUNTIME_EXPLICIT_MARKERS = (
    "проверка enterprise runtime",
    "runtime report",
    "runtime status",
    "status report",
    "проверь runtime",
    "проверь рантайм",
    "диагностика runtime",
    "диагностика рантайма",
    "проверка среды",
    "проверь среду",
    "покажи среду",
    "покажи рантайм",
    "сними runtime probe",
)
ROUTER_POLICY_LESSONS = (
    "do-not-claim-unverified-actions",
    "respect-route-contract",
    "prefer-local-evidence-when-available",
)


@dataclass(frozen=True)
class RouterRuntimeDeps:
    owner_user_id: int
    normalize_whitespace_func: Callable[[str], str]
    detect_news_query_func: Callable[[str], str]
    detect_current_fact_query_func: Callable[[str], str]
    detect_weather_location_func: Callable[[str], str]
    detect_currency_pair_func: Callable[[str], Optional[Tuple[str, str]]]
    detect_crypto_asset_func: Callable[[str], str]
    detect_stock_symbol_func: Callable[[str], str]
    can_owner_use_workspace_mode_func: Callable[[Optional[int], str, str], bool]
    is_dangerous_request_func: Callable[[str], bool]
    validate_route_decision_func: Callable[[RouteDecision, Set[str]], RouteDecision]


def detect_local_chat_query(user_text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(user_text).lower()
    if not lowered:
        return False
    chat_markers = (
        "этот чат", "наш чат", "в чате", "в группе", "здесь", "тут", "переписк",
        "контекст чата", "локальный контекст", "что тут происходит", "что происходит в чате",
        "кто тут", "кто здесь", "по нашему чату", "по этой переписке", "изучи чат",
        "изучи этот чат", "разбери чат", "роль в чате", "динамика", "участник", "участники",
    )
    return any(marker in lowered for marker in chat_markers)


def is_local_project_meta_request(user_text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(user_text).lower()
    if not lowered:
        return False
    primary_scope_markers = (
        "этот чат", "наш чат", "в чате", "по базе", "из базы", "локальный", "в проекте",
        "по проекту", "этот проект", "весь проект", "код", "логика", "роут", "маршрут",
        "контекст", "reply", "chat_id",
    )
    service_scope_markers = ("jarvis", "enterprise", "бот")
    local_evidence_markers = (
        "предупреждение", "warn", "санкц", "модера", "удалил сообщение", "сообщение удалено",
        "reply", "роут", "маршрут", "контекст", "логика", "chat_id", "по базе", "из базы",
        "проект", "код", "id=",
    )
    action_markers = ("изучи", "разбери", "проанализируй", "исправ", "почини", "улучши", "посмотри", "проверь", "делай")
    if any(marker in lowered for marker in primary_scope_markers) and any(marker in lowered for marker in action_markers):
        return True
    return (
        any(marker in lowered for marker in service_scope_markers)
        and any(marker in lowered for marker in local_evidence_markers)
        and any(marker in lowered for marker in action_markers)
    )


def detect_owner_admin_request(user_text: str, user_id: Optional[int], *, owner_user_id: int, normalize_whitespace_func: Callable[[str], str]) -> bool:
    if user_id != owner_user_id:
        return False
    lowered = normalize_whitespace_func(user_text).lower()
    if not lowered:
        return False
    return lowered.startswith("/") or any(
        marker in lowered
        for marker in (
            "owner", "gitstatus", "gitlast", "ownerreport", "memorychat", "memoryuser",
            "memorysummary", "worldstate", "selfstate", "autobio", "skills", "reflections",
            "routes", "errors", "events", "repairstatus",
        )
    )


def should_include_database_context(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    markers = (
        "база", "бд", "db", "database", "история", "событи", "кто", "почему", "когда",
        "участник", "пользоват", "user_id", "@", "рейтинг", "топ", "уров", "xp", "ачив",
        "достиж", "апел", "appeal", "бан", "мут", "warn", "варн", "санкц", "модер",
        "наруш", "профил", "статист", "лог", "факт", "remember", "recall", "feedback",
        "фидбек", "отзыв", "роут", "маршрут", "router", "policy", "self-check", "контекст",
    )
    return any(marker in lowered for marker in markers)


def has_external_research_signal(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    if is_local_project_meta_request(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return False
    triggers = (
        "найди", "поищи", "поиск", "в интернете", "интернет", "изучи", "исследуй",
        "что пишут", "свеж", "новост", "latest", "today", "сегодня", "проверь",
        "погода", "температур", "прогноз", "курс", "доллар", "евро", "битко", "bitcoin",
        "продаваем", "новинк", "вышло", "вышли", "релиз", "анонс", "актуальн",
    )
    if any(trigger in lowered for trigger in triggers):
        return True
    product_markers = ("смартфон", "телефон", "ноутбук", "планшет", "камера")
    freshness_markers = ("новых", "новые", "новый", "вышло", "вышли", "последние", "свежие")
    return any(marker in lowered for marker in product_markers) and any(marker in lowered for marker in freshness_markers)


def is_product_selection_help_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    product_markers = ("смартфон", "телефон", "ноутбук", "планшет", "камера", "наушник", "монитор", "роутер", "товар")
    selection_markers = ("помоги выбрать", "помогите выбрать", "что выбрать", "что лучше взять", "лучше взять", "выбор", "бюджет", "до ")
    return any(marker in lowered for marker in product_markers) and any(marker in lowered for marker in selection_markers)


def is_purchase_advice_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    product_markers = (
        "смартфон", "телефон", "ноутбук", "планшет", "камера", "наушник", "монитор", "роутер",
        "флагман", "айфон", "iphone", "samsung", "xiaomi", "realme", "oppo", "poco", "pixel", "honor", "vivo", "iqoo",
    )
    purchase_markers = (
        "что купить", "что лучше купить", "что выбрать", "помоги выбрать", "помогите выбрать",
        "лучше взять", "стоит ли брать", "сравни", "сравнить", "что круче", "круче", "лучше",
        "бюджет", "до ", "для игр", "для фото", "для фотосъем", "для камеры", "автономност", "производительност",
    )
    return any(marker in lowered for marker in product_markers) and any(marker in lowered for marker in purchase_markers)


def is_comparison_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    comparison_markers = ("сравни", "сравнить", "что лучше", "что круче", "чем отличается", "vs", "versus", "или", "против")
    object_markers = (
        "смартфон", "телефон", "ноутбук", "планшет", "камера", "наушник", "монитор", "роутер",
        "процессор", "видеокарта", "iphone", "samsung", "xiaomi", "realme", "oppo", "vivo", "honor", "poco", "pixel", "iqoo",
    )
    return any(marker in lowered for marker in comparison_markers) and (
        any(marker in lowered for marker in object_markers) or " или " in lowered or " vs " in lowered or " versus " in lowered
    )


def is_recommendation_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    recommendation_markers = ("посоветуй", "посоветуйте", "порекомендуй", "порекомендуйте", "что взять", "какой взять", "какую взять", "что выбрать", "что посоветуешь", "что порекомендуешь")
    topic_markers = ("смартфон", "телефон", "ноутбук", "планшет", "камера", "монитор", "роутер", "игр", "фильм", "сериал", "книга", "наушник", "мыш", "клавиатур", "процессор", "видеокарт")
    return any(marker in lowered for marker in recommendation_markers) and (any(marker in lowered for marker in topic_markers) or len(lowered.split()) >= 4)


def is_opinion_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    markers = ("как думаешь", "как считaешь", "как считаешь", "твое мнение", "твоё мнение", "что скажешь", "нормально ли", "есть смысл", "стоит ли")
    return any(marker in lowered for marker in markers)


def should_include_event_context(user_text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    text = user_text.lower()
    markers = ["помнишь", "напомни", "что писал", "что писали", "кто писал", "кто написал", "история", "лог", "перескажи", "вспомни", "что было", "из базы", "по базе", "архив", "раньше", "ранее", "до этого", "в чате", "в группе"]
    return detect_local_chat_query(text, normalize_whitespace_func=normalize_whitespace_func) or any(marker in text for marker in markers)


def detect_runtime_query(user_text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(user_text).lower()
    if not lowered:
        return False
    if any(marker in lowered for marker in RUNTIME_EXPLICIT_MARKERS):
        return True
    if "ошибк" in lowered and not any(marker in lowered for marker in RUNTIME_EXPLICIT_MARKERS):
        # "что за ошибка" чаще означает разбор сбоя/ответа, а не запрос на прямую
        # диагностику среды. Иначе Enterprise слишком часто уезжает в runtime-report.
        lowered = lowered.replace("ошибк", "")
    token_markers = {"ram", "mem", "cpu"}
    text_tokens = set(re.findall(r"[a-zа-яё0-9_+-]+", lowered, flags=re.IGNORECASE))
    for marker in RUNTIME_QUERY_MARKERS:
        if marker in token_markers:
            if marker in text_tokens:
                return True
            continue
        if marker in lowered:
            return True
    return False


def is_explicit_help_request(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered or len(lowered) < 12:
        return False
    help_markers = (
        "помоги", "помогите", "подскажи", "подскажите", "кто знает", "что делать", "как исправить",
        "как решить", "можно ли", "есть ли", "не работает", "не получается", "не могу", "почему",
        "как выбрать", "как настроить", "зачем", "ошибка", "сломалось", "в чем проблема", "что выбрать", "как лучше",
    )
    if not any(marker in lowered for marker in help_markers):
        return False
    if "?" in lowered:
        return True
    question_words = ("как", "почему", "зачем", "где", "кто", "что", "можно ли", "есть ли")
    return any(lowered.startswith(word + " ") or f" {word} " in lowered for word in question_words)


def detect_intent(user_text: str, *, normalize_whitespace_func: Callable[[str], str]) -> str:
    text = user_text.lower()
    if detect_runtime_query(text, normalize_whitespace_func=normalize_whitespace_func):
        return "runtime_status"
    if is_comparison_request(text, normalize_whitespace_func=normalize_whitespace_func):
        return "comparison_request"
    if is_purchase_advice_request(text, normalize_whitespace_func=normalize_whitespace_func):
        return "purchase_advice"
    if is_recommendation_request(text, normalize_whitespace_func=normalize_whitespace_func):
        return "recommendation_request"
    if detect_local_chat_query(text, normalize_whitespace_func=normalize_whitespace_func) and not has_external_research_signal(text, normalize_whitespace_func=normalize_whitespace_func):
        return "chat_dynamics"
    if is_explicit_help_request(text, normalize_whitespace_func=normalize_whitespace_func):
        return "troubleshooting_help"
    if is_opinion_request(text, normalize_whitespace_func=normalize_whitespace_func):
        return "opinion_request"
    if any(token in text for token in ["error", "ошибка", "traceback", "exception", "не работает", "сломалось"]):
        return "error_analysis"
    if any(token in text for token in ["код", "python", "js", "ts", "bash", "sql", "script", "скрипт", "функц", "класс"]):
        return "coding"
    if any(token in text for token in ["сделай", "напиши", "создай", "план", "как лучше", "что делать"]):
        return "task_solving"
    if len(text.split()) <= 4:
        return "short_question"
    return "general_dialog"


def response_shape_hint(intent: str) -> str:
    if intent == "runtime_status":
        return "Сначала конкретный статус или метрика. Если точной проверки не было, прямо скажи это. Не имитируй выполненную диагностику."
    if intent == "purchase_advice":
        return "Отвечай как внятный советчик по выбору покупки. Сначала короткий вывод под запрос пользователя. Потом 2-4 лучших варианта с понятными плюсами и минусами. Если в чате уже обсуждали модели или предпочтения, учитывай именно их. Если данных не хватает, задай один уточняющий вопрос вместо общего рассуждения. Не подавай рекомендацию как абсолютную истину: если выбор спорный, прямо скажи, в чём компромисс."
    if intent == "comparison_request":
        return "Отвечай как внятное сравнение. Сначала коротко скажи, кто сильнее и в каком сценарии. Потом сравни по 3-5 ключевым критериям, которые реально важны для этого вопроса. Если явного победителя нет, прямо скажи, от чего зависит выбор."
    if intent == "recommendation_request":
        return "Отвечай как нормальная рекомендация, а не как общий список. Сначала дай короткий вывод, потом 2-4 подходящих варианта. Если пользователь не уточнил важные ограничения, задай один короткий уточняющий вопрос."
    if intent == "chat_dynamics":
        return "Сначала коротко скажи, что происходит в этом чате сейчас. Затем по делу: участники, динамика, тон, суть. Не уходи в новости и не пересказывай лишнее."
    if intent == "troubleshooting_help":
        return "Сначала наиболее вероятная причина. Потом конкретные шаги, что проверить и что сделать. Не раздувай ответ."
    if intent == "opinion_request":
        return "Отвечай как мнение и оценка, а не как абсолютный факт. Сначала короткая позиция, потом 2-4 аргумента по делу."
    if intent == "error_analysis":
        return "Сначала вероятная причина. Затем конкретное решение. Без длинных вступлений."
    if intent == "coding":
        return "Сначала рабочее решение. Затем короткое пояснение. Если нужен код, покажи его достаточным фрагментом."
    if intent == "task_solving":
        return "Дай самый практичный вариант действий. Если шагов мало, не раздувай список."
    if intent == "short_question":
        return "Ответь коротко и прямо, без вводных фраз."
    return "Держи ответ компактным, точным и естественным."


def should_use_web_research(text: str, *, normalize_whitespace_func: Callable[[str], str]) -> bool:
    lowered = normalize_whitespace_func(text).lower()
    if not lowered:
        return False
    if is_local_project_meta_request(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return False
    if detect_runtime_query(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return False
    if is_comparison_request(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return True
    if is_purchase_advice_request(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return True
    if is_recommendation_request(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return True
    if is_product_selection_help_request(lowered, normalize_whitespace_func=normalize_whitespace_func) and not has_external_research_signal(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return False
    local_chat_query = detect_local_chat_query(lowered, normalize_whitespace_func=normalize_whitespace_func)
    if local_chat_query and not has_external_research_signal(lowered, normalize_whitespace_func=normalize_whitespace_func):
        return False
    return has_external_research_signal(lowered, normalize_whitespace_func=normalize_whitespace_func)


def classify_request_kind(user_text: str, *, user_id: Optional[int], assistant_persona: str, reply_context: str, deps: RouterRuntimeDeps) -> str:
    lowered = deps.normalize_whitespace_func(user_text).lower()
    if detect_owner_admin_request(lowered, user_id, owner_user_id=deps.owner_user_id, normalize_whitespace_func=deps.normalize_whitespace_func):
        return "owner_admin"
    if detect_runtime_query(lowered, normalize_whitespace_func=deps.normalize_whitespace_func):
        return "runtime"
    if is_local_project_meta_request(lowered, normalize_whitespace_func=deps.normalize_whitespace_func):
        return "project"
    if (
        deps.detect_news_query_func(lowered)
        or deps.detect_current_fact_query_func(lowered)
        or deps.detect_weather_location_func(lowered)
        or deps.detect_currency_pair_func(lowered)
        or deps.detect_crypto_asset_func(lowered)
        or deps.detect_stock_symbol_func(lowered)
        or should_use_web_research(lowered, normalize_whitespace_func=deps.normalize_whitespace_func)
    ):
        return "live"
    if detect_local_chat_query(lowered, normalize_whitespace_func=deps.normalize_whitespace_func) or bool(reply_context.strip()):
        return "chat_local_context"
    return "chat"


def analyze_request_route(user_text: str, assistant_persona: str, chat_type: str, *, user_id: Optional[int] = None, reply_context: str = "", deps: RouterRuntimeDeps) -> RouteDecision:
    normalized_text = deps.normalize_whitespace_func(user_text)
    local_project_meta_request = is_local_project_meta_request(normalized_text, normalize_whitespace_func=deps.normalize_whitespace_func)
    request_kind = classify_request_kind(
        normalized_text,
        user_id=user_id,
        assistant_persona=assistant_persona,
        reply_context=reply_context,
        deps=deps,
    )
    route_policy = ROUTER_POLICY_MATRIX.get(request_kind, ROUTER_POLICY_MATRIX["chat"])
    intent = detect_intent(normalized_text, normalize_whitespace_func=deps.normalize_whitespace_func)
    runtime_query = detect_runtime_query(normalized_text, normalize_whitespace_func=deps.normalize_whitespace_func)
    workspace_allowed = deps.can_owner_use_workspace_mode_func(user_id, chat_type, assistant_persona)
    route_kind = "codex_workspace" if workspace_allowed else "codex_chat"
    source_label = "Enterprise runtime" if runtime_query and workspace_allowed else "Enterprise"
    route_kind_live_map = {
        "live_weather": ("open-meteo", deps.detect_weather_location_func),
        "live_fx": ("frankfurter+yahoo-finance", deps.detect_currency_pair_func),
        "live_crypto": ("coingecko", deps.detect_crypto_asset_func),
        "live_stocks": ("yahoo-finance", deps.detect_stock_symbol_func),
        "live_current_fact": ("duckduckgo+Enterprise", deps.detect_current_fact_query_func),
        "live_news": ("google-news-rss", deps.detect_news_query_func),
    }
    allowed_route_kinds = {"codex_chat", "codex_workspace", *route_kind_live_map.keys()}
    live_hits: List[Tuple[str, str]] = []
    if not local_project_meta_request:
        for candidate_kind, (candidate_source, detector) in route_kind_live_map.items():
            detected_value = detector(normalized_text)
            if detected_value:
                live_hits.append((candidate_kind, candidate_source))
    if live_hits:
        route_kind, source_label = live_hits[0]
    use_live = route_kind.startswith("live_")
    use_web = should_use_web_research(normalized_text, normalize_whitespace_func=deps.normalize_whitespace_func) and not use_live and not runtime_query and request_kind not in {"project", "chat_local_context", "runtime", "owner_admin"}
    use_events = should_include_event_context(normalized_text, normalize_whitespace_func=deps.normalize_whitespace_func) and not runtime_query and request_kind in {"chat_local_context", "project", "owner_admin"}
    use_database = should_include_database_context(normalized_text) and not runtime_query and request_kind in {"chat_local_context", "project", "owner_admin", "live"}
    use_reply = bool(reply_context.strip())
    use_workspace = route_kind == "codex_workspace"
    guardrails: List[str] = []
    guardrails.extend(ROUTER_POLICY_LESSONS)
    if use_live:
        guardrails.append("freshness")
        guardrails.append("cite-source")
    if use_web:
        guardrails.append("external-web")
    if use_events or use_database or use_reply:
        guardrails.append("ground-in-chat-state")
    if intent in {"coding", "error_analysis"}:
        guardrails.append("be-explicit-about-assumptions")
    if runtime_query:
        guardrails.append("runtime-verification")
    if assistant_persona == "enterprise":
        guardrails.append("respect-enterprise-mode")
    if deps.is_dangerous_request_func(normalized_text) and assistant_persona != "enterprise":
        guardrails.append("no-system-actions")
    decision = RouteDecision(
        persona=assistant_persona or "jarvis",
        intent=intent,
        chat_type=chat_type,
        route_kind=route_kind,
        source_label=source_label,
        use_live=use_live,
        use_web=use_web,
        use_events=use_events,
        use_database=use_database,
        use_reply=use_reply,
        use_workspace=use_workspace,
        guardrails=tuple(guardrails),
        request_kind=request_kind,
        allowed_sources=route_policy.allowed_sources,
        forbidden_sources=route_policy.forbidden_sources,
        required_tools=route_policy.required_tools,
        answer_contract=route_policy.answer_contract,
    )
    deps.validate_route_decision_func(decision, allowed_route_kinds)
    return decision
