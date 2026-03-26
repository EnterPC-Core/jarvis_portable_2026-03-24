import json
import re
import time
from typing import Any, Callable, Dict, List, Optional


class GroupConversationState:
    def __init__(
        self,
        *,
        state: Any,
        normalize_whitespace_func: Callable[[str], str],
        is_dangerous_request_func: Callable[[str], bool],
        is_explicit_help_request_func: Callable[[str], bool],
        bot_user_id_getter: Callable[[], Optional[int]],
        owner_user_id: int,
    ) -> None:
        self.state = state
        self.normalize_whitespace = normalize_whitespace_func
        self.is_dangerous_request = is_dangerous_request_func
        self.is_explicit_help_request = is_explicit_help_request_func
        self.bot_user_id_getter = bot_user_id_getter
        self.owner_user_id = owner_user_id

    def _threads_key(self, chat_id: int) -> str:
        return f"group_discussion_threads:{chat_id}"

    def _legacy_key(self, chat_id: int) -> str:
        return f"group_discussion_state:{chat_id}"

    def _extract_topic_keywords(self, text: str) -> list[str]:
        normalized = self.normalize_whitespace(text).lower()
        if not normalized:
            return []
        stop_words = {
            "привет", "чат", "jarvis", "джарвис", "бот", "это", "этот", "эта", "эти", "так", "тут", "здесь",
            "что", "как", "где", "когда", "почему", "зачем", "можно", "нужно", "если", "тогда", "вообще",
            "помоги", "помогите", "подскажи", "подскажите", "выбрать", "лучше", "сравни", "сравнить",
            "брать", "взять", "есть", "смысл", "нужен", "нужно", "прошу", "пожалуйста",
            "этих", "этого", "двух", "тогда", "вчера", "сегодня",
        }
        words = []
        for raw_word in re.findall(r"[a-zа-яё0-9_+-]+", normalized, flags=re.IGNORECASE):
            word = raw_word.strip().lower()
            if len(word) < 4 or word in stop_words:
                continue
            words.append(word)
        return words[:10]

    def _has_topic_overlap(self, text: str, topic_keywords: list[str]) -> bool:
        if not topic_keywords:
            return True
        normalized = self.normalize_whitespace(text).lower()
        if not normalized:
            return False
        for keyword in topic_keywords[:8]:
            if keyword in normalized:
                return True
            if len(keyword) >= 5 and keyword[:5] in normalized:
                return True
            if len(keyword) >= 4 and keyword[:4] in normalized:
                return True
        return False

    def _looks_like_continuation_prompt(self, message: dict, text: str) -> bool:
        normalized = self.normalize_whitespace(text).lower()
        if not normalized:
            return False
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if reply_from.get("is_bot"):
            return True
        if "?" in normalized:
            return True
        if self.is_explicit_help_request(normalized):
            return True
        continuation_markers = (
            "а если",
            "а что",
            "а как",
            "почему",
            "то есть",
            "из этих",
            "из этого",
            "какой лучше",
            "что лучше",
            "стоит ли",
            "есть смысл",
            "сравни",
            "сравнить",
            "чем отличается",
            "а есть",
        )
        return any(marker in normalized for marker in continuation_markers)

    def _looks_like_new_participant_join(self, text: str) -> bool:
        normalized = self.normalize_whitespace(text).lower()
        if not normalized:
            return False
        if self.is_explicit_help_request(normalized):
            return True
        join_markers = (
            "а если",
            "а что",
            "а как",
            "почему",
            "из этих",
            "из этого",
            "что лучше",
            "какой лучше",
            "чем отличается",
            "есть смысл",
            "стоит ли",
            "а есть",
        )
        return "?" in normalized and any(marker in normalized for marker in join_markers)

    def _sanitize_thread(self, payload: Dict[str, object]) -> Dict[str, object]:
        expires_at = int(payload.get("expires_at") or 0)
        participants = [int(item) for item in (payload.get("participants") or []) if str(item).lstrip("-").isdigit()]
        topic_keywords = [str(item) for item in (payload.get("topic_keywords") or []) if str(item).strip()]
        return {
            "thread_id": str(payload.get("thread_id") or ""),
            "expires_at": expires_at,
            "last_activity_at": int(payload.get("last_activity_at") or expires_at or 0),
            "anchor_user_id": int(payload.get("anchor_user_id") or 0),
            "anchor_message_id": int(payload.get("anchor_message_id") or 0),
            "anchor_reply_user_id": int(payload.get("anchor_reply_user_id") or 0),
            "participants": participants,
            "reply_to_bot": int(payload.get("reply_to_bot") or 0),
            "topic_keywords": topic_keywords,
        }

    def _load_threads(self, chat_id: int) -> List[Dict[str, object]]:
        if chat_id >= 0:
            return []
        with self.state.db_lock:
            raw = self.state.get_meta(self._threads_key(chat_id), "")
            legacy_raw = self.state.get_meta(self._legacy_key(chat_id), "")
        threads: List[Dict[str, object]] = []
        if raw:
            try:
                payload = json.loads(raw)
                for item in payload if isinstance(payload, list) else []:
                    if isinstance(item, dict):
                        threads.append(self._sanitize_thread(item))
            except Exception:
                threads = []
        if not threads and legacy_raw:
            try:
                legacy_payload = json.loads(legacy_raw)
                if isinstance(legacy_payload, dict):
                    threads.append(self._sanitize_thread(legacy_payload))
            except Exception:
                pass
        now_ts = int(time.time())
        return [item for item in threads if int(item.get("expires_at") or 0) > now_ts]

    def _save_threads(self, chat_id: int, threads: List[Dict[str, object]]) -> None:
        with self.state.db_lock:
            self.state.set_meta(self._threads_key(chat_id), json.dumps(threads[:4], ensure_ascii=True))
            primary = threads[0] if threads else {}
            self.state.set_meta(self._legacy_key(chat_id), json.dumps(primary, ensure_ascii=True) if primary else "")

    def _reply_to_bot(self, message: dict) -> bool:
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        bot_user_id = self.bot_user_id_getter()
        return bool(reply_from.get("is_bot")) or (bot_user_id is not None and reply_from.get("id") == bot_user_id)

    def _reply_to_user_id(self, message: dict) -> int:
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        reply_user_id = reply_from.get("id")
        if reply_from.get("is_bot") or reply_user_id is None:
            return 0
        return int(reply_user_id)

    def _build_thread_payload(
        self,
        *,
        previous_thread: Dict[str, object],
        user_id: Optional[int],
        message: Optional[dict],
        ttl_seconds: int,
    ) -> Dict[str, object]:
        participants = []
        if user_id is not None:
            participants.append(int(user_id))
        reply_user_id = self._reply_to_user_id(message or {})
        if reply_user_id:
            participants.append(reply_user_id)
        text = (message or {}).get("text") or (message or {}).get("caption") or ""
        topic_keywords = self._extract_topic_keywords(text)
        previous_keywords = [str(item) for item in (previous_thread.get("topic_keywords") or []) if str(item).strip()]
        if len(topic_keywords) < 2 and previous_keywords:
            topic_keywords = list(dict.fromkeys(topic_keywords + previous_keywords))[:10]
        return {
            "thread_id": str(previous_thread.get("thread_id") or f"{int(time.time())}:{int((message or {}).get('message_id') or 0)}"),
            "expires_at": int(time.time()) + max(60, int(ttl_seconds)),
            "last_activity_at": int(time.time()),
            "anchor_user_id": int(user_id) if user_id is not None else int(previous_thread.get("anchor_user_id") or 0),
            "anchor_message_id": int((message or {}).get("message_id") or previous_thread.get("anchor_message_id") or 0),
            "anchor_reply_user_id": reply_user_id or int(previous_thread.get("anchor_reply_user_id") or 0),
            "participants": sorted({int(item) for item in participants + list(previous_thread.get("participants") or []) if int(item) > 0}),
            "reply_to_bot": int(self._reply_to_bot(message or {})) or int(previous_thread.get("reply_to_bot") or 0),
            "topic_keywords": topic_keywords,
        }

    def _select_best_thread(self, chat_id: int, message: Optional[dict], raw_text: str = "") -> Dict[str, object]:
        threads = self._load_threads(chat_id)
        if not threads:
            return {}
        if not message:
            return sorted(threads, key=lambda item: int(item.get("last_activity_at") or 0), reverse=True)[0]
        user_id = (message.get("from") or {}).get("id")
        reply_to_bot = self._reply_to_bot(message)
        reply_user_id = self._reply_to_user_id(message)
        normalized_text = self.normalize_whitespace(raw_text or (message.get("text") or "")).lower()
        scored: List[tuple[int, Dict[str, object]]] = []
        for thread in threads:
            score = 0
            participants = {int(item) for item in (thread.get("participants") or []) if str(item).lstrip("-").isdigit()}
            if reply_to_bot and int(thread.get("reply_to_bot") or 0):
                score += 10
            if reply_user_id and reply_user_id == int(thread.get("anchor_reply_user_id") or 0):
                score += 8
            if reply_user_id and reply_user_id in participants:
                score += 6
            if user_id is not None and int(user_id) in participants:
                score += 5
            if self._has_topic_overlap(normalized_text, [str(item) for item in (thread.get("topic_keywords") or [])]):
                score += 4
            score += min(3, max(0, int(thread.get("last_activity_at") or 0) // 300000000))
            scored.append((score, thread))
        best_score, best_thread = sorted(scored, key=lambda item: (item[0], int(item[1].get("last_activity_at") or 0)), reverse=True)[0]
        return best_thread if best_score > 0 else {}

    def _is_parallel_reply_branch(self, thread: Dict[str, object], message: dict) -> bool:
        reply_user_id = self._reply_to_user_id(message)
        if not reply_user_id:
            return False
        participants = {int(item) for item in (thread.get("participants") or []) if str(item).lstrip("-").isdigit()}
        if reply_user_id in participants:
            return False
        if reply_user_id in {int(thread.get("anchor_user_id") or 0), int(thread.get("anchor_reply_user_id") or 0)}:
            return False
        return True

    def mark_active_discussion(self, chat_id: int, user_id: Optional[int], message: Optional[dict], ttl_seconds: int = 900) -> None:
        if chat_id >= 0:
            return
        threads = self._load_threads(chat_id)
        previous_thread = self._select_best_thread(chat_id, message, (message or {}).get("text") or "")
        payload = self._build_thread_payload(
            previous_thread=previous_thread,
            user_id=user_id,
            message=message,
            ttl_seconds=ttl_seconds,
        )
        updated_threads: List[Dict[str, object]] = []
        replaced = False
        for thread in threads:
            if thread.get("thread_id") == payload.get("thread_id"):
                updated_threads.append(payload)
                replaced = True
            else:
                updated_threads.append(thread)
        if not replaced:
            updated_threads.insert(0, payload)
        updated_threads = sorted(updated_threads, key=lambda item: int(item.get("last_activity_at") or 0), reverse=True)[:4]
        self._save_threads(chat_id, updated_threads)

    def get_active_discussion(self, chat_id: int, message: Optional[dict] = None, raw_text: str = "") -> Dict[str, object]:
        if chat_id >= 0:
            return {}
        return self._select_best_thread(chat_id, message, raw_text)

    def get_group_participant_priority(self, chat_id: int, message: dict) -> str:
        from_user = (message.get("from") or {})
        user_id = from_user.get("id")
        if user_id == self.owner_user_id:
            return "owner"
        thread = self.get_active_discussion(chat_id, message, (message.get("text") or ""))
        if not thread:
            return "ambient"
        if self._reply_to_bot(message):
            return "reply_to_bot"
        participants = {int(item) for item in (thread.get("participants") or []) if str(item).lstrip("-").isdigit()}
        if user_id is not None and int(user_id) in participants:
            return "active_participant"
        return "new_participant"

    def is_group_discussion_continuation(self, chat_id: int, message: dict, raw_text: str) -> bool:
        if chat_id >= 0:
            return False
        thread = self.get_active_discussion(chat_id, message, raw_text)
        if not thread:
            return False
        text = self.normalize_whitespace(raw_text)
        if not text or text.startswith("/"):
            return False
        if self.is_dangerous_request(text):
            return False
        from_user = message.get("from") or {}
        if from_user.get("is_bot"):
            return False
        if self._is_parallel_reply_branch(thread, message):
            return False
        user_id = from_user.get("id")
        participants = {int(item) for item in (thread.get("participants") or []) if str(item).lstrip("-").isdigit()}
        topic_keywords = [str(item) for item in (thread.get("topic_keywords") or []) if str(item).strip()]
        if self._reply_to_bot(message):
            return True
        if user_id is not None and int(user_id) in participants and self._looks_like_continuation_prompt(message, text):
            return True
        if user_id is not None and int(user_id) in participants and "?" in text and self._has_topic_overlap(text, topic_keywords):
            return True
        if self._looks_like_new_participant_join(text) and self._has_topic_overlap(text, topic_keywords):
            return True
        return False

    def render_discussion_state_hint(self, chat_id: int) -> str:
        thread = self.get_active_discussion(chat_id)
        if not thread:
            return ""
        threads = self._load_threads(chat_id)
        participants = thread.get("participants") or []
        expires_at = int(thread.get("expires_at") or 0)
        ttl = max(0, expires_at - int(time.time()))
        return (
            "Discussion state:\n"
            f"- active_discussion: yes\n"
            f"- tracked_threads: {len(threads)}\n"
            f"- participants: {', '.join(str(item) for item in participants) if participants else 'none'}\n"
            f"- expires_in_seconds: {ttl}\n"
            f"- anchor_message_id: {int(thread.get('anchor_message_id') or 0)}\n"
            f"- reply_to_bot_anchor: {'yes' if int(thread.get('reply_to_bot') or 0) else 'no'}\n"
            f"- topic_keywords: {', '.join(str(item) for item in (thread.get('topic_keywords') or [])[:8]) or 'none'}"
        )
