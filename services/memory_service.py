from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from prompts.builders import build_ai_chat_memory_prompt, build_ai_user_memory_prompt
from utils.text_utils import normalize_whitespace


@dataclass(frozen=True)
class MemoryServiceDeps:
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str]


class MemoryService:
    def __init__(self, deps: MemoryServiceDeps) -> None:
        self.deps = deps

    def refresh_ai_chat_summary(self, bridge: "TelegramBridge", chat_id: int) -> bool:
        rows = bridge.state.get_recent_chat_rows(chat_id, limit=40)
        if len(rows) < 12:
            return False
        current_summary = bridge.state.get_summary(chat_id)
        facts = bridge.state.get_facts(chat_id, limit=6)
        prompt = build_ai_chat_memory_prompt(chat_id, rows, current_summary, facts, self.deps.build_actor_name_func, bridge.truncate_text)
        ai_summary = bridge.run_codex_short(prompt, timeout_seconds=30)
        cleaned = normalize_whitespace(ai_summary)
        if not cleaned:
            return False
        bridge.state.add_summary_snapshot(chat_id, "ai_rollup", cleaned)
        return True

    def refresh_ai_user_memory(self, bridge: "TelegramBridge", chat_id: int) -> bool:
        rows = bridge.state.get_recent_chat_rows(chat_id, limit=80)
        counts: Dict[int, int] = {}
        labels: Dict[int, Tuple[str, str, str]] = {}
        for _created_at, user_id, username, first_name, last_name, role, _message_type, _text in rows:
            if role != "user" or user_id is None:
                continue
            counts[user_id] = counts.get(user_id, 0) + 1
            labels[user_id] = (username or "", first_name or "", last_name or "")
        refreshed = False
        for user_id, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:2]:
            user_rows = bridge.state.get_recent_user_rows(chat_id, user_id, limit=18)
            if len(user_rows) < 6:
                continue
            username, first_name, last_name = labels.get(user_id, ("", "", ""))
            profile_label = self.deps.build_actor_name_func(user_id, username, first_name, last_name, "user")
            heuristic_context = bridge.state.get_user_memory_context(chat_id, user_id=user_id)
            prompt = build_ai_user_memory_prompt(profile_label, user_rows, heuristic_context, bridge.truncate_text)
            ai_summary = bridge.run_codex_short(prompt, timeout_seconds=25)
            cleaned = normalize_whitespace(ai_summary)
            if not cleaned:
                continue
            bridge.state.set_user_memory_ai_summary(chat_id, user_id, cleaned)
            refreshed = True
        return refreshed


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
