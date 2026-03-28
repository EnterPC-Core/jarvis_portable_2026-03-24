import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


ALL_PEDALS_RULES_TEXT = (
    "Правила чата «Все педали!»\n\n"
    "Пространство чата регулируется интеллектуальной системой автоматической модерации — ботом "
    "JARVIS (@Jarvis_3_0_bot). Взаимодействуя с чатом, вы соглашаетесь с этими правилами.\n\n"
    "1. Принципы работы модерации\n"
    "• Порядок поддерживает бот JARVIS. Решения принимаются автоматически по смыслу, контексту и модели поведения.\n"
    "• JARVIS анализирует не отдельную фразу, а цель высказывания, общий тон и паттерн поведения.\n"
    "• JARVIS действует в правовом поле РФ.\n"
    "• Формируется цифровой поведенческий профиль. Регулярные попытки манипуляции, дезинформации и обхода правил ведут к санкциям.\n\n"
    "2. Тематика и границы дискуссий\n"
    "• Основная тема: контент канала «РасПаковкаДваПаковка», видео, стримы, анонсы, техника, гаджеты и товары из обзоров.\n"
    "• Лёгкий оффтоп допустим, если он не доминирует над основной темой.\n\n"
    "3. Строго запрещено\n"
    "• Политика, религия, национальные вопросы.\n"
    "• Холивары ради конфликта.\n"
    "• Медицина, диетология и финансовые советы как категорические рекомендации.\n"
    "• Оскорбления, провокации, травля, агрессивный сарказм и личные выпады.\n"
    "• Навязчивое повторение одного и того же вопроса или текста.\n"
    "• Поток несвязанных изображений, мемов, гифок и ссылок без контекста.\n"
    "• Реклама.\n"
    "• 18+, пиратство, инструкции по взлому, экстремизм, насилие, запрещённый нелегальный контент.\n"
    "• Обсуждение VPN для запрещённых целей.\n"
    "• Публикация чужих личных данных без согласия.\n"
    "• Агрессивное навязывание точки зрения как единственно верной и заведомо ложные советы.\n\n"
    "4. Нецензурная лексика\n"
    "• Мат для оскорблений и провокаций запрещён.\n"
    "• 3+ сообщений подряд с матом или систематическое злоупотребление ведут к санкциям.\n\n"
    "5. Технические аспекты и жалобы\n"
    "• Массовое удаление своих сообщений после отправки расценивается как попытка скрыть нарушение.\n"
    "• Нарушение можно отметить командой /report в reply на сообщение нарушителя.\n"
    "• В чате могут быть другие боты. JARVIS не отвечает за их действия и не может отменять их баны.\n\n"
    "6. Обжалование\n"
    "• Если вы уверены, что решение JARVIS ошибочно, пишите в личные сообщения @DmitryUnboxing.\n\n"
    "Незнание правил не освобождает от ответственности. Цель правил — сделать общение комфортным для всех."
)


GENERIC_GROUP_RULES_TEXT = (
    "JARVIS-модерация в группе:\n"
    "• без оскорблений, травли и личных выпадов;\n"
    "• без навязчивого спама и повторов;\n"
    "• без опасного, нелегального и откровенно деструктивного контента;\n"
    "• за токсичное поведение бот может удалить сообщение, выдать предупреждение, мут или бан."
)


TARGETED_ABUSE_PATTERNS = (
    r"\bтуп(?:ой|ая|ые|ое|ица|ишь|ите)\b",
    r"\bидиот(?:ка)?\b",
    r"\bдебил(?:ка)?\b",
    r"\bпридур(?:ок|ок)?\b",
    r"\bкончен(?:ый|ая|ое)\b",
    r"\bмраз(?:ь|ота)\b",
    r"\bурод(?:ина)?\b",
    r"\bчмо\b",
    r"\bдаун\b",
    r"\bшиз(?:ик|оид)?\b",
    r"\bублюд(?:ок)?\b",
    r"\bсдохни\b",
    r"\bнедоразвит(?:ый|ая|ое|ые)\b",
    r"\bжопедрил(?:о|а)?\b",
    r"\bвысер\b",
    r"\bобтекай\b",
    r"\bберега\s+попутал\b",
    r"\bзакатай\s+свою\s+губу\b",
    r"\bродит\s+тебя\s+обратно\b",
    r"\bкто\s+дерзить\s+учил\b",
)

