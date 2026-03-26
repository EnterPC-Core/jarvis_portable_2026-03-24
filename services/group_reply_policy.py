import time
from typing import Any, Callable, Optional


class GroupReplyPolicy:
    def __init__(
        self,
        *,
        state: Any,
        config: Any,
        normalize_whitespace_func: Callable[[str], str],
        is_dangerous_request_func: Callable[[str], bool],
        compute_score_func: Callable[[str], int],
        get_chat_event_count_func: Callable[[int], int],
        log_func: Callable[[str], None],
    ) -> None:
        self.state = state
        self.config = config
        self.normalize_whitespace = normalize_whitespace_func
        self.is_dangerous_request = is_dangerous_request_func
        self.compute_score = compute_score_func
        self.get_chat_event_count = get_chat_event_count_func
        self.log = log_func

    def _discussion_turn_count_key(self, chat_id: int, user_id: int) -> str:
        return f"group_discussion_turn_count:{chat_id}:{user_id}"

    def _discussion_block_key(self, chat_id: int, user_id: int) -> str:
        return f"group_discussion_block_until:{chat_id}:{user_id}"

    def _discussion_window_key(self, chat_id: int, user_id: int) -> str:
        return f"group_followup_until:{chat_id}:{user_id}"

    def is_group_discussion_rate_limited(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id is None or chat_id >= 0:
            return False
        block_key = self._discussion_block_key(chat_id, int(user_id))
        with self.state.db_lock:
            raw_value = self.state.get_meta(block_key, "0")
        try:
            blocked_until = int(raw_value or "0")
        except ValueError:
            blocked_until = 0
        return blocked_until > int(time.time())

    def record_group_discussion_turn(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id is None or chat_id >= 0:
            return True
        user_id = int(user_id)
        now_ts = int(time.time())
        window_key = self._discussion_window_key(chat_id, user_id)
        count_key = self._discussion_turn_count_key(chat_id, user_id)
        block_key = self._discussion_block_key(chat_id, user_id)
        with self.state.db_lock:
            raw_window = self.state.get_meta(window_key, "0")
            raw_count = self.state.get_meta(count_key, "0")
            raw_block = self.state.get_meta(block_key, "0")
            try:
                window_until = int(raw_window or "0")
            except ValueError:
                window_until = 0
            try:
                turn_count = int(raw_count or "0")
            except ValueError:
                turn_count = 0
            try:
                blocked_until = int(raw_block or "0")
            except ValueError:
                blocked_until = 0
            if blocked_until > now_ts:
                return False
            if window_until <= now_ts:
                window_until = now_ts + int(self.config.group_followup_window_seconds)
                turn_count = 0
                self.state.set_meta(window_key, str(window_until))
            turn_count += 1
            self.state.set_meta(count_key, str(turn_count))
            if turn_count > int(self.config.group_discussion_max_turns_per_user):
                blocked_until = now_ts + int(self.config.group_discussion_cooldown_seconds)
                self.state.set_meta(block_key, str(blocked_until))
                return False
        return True

    def is_ambient_group_chatter(self, message: dict, raw_text: str) -> bool:
        normalized = self.normalize_whitespace(raw_text).lower()
        if not normalized or normalized.startswith("/"):
            return False
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if reply_from.get("is_bot"):
            return False
        if "?" in normalized:
            return False
        if self.compute_score(normalized) >= 2:
            return False
        short_ack_markers = (
            "ага",
            "ок",
            "окей",
            "ясно",
            "понял",
            "поняла",
            "понятно",
            "бывает",
            "норм",
            "нормально",
            "спасибо",
            "благодарю",
            "лол",
            "хаха",
            "ахаха",
            "жесть",
            "капец",
            "имба",
            "согласен",
            "согласна",
            "плюсую",
            "в точку",
            "ну да",
            "да, понял",
            "да понял",
        )
        if any(marker == normalized or marker in normalized for marker in short_ack_markers):
            return True
        if len(normalized.split()) <= 3 and len(normalized) <= 24:
            return True
        return False

    def is_meaningful_group_request(self, message: dict, raw_text: str) -> bool:
        normalized = self.normalize_whitespace(raw_text).lower()
        if not normalized or normalized.startswith("/"):
            return False
        if self.is_ambient_group_chatter(message, normalized):
            return False
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if reply_from.get("is_bot"):
            return True
        if "?" in normalized:
            return True
        if self.compute_score(normalized) >= 3:
            return True
        request_markers = (
            "сравни",
            "сравнить",
            "что лучше",
            "что круче",
            "посоветуй",
            "посоветуйте",
            "какой взять",
            "стоит ли",
            "есть смысл",
            "чем отличается",
            "а если",
        )
        return any(marker in normalized for marker in request_markers)

    def _looks_like_requested_followup(self, message: dict, text: str) -> bool:
        normalized = self.normalize_whitespace(text).lower()
        if not normalized:
            return False
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if reply_from.get("is_bot"):
            return True
        if "?" in normalized:
            return True
        if self.compute_score(normalized) >= 3:
            return True
        followup_markers = (
            "а если",
            "а что",
            "а как",
            "почему",
            "зачем",
            "то есть",
            "из этих",
            "из этого",
            "какой лучше",
            "что лучше",
            "какой взять",
            "стоит ли",
            "есть смысл",
            "сравни",
            "сравнить",
        )
        return any(marker in normalized for marker in followup_markers)

    def try_claim_group_spontaneous_reply_slot(self, chat_id: int, message_id: Optional[int]) -> bool:
        cooldown_key = f"group_spontaneous_reply_last_ts:{chat_id}"
        message_key = f"group_spontaneous_reply_last_message_id:{chat_id}"
        now_ts = int(time.time())
        with self.state.db_lock:
            last_ts_raw = self.state.get_meta(cooldown_key, "0")
            last_message_id = self.state.get_meta(message_key, "")
            try:
                last_ts = int(last_ts_raw or "0")
            except ValueError:
                last_ts = 0
            if last_ts and now_ts - last_ts < self.config.group_spontaneous_reply_cooldown_seconds:
                return False
            if message_id is not None and last_message_id == str(message_id):
                return False
            self.state.set_meta(cooldown_key, str(now_ts))
            self.state.set_meta(message_key, str(message_id or ""))
        return True

    def is_group_spontaneous_reply_candidate(self, chat_id: int, message: dict, raw_text: str) -> bool:
        text = self.normalize_whitespace(raw_text)
        if not text or text.startswith("/"):
            return False
        from_user = message.get("from") or {}
        if from_user.get("is_bot"):
            return False
        if self.is_dangerous_request(text):
            return False
        if self.is_ambient_group_chatter(message, text):
            return False
        if self.get_chat_event_count(chat_id) < 80:
            return False
        return self.compute_score(text) >= 3

    def grant_group_followup_window(self, chat_id: int, user_id: Optional[int]) -> None:
        if user_id is None or chat_id >= 0:
            return
        expires_at = int(time.time()) + int(self.config.group_followup_window_seconds)
        key = self._discussion_window_key(chat_id, int(user_id))
        with self.state.db_lock:
            self.state.set_meta(key, str(expires_at))
            self.state.set_meta(self._discussion_turn_count_key(chat_id, int(user_id)), "0")

    def has_active_group_followup_window(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id is None or chat_id >= 0:
            return False
        key = self._discussion_window_key(chat_id, int(user_id))
        with self.state.db_lock:
            raw_value = self.state.get_meta(key, "0")
        try:
            expires_at = int(raw_value or "0")
        except ValueError:
            expires_at = 0
        return expires_at > int(time.time())

    def is_group_followup_message(self, chat_id: int, message: dict, raw_text: str) -> bool:
        from_user = message.get("from") or {}
        user_id = from_user.get("id")
        if not self.has_active_group_followup_window(chat_id, user_id):
            return False
        if self.is_group_discussion_rate_limited(chat_id, user_id):
            return False
        text = self.normalize_whitespace(raw_text)
        if not text or text.startswith("/"):
            return False
        if from_user.get("is_bot"):
            return False
        if self.is_dangerous_request(text):
            return False
        if len(text) < 4 or not any(ch.isalpha() for ch in text):
            return False
        if self.is_ambient_group_chatter(message, text):
            return False
        return self._looks_like_requested_followup(message, text)

    def should_consider_group_spontaneous_reply(self, chat_id: int, message: dict, raw_text: str) -> bool:
        if not self.config.group_spontaneous_reply_enabled:
            return False
        if not self.is_group_spontaneous_reply_candidate(chat_id, message, raw_text):
            return False
        text = self.normalize_whitespace(raw_text)
        message_id = message.get("message_id")
        score = self.compute_score(text)
        if score >= 4:
            accepted = self.try_claim_group_spontaneous_reply_slot(chat_id, message_id)
            if not accepted:
                self.log(
                    f"group spontaneous reply skipped chat={chat_id} user={(message.get('from') or {}).get('id')} "
                    f"message_id={message_id} reason=cooldown score={score}"
                )
            return accepted
        chance = max(0, min(100, int(self.config.group_spontaneous_reply_chance_percent)))
        if chance <= 0:
            return False
        roll_seed = abs(int(chat_id)) + abs(int(message_id or 0)) * 17 + len(text) * 13
        if roll_seed % 100 >= chance:
            self.log(
                f"group spontaneous reply skipped chat={chat_id} user={(message.get('from') or {}).get('id')} "
                f"message_id={message_id} reason=chance score={score} chance={chance}"
            )
            return False
        if not self.try_claim_group_spontaneous_reply_slot(chat_id, message_id):
            self.log(
                f"group spontaneous reply skipped chat={chat_id} user={(message.get('from') or {}).get('id')} "
                f"message_id={message_id} reason=cooldown score={score}"
            )
            return False
        return True