SEVERE_ABUSE_PATTERNS = (
    r"\bпош[её]л\s+нах",
    r"\bиди\s+нах",
    r"\bсдохни\b",
    r"\bсдохни\s+ты\b",
    r"\bмраз(?:ь|ота)\b",
    r"\bубью\b",
    r"\bубил\s+бы\b",
    r"\bкончен(?:ый|ая|ое)\b",
    r"\bадресн(?:ый|ая)\s+высер\b",
    r"\bтебя\s+обласкать\b",
    r"\bиди\s+сюда\b",
)

TOXIC_TONE_PATTERNS = (
    r"\bнедоразвит(?:ый|ая|ое|ые)\b",
    r"\bжопедрил(?:о|а)?\b",
    r"\bвысер\b",
    r"\bобтекай\b",
    r"\bберега\s+попутал\b",
    r"\bзакатай\s+свою\s+губу\b",
    r"\bродит\s+тебя\s+обратно\b",
    r"\bкто\s+дерзить\s+учил\b",
    r"\bиди\s+сюда\b",
    r"\bобласкать\b",
)

SOFT_CONFLICT_PATTERNS = (
    r"\bбред\b",
    r"\bчуш(?:ь)?\b",
    r"\bерунда\b",
    r"\bфигня\b",
    r"\bсказки\b",
    r"\bчепуха\b",
    r"\bне\s+свисти\b",
    r"\bпургу\b",
    r"\bпритянуто\b",
)

UNVERIFIED_FACT_PATTERNS = (
    r"\bэто\s+факт\b",
    r"\b100%\b",
    r"\bсто\s+процент",
    r"\bточно\b",
    r"\bбез\s+вариантов\b",
    r"\bгарантир",
    r"\bдоказано\b",
    r"\bочевидно\b",
    r"\bполучит\s+доступ\s+к\s+руту\b",
    r"\bпрошивк\w+\s+под\s+себя\b",
    r"\bвсе\s+данные\s+давно\s+есть\b",
)

MODERATION_CHALLENGE_PATTERNS = (
    r"\bразве\s+это\s+оскорблен",
    r"\bэто\s+разве\s+оскорблен",
    r"\bчто,\s*и\s+это\s+тоже\b",
    r"\bберега\s+попутал\b",
)

BOT_MARKERS = ("jarvis", "джарвис", "@jarvis_3_0_bot", "бот", "@test_aipc_bot")
SECOND_PERSON_MARKERS = ("ты", "тебя", "тебе", "твой", "твоя", "твоё", "тупой", "идиот", "дебил")
RULES_QUOTE_MARKERS = ("запрещено", "правила", "оскорбления", "провокации", "санкц", "модерац")


@dataclass(frozen=True)
class AutoModerationDecision:
    code: str
    action: str
    reason: str
    public_reason: str
    severity: str = "medium"
    suggested_owner_action: str = ""
    delete_message: bool = True
    mute_seconds: int = 0
    ban_seconds: int = 0
    add_warning: bool = False


def normalize_chat_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def is_all_pedals_chat(title: str) -> bool:
    normalized = normalize_chat_title(title)
    return "все педали" in normalized


def get_group_rules_text(chat_title: str) -> str:
    if is_all_pedals_chat(chat_title):
        return ALL_PEDALS_RULES_TEXT
    return GENERIC_GROUP_RULES_TEXT


def _contains_pattern(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _normalize_message_text(text: str) -> str:
    cleaned = (text or "").lower().replace("ё", "е")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _looks_like_rules_quote(text: str) -> bool:
    if len(text) < 120:
        return False
    return sum(1 for marker in RULES_QUOTE_MARKERS if marker in text) >= 2


def _targets_bot(message: dict, normalized_text: str, *, bot_username: str, trigger_name: str) -> bool:
    reply_to = (message or {}).get("reply_to_message") or {}
    reply_from = reply_to.get("from") or {}
    if reply_from.get("is_bot"):
        return True
    markers = list(BOT_MARKERS)
    if bot_username:
        markers.append(f"@{bot_username.lower().lstrip('@')}")
    if trigger_name:
        markers.append(trigger_name.lower())
    return any(marker and marker in normalized_text for marker in markers)


def _targets_user(message: dict, normalized_text: str) -> bool:
    reply_to = (message or {}).get("reply_to_message") or {}
    reply_from = reply_to.get("from") or {}
    if reply_from and not reply_from.get("is_bot"):
        return True
    if "@" in normalized_text:
        return True
    return any(marker in normalized_text for marker in SECOND_PERSON_MARKERS)


def _is_repeated_spam(normalized_text: str, recent_texts: list[str]) -> bool:
    if len(normalized_text) < 8:
        return False
    comparable = [item for item in recent_texts if item]
    if comparable.count(normalized_text) >= 3:
        return True
    condensed = re.sub(r"[!?.,:;\\-]+", "", normalized_text)
    similar_count = 0
    for item in comparable:
        candidate = re.sub(r"[!?.,:;\\-]+", "", item)
        if candidate == condensed:
            similar_count += 1
    return similar_count >= 3


def _is_profanity_flood(recent_texts: list[str], contains_profanity_func: Callable[[str], bool]) -> bool:
    profanity_hits = 0
    for item in recent_texts[-5:]:
        if contains_profanity_func(item):
            profanity_hits += 1
    return profanity_hits >= 3


def _is_toxic_tone(text: str, contains_profanity_func: Callable[[str], bool]) -> bool:
    return contains_profanity_func(text) or _contains_pattern(text, TARGETED_ABUSE_PATTERNS) or _contains_pattern(text, TOXIC_TONE_PATTERNS)


def _recent_toxic_count(recent_texts: list[str], contains_profanity_func: Callable[[str], bool]) -> int:
    return sum(1 for item in recent_texts[-5:] if _is_toxic_tone(item, contains_profanity_func))


def detect_auto_moderation_decision(
    *,
    message: dict,
    raw_text: str,
    recent_texts: list[str],
    chat_title: str,
    bot_username: str,
    trigger_name: str,
    contains_profanity_func: Callable[[str], bool],
) -> Optional[AutoModerationDecision]:
    normalized_text = _normalize_message_text(raw_text)
    if not normalized_text or normalized_text.startswith("/"):
        return None
    if _looks_like_rules_quote(normalized_text):
        return None

    targets_bot = _targets_bot(message, normalized_text, bot_username=bot_username, trigger_name=trigger_name)
    targets_user = _targets_user(message, normalized_text)
    if targets_bot:
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if not reply_from or reply_from.get("is_bot"):
            targets_user = False
    has_profanity = contains_profanity_func(normalized_text)
    has_targeted_abuse = _contains_pattern(normalized_text, TARGETED_ABUSE_PATTERNS)
    has_severe_abuse = _contains_pattern(normalized_text, SEVERE_ABUSE_PATTERNS)
    has_toxic_tone = _contains_pattern(normalized_text, TOXIC_TONE_PATTERNS)
    has_soft_conflict = _contains_pattern(normalized_text, SOFT_CONFLICT_PATTERNS)
    has_unverified_fact = _contains_pattern(normalized_text, UNVERIFIED_FACT_PATTERNS)
    challenges_moderation = _contains_pattern(normalized_text, MODERATION_CHALLENGE_PATTERNS)
    recent_toxic_count = _recent_toxic_count(recent_texts, contains_profanity_func)
    recent_conflict_count = sum(1 for item in recent_texts[-5:] if _contains_pattern(item, SOFT_CONFLICT_PATTERNS))

    if targets_user and (has_severe_abuse or (has_profanity and has_targeted_abuse)):
        return AutoModerationDecision(
            code="targeted_severe_abuse",
            action="mute",
            reason="автомут: тяжёлые личные оскорбления участника",
            public_reason="тяжёлые личные оскорбления участника",
            severity="high",
            suggested_owner_action="Посмотреть контекст и решить: оставить мут, продлить мут вручную или удалить участника.",
            mute_seconds=12 * 3600,
            add_warning=True,
        )
    if targets_bot and (has_severe_abuse or (has_profanity and has_targeted_abuse)):
        return AutoModerationDecision(
            code="bot_abuse_strong",
            action="mute",
            reason="автомут: тяжёлые оскорбления JARVIS",
            public_reason="тяжёлые оскорбления JARVIS",
            severity="high",
            suggested_owner_action="Посмотреть контекст и решить: хватит ли этого мута или нужна ручная санкция.",
            mute_seconds=2 * 3600,
            add_warning=True,
        )
    if targets_user and has_toxic_tone:
        return AutoModerationDecision(
            code="targeted_toxic_tone",
            action="mute",
            reason="автомут: токсичный адресный наезд на участника",
            public_reason="токсичный адресный наезд на участника",
            severity="high" if recent_toxic_count >= 2 else "medium",
            suggested_owner_action="Если это не первый выпад подряд, лучше не спорить с участником и оставить мут.",
            mute_seconds=2 * 3600 if recent_toxic_count >= 2 else 60 * 60,
            add_warning=True,
        )
    if targets_user and (has_targeted_abuse or has_profanity):
        return AutoModerationDecision(
            code="targeted_abuse",
            action="mute",
            reason="автомут: личные оскорбления участника",
            public_reason="личные оскорбления участника",
            severity="medium",
            suggested_owner_action="Обычно достаточно мута. Если участник продолжит, уже решать вручную.",
            mute_seconds=60 * 60,
            add_warning=True,
        )
    if targets_bot and (has_toxic_tone or (recent_toxic_count >= 2 and challenges_moderation)):
        return AutoModerationDecision(
            code="bot_toxic_tone",
            action="mute" if recent_toxic_count >= 2 else "warn",
            reason="автосанкция: токсичный адресный наезд на JARVIS",
            public_reason="токсичный адресный наезд на JARVIS",
            severity="high" if recent_toxic_count >= 2 else "medium",
            suggested_owner_action="Если это серия выпадов, спор уже бесполезен: оставить мут и не продолжать перепалку.",
            mute_seconds=2 * 3600 if recent_toxic_count >= 2 else 0,
            add_warning=True,
        )
    if targets_bot and (has_targeted_abuse or has_profanity):
        return AutoModerationDecision(
            code="bot_abuse",
            action="warn",
            reason="автопредупреждение: оскорбления JARVIS",
            public_reason="оскорбления JARVIS",
            severity="medium",
            suggested_owner_action="Обычно хватает предупреждения. Если пойдёт дальше, можно дать ручной мут.",
            add_warning=True,
        )
    if _is_repeated_spam(normalized_text, recent_texts):
        return AutoModerationDecision(
            code="repeated_spam",
            action="mute",
            reason="автомут: навязчивый повтор одного и того же сообщения",
            public_reason="навязчивый повтор одного и того же сообщения",
            severity="medium",
            suggested_owner_action="Проверить, не начал ли участник засыпать чат однотипными сообщениями системно.",
            mute_seconds=15 * 60,
            add_warning=True,
        )
    if _is_profanity_flood(recent_texts, contains_profanity_func):
        return AutoModerationDecision(
            code="profanity_flood",
            action="mute",
            reason="автомут: поток мата и токсичного общения",
            public_reason="поток мата и токсичного общения",
            severity="medium",
            suggested_owner_action="Если это разовый срыв, хватит мута. Если паттерн повторяется, решать вручную.",
            mute_seconds=30 * 60,
            add_warning=True,
        )
    if has_unverified_fact and (has_soft_conflict or recent_conflict_count >= 1):
        return AutoModerationDecision(
            code="disinfo_risk_deescalation",
            action="deescalate",
            reason="мягкое вмешательство: спорные утверждения без подтверждения в разогретом споре",
            public_reason="стоп, отделяем личный опыт от проверяемых фактов. Спорные утверждения без подтверждения не подаем как установленную истину; если есть источник, приносите его.",
            severity="low",
            suggested_owner_action="Наблюдать. Если спор уйдёт в личные выпады или навязчивую дезинформацию, уже включать санкции.",
            delete_message=False,
        )
    if (targets_user or recent_conflict_count >= 2) and has_soft_conflict and not has_profanity and not has_targeted_abuse:
        return AutoModerationDecision(
            code="soft_conflict_deescalation",
            action="deescalate",
            reason="мягкое вмешательство: спор разогревается и уходит в пикировку",
            public_reason="сбавим температуру. Спорьте по сути, без подколов и перехода на личности; сначала формулируем тезис, потом аргумент.",
            severity="low",
            suggested_owner_action="Обычно хватает короткого охлаждения диалога. Если после этого начнутся адресные выпады, тогда уже warn/mute.",
            delete_message=False,
        )
    if is_all_pedals_chat(chat_title) and has_profanity:
        return AutoModerationDecision(
            code="all_pedals_profanity",
            action="warn",
            reason="автопредупреждение: токсичная лексика в «Все педали!»",
            public_reason="токсичная лексика",
            severity="low",
            suggested_owner_action="Пока без жёстких мер. Просто наблюдать за дальнейшим поведением.",
            add_warning=True,
        )
    return None
