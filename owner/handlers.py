import time
from datetime import datetime
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from services.diagnostics_metrics import collect_diagnostics_metrics, render_diagnostics_metrics
from services.failure_detectors import detect_failure_signals, render_failure_signals
from services.repair_playbooks import render_playbook_summary, select_playbooks_for_signals
from services.self_heal_manager import (
    approve_self_heal_incident,
    deny_self_heal_incident,
    render_self_heal_status,
    run_self_heal_playbook,
)
from utils.text_utils import normalize_whitespace, truncate_text


def _ru_flag(flag: str) -> str:
    from tg_codex_bridge import translate_risk_flag
    return translate_risk_flag(flag)


def _ru_visual_text(text: str) -> str:
    from tg_codex_bridge import normalize_visual_analysis_text
    return normalize_visual_analysis_text(text)


class OwnerCommandService:
    def __init__(
        self,
        *,
        owner_user_id: int,
        is_owner_private_chat_func: Callable[[Optional[int], int], bool],
        memory_user_usage_text: str,
        reflections_usage_text: str,
        chat_digest_usage_text: str,
    ) -> None:
        self.owner_user_id = owner_user_id
        self.is_owner_private_chat_func = is_owner_private_chat_func
        self.memory_user_usage_text = memory_user_usage_text
        self.reflections_usage_text = reflections_usage_text
        self.chat_digest_usage_text = chat_digest_usage_text

    def _append_truthfulness_scope(
        self,
        text: str,
        *,
        scope_line: str,
        evidence_lines: List[str],
    ) -> str:
        lines = [(text or "").rstrip(), "", "Границы ответа:"]
        lines.append(f"- {scope_line}")
        lines.extend(f"- {item}" for item in evidence_lines)
        return "\n".join(lines)

    def handle_memory_chat_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, bridge.state.get_chat_memory_context(chat_id, query=query or "") or "Chat memory пока пуста.")
        return True

    def handle_memory_user_command(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        user_id: Optional[int],
        raw_target: str,
        message: Optional[dict],
    ) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_user_id: Optional[int] = None
        cleaned = (raw_target or "").strip()
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if cleaned:
            if cleaned.startswith("@"):
                resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                target_user_id = resolved_id
            else:
                try:
                    target_user_id = int(cleaned)
                except ValueError:
                    resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                    target_user_id = resolved_id
        elif reply_to and not reply_from.get("is_bot"):
            target_user_id = reply_from.get("id")
        else:
            bridge.safe_send_text(chat_id, self.memory_user_usage_text)
            return True
        if target_user_id is None:
            bridge.safe_send_text(chat_id, "Не удалось определить участника в памяти текущего чата.")
            return True
        context = bridge.state.get_user_memory_context(chat_id, user_id=target_user_id)
        if not context:
            bridge.safe_send_text(chat_id, "User memory по этому участнику пока пуста.")
            return True
        bridge.safe_send_text(chat_id, context)
        return True

    def handle_memory_summary_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_summary_memory_context(chat_id, limit=6)
        bridge.safe_send_text(chat_id, context or "Summary memory пока пуста.")
        return True

    def handle_self_state_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, bridge.state.get_self_model_context("enterprise"))
        return True

    def handle_world_state_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        payload = bridge.refresh_world_state_registry("manual_world_state", chat_id=chat_id)
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="world_state_check",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested world state",
            details=f"world_state keys={sorted(payload.keys())}",
            status="ok",
            importance=40,
            open_state="closed",
            tags="owner,world-state",
            observed_payload=payload,
        )
        bridge.safe_send_text(chat_id, bridge.state.get_world_state_context(limit=12) or "World state пока пуст.")
        return True

    def handle_drives_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        scores = bridge.recompute_drive_scores()
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="drive_check",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested drive pressures",
            details=", ".join(f"{key}={value:.1f}" for key, value in sorted(scores.items())),
            status="ok",
            importance=40,
            open_state="closed",
            tags="owner,drives",
        )
        bridge.safe_send_text(chat_id, bridge.state.get_drive_context() or "Drive pressures пока не рассчитаны.")
        return True

    def handle_autobio_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_autobiographical_context(chat_id, query=query or "", limit=8)
        bridge.safe_send_text(chat_id, context or "Autobiographical memory пока пуста.")
        return True

    def handle_skills_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_skill_memory_context(query or "owner operations", route_kind="", limit=6)
        bridge.safe_send_text(chat_id, context or "Skill memory пока пуста.")
        return True

    def handle_reflections_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        limit = 6
        cleaned = (payload or "").strip()
        if cleaned:
            try:
                limit = max(1, min(20, int(cleaned)))
            except ValueError:
                bridge.safe_send_text(chat_id, self.reflections_usage_text)
                return True
        context = bridge.state.get_reflection_context(limit=limit)
        bridge.safe_send_text(chat_id, context or "Reflections пока пусты.")
        return True

    def handle_chat_digest_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        cleaned = (payload or "").strip()
        if not cleaned:
            bridge.safe_send_text(chat_id, self.chat_digest_usage_text)
            return True
        parts = cleaned.split(maxsplit=1)
        try:
            target_chat_id = int(parts[0])
        except ValueError:
            bridge.safe_send_text(chat_id, self.chat_digest_usage_text)
            return True
        day = parts[1].strip() if len(parts) > 1 else ""
        bridge.safe_send_text(chat_id, self.render_chat_digest_text(bridge, target_chat_id, day))
        return True

    def handle_chat_deep_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /chatdeep [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_chat_deep_text(bridge, target_chat_id))
        return True

    def handle_whois_command(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        user_id: Optional[int],
        payload: str,
        message: Optional[dict],
    ) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_user_id = self._resolve_target_user_id(bridge, chat_id, payload, message)
        if target_user_id is None:
            bridge.safe_send_text(chat_id, "Используй: /whois @username, /whois user_id или reply на сообщение участника.")
            return True
        bridge.safe_send_text(chat_id, self.render_whois_text(bridge, chat_id, target_user_id))
        return True

    def handle_profilecheck_command(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        user_id: Optional[int],
        payload: str,
        message: Optional[dict],
    ) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_user_id = self._resolve_target_user_id(bridge, chat_id, payload, message)
        if target_user_id is None:
            bridge.safe_send_text(chat_id, "Используй: /profilecheck @username, /profilecheck user_id или reply на сообщение участника.")
            return True
        bridge.safe_send_text(chat_id, self.render_profilecheck_text(bridge, chat_id, target_user_id))
        return True

    def handle_whats_happening_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, self.render_whats_happening_text(bridge, chat_id, payload))
        return True

    def handle_summary24h_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /summary24h [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_summary24h_text(bridge, target_chat_id))
        return True

    def handle_conflicts_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /conflicts [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_conflicts_text(bridge, target_chat_id))
        return True

    def handle_ownergraph_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        del payload
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, self.render_ownergraph_text(bridge))
        return True

    def handle_watchlist_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /watchlist [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_watchlist_text(bridge, target_chat_id))
        return True

    def handle_reliable_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /reliable [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_reliable_text(bridge, target_chat_id))
        return True

    def handle_suspects_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, payload)
        if target_chat_id is None:
            bridge.safe_send_text(chat_id, "Используй: /suspects [chat_id]. В группе можно без chat_id.")
            return True
        bridge.safe_send_text(chat_id, self.render_suspects_text(bridge, target_chat_id))
        return True

    def handle_achievement_audit_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, self.render_achievement_audit_text(bridge, payload))
        return True

    def render_chat_digest_text(self, bridge: "TelegramBridge", target_chat_id: int, day: str) -> str:
        target_day, rows = bridge.state.get_daily_summary_context(target_chat_id, day)
        if not rows:
            return f"За {target_day} событий не найдено."
        user_rows = [row for row in rows if row[5] == "user"]
        assistant_rows = [row for row in rows if row[5] == "assistant"]
        type_counts: Dict[str, int] = {}
        user_counts: Dict[str, int] = {}
        highlights: list[str] = []
        for created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
            type_counts[message_type] = type_counts.get(message_type, 0) + 1
            if role == "user":
                actor = bridge.build_actor_name(user_id, username or "", first_name or "", last_name or "", role)
                user_counts[actor] = user_counts.get(actor, 0) + 1
                if len(highlights) < 6 and message_type in {"text", "caption", "edited_text", "photo", "voice", "document"}:
                    stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                    highlights.append(f"[{stamp}] {actor}: {truncate_text(content, 120)}")
        top_users = sorted(user_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        top_types = sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        lines = [
            f"Сводка за {target_day}",
            f"ID чата: {target_chat_id}",
            f"Всего событий: {len(rows)}",
            f"Сообщений пользователей: {len(user_rows)}",
            f"Ответов/сервисных действий бота: {len(assistant_rows)}",
        ]
        if top_users:
            lines.append("")
            lines.append("Топ активности:")
            lines.extend(f"- {name}: {count}" for name, count in top_users)
        if top_types:
            lines.append("")
            lines.append("Типы событий:")
            lines.extend(f"- {name}: {count}" for name, count in top_types)
        if highlights:
            lines.append("")
            lines.append("Ключевые куски дня:")
            lines.extend(f"- {item}" for item in highlights)
        return self._append_truthfulness_scope(
            "\n".join(lines),
            scope_line=f"сводка только за {target_day} по найденным chat_events, не по всей истории чата",
            evidence_lines=[
                "прямые наблюдения: события за этот день, типы сообщений, число сообщений по участникам",
                "интерпретация минимальная; это operational digest, а не полный semantic summary всего чата",
            ],
        )

    def render_chat_deep_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        title = bridge.state.get_chat_title(target_chat_id) or str(target_chat_id)
        chat_memory = bridge.state.get_chat_memory_context(target_chat_id, query="расскажи про чат подробно")
        summary_memory = bridge.state.get_summary_memory_context(target_chat_id, limit=4)
        watchlist_text = self.render_watchlist_text(bridge, target_chat_id)
        reliable_text = self.render_reliable_text(bridge, target_chat_id)
        rows = bridge.state.get_recent_chat_rows(target_chat_id, limit=12)
        highlights = []
        for created_at, user_id, username, first_name, last_name, role, message_type, text in rows:
            if role != "user":
                continue
            actor = bridge.build_actor_name(user_id, username or "", first_name or "", last_name or "", role)
            stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
            highlights.append(f"- [{stamp}] {actor}: {truncate_text(normalize_whitespace(text or ''), 160)}")
            if len(highlights) >= 6:
                break
        lines = [
            f"Глубокий профиль чата: {title}",
            f"ID чата: {target_chat_id}",
        ]
        if chat_memory:
            lines.extend(["", chat_memory])
        if summary_memory:
            lines.extend(["", summary_memory])
        if watchlist_text:
            lines.extend(["", watchlist_text])
        if reliable_text:
            lines.extend(["", reliable_text])
        if highlights:
            lines.extend(["", "Последние реплики:", *highlights])
        return self._append_truthfulness_scope(
            "\n".join(lines),
            scope_line="ответ собран из chat memory, summary memory, watchlist/reliable слоёв и последних 12 реплик; это не полный экспорт всей истории",
            evidence_lines=[
                "прямые наблюдения: последние 12 реплик и текущие persisted memory blocks",
                "memory слои могут быть неполными или отстающими по времени относительно полного архива",
            ],
        )

    def render_whois_text(self, bridge: "TelegramBridge", chat_id: int, target_user_id: int) -> str:
        bridge.state.refresh_participant_behavior_profile(target_user_id, chat_id=chat_id)
        label, profile_context = bridge.state.get_participant_profile_context(chat_id, target_user_id=target_user_id, limit=20)
        behavior_context = bridge.state.get_participant_behavior_context(chat_id, target_user_id=target_user_id)
        user_memory = bridge.state.get_user_memory_context(chat_id, user_id=target_user_id, limit=1)
        relation_memory = bridge.state.get_relation_memory_context(chat_id, user_id=target_user_id, query="", limit=4)
        global_rows = bridge.state.get_recent_global_user_rows(target_user_id, limit=12)
        global_chats: Dict[int, int] = {}
        for created_at, user_id, username, first_name, last_name, message_type, text in global_rows:
            del created_at, user_id, username, first_name, last_name, message_type, text
        with bridge.state.db_lock:
            chat_rows = bridge.state.db.execute(
                """
                SELECT e.chat_id, COALESCE(MAX(NULLIF(c.chat_title, '')), '') AS chat_title, COUNT(*) AS cnt
                FROM chat_events e
                LEFT JOIN chat_runtime_cache c ON c.chat_id = e.chat_id
                WHERE e.role = 'user' AND e.user_id = ?
                GROUP BY e.chat_id
                ORDER BY cnt DESC
                LIMIT 6
                """,
                (target_user_id,),
            ).fetchall()
        lines = [f"Whois: {label or f'user_id={target_user_id}'}", f"Профиль участника: {label or f'user_id={target_user_id}'}"]
        if behavior_context:
            lines.extend(["", behavior_context])
        if user_memory:
            lines.extend(["", user_memory])
        if relation_memory:
            lines.extend(["", relation_memory])
        if chat_rows:
            lines.append("")
            lines.append("Где замечен:")
            for row in chat_rows:
                chat_title = normalize_whitespace(row["chat_title"] or "") or str(int(row["chat_id"] or 0))
                lines.append(f"- {truncate_text(chat_title, 80)}: сообщений={int(row['cnt'] or 0)}; ID чата={int(row['chat_id'] or 0)}")
        if profile_context:
            lines.extend(["", profile_context])
        return self._append_truthfulness_scope(
            "\n".join(lines),
            scope_line="профиль собран из participant profile, behavior signals, user/relation memory и recent global presence, а не из полного ручного аудита всей истории",
            evidence_lines=[
                "прямые наблюдения: persisted profile rows, behavior signals, chat presence counts",
                "интерпретация: user/relation memory и behavior profile могут содержать агрегированные эвристики",
            ],
        )

    def render_whats_happening_text(self, bridge: "TelegramBridge", chat_id: int, payload: str) -> str:
        cleaned = (payload or "").strip()
        target_chat_id = self._resolve_target_chat_id(bridge, chat_id, cleaned)
        if target_chat_id is not None:
            return self.render_chat_deep_text(bridge, target_chat_id)
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                """
                SELECT e.chat_id, COALESCE(MAX(NULLIF(c.chat_title, '')), '') AS chat_title,
                       COUNT(*) AS cnt, MAX(e.created_at) AS last_ts
                FROM chat_events e
                LEFT JOIN chat_runtime_cache c ON c.chat_id = e.chat_id
                WHERE e.role = 'user' AND e.chat_id < 0 AND e.created_at >= strftime('%s','now') - 86400
                GROUP BY e.chat_id
                ORDER BY last_ts DESC
                LIMIT 8
                """
            ).fetchall()
            summary_rows = bridge.state.db.execute(
                """
                SELECT s.chat_id, s.summary
                FROM summary_snapshots s
                JOIN (
                    SELECT chat_id, MAX(id) AS max_id
                    FROM summary_snapshots
                    WHERE scope IN ('rolling', 'group_deep_profile')
                    GROUP BY chat_id
                ) latest ON latest.chat_id = s.chat_id AND latest.max_id = s.id
                ORDER BY s.created_at DESC
                LIMIT 12
                """
            ).fetchall()
        summary_map = {int(row["chat_id"] or 0): normalize_whitespace(row["summary"] or "") for row in summary_rows}
        if not rows:
            return "За последние 24 часа по группам почти нет движения."
        lines = ["Что происходит по чатам за 24 часа:"]
        for row in rows:
            chat_id_value = int(row["chat_id"] or 0)
            chat_title = normalize_whitespace(row["chat_title"] or "") or str(chat_id_value)
            stamp = datetime.fromtimestamp(int(row["last_ts"] or 0)).strftime("%m-%d %H:%M") if row["last_ts"] else "--:--"
            lines.append(f"- {truncate_text(chat_title, 80)}: сообщений={int(row['cnt'] or 0)}; last={stamp}; chat_id={chat_id_value}")
            summary_text = summary_map.get(chat_id_value, "")
            if summary_text:
                lines.append(f"  {truncate_text(summary_text, 220)}")
        return self._append_truthfulness_scope(
            "\n".join(lines),
            scope_line="это обзор только по групповой активности за последние 24 часа, а не по всей истории всех чатов",
            evidence_lines=[
                "прямые наблюдения: user chat_events за последние 24 часа",
                "summary строки взяты из последних persisted summary snapshots и могут быть старше текущих последних сообщений",
            ],
        )

    def render_summary24h_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        return self.render_chat_digest_text(bridge, target_chat_id, "")

    def render_conflicts_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        rows = bridge.state.get_recent_chat_rows(target_chat_id, limit=80)
        if not rows:
            return "По этому чату пока нет данных."
        rough_counts: Dict[str, int] = {}
        reply_pairs: Dict[str, int] = {}
        conflict_examples: list[str] = []
        for created_at, user_id, username, first_name, last_name, role, message_type, text in rows:
            if role != "user":
                continue
            actor = bridge.build_actor_name(user_id, username or "", first_name or "", last_name or "", role)
            cleaned = normalize_whitespace(text or "")
            lowered = cleaned.lower()
            if any(token in lowered for token in ("нах", "охуе", "говно", "заеб", "пизд", "заткнись", "иди ты")):
                rough_counts[actor] = rough_counts.get(actor, 0) + 1
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                conflict_examples.append(f"- [{stamp}] {actor}: {truncate_text(cleaned, 140)}")
        with bridge.state.db_lock:
            pair_rows = bridge.state.db.execute(
                """
                SELECT e.user_id, e.username, e.first_name, e.last_name, e.reply_to_user_id, COUNT(*) AS cnt
                FROM chat_events e
                WHERE e.chat_id = ? AND e.role = 'user' AND e.reply_to_user_id IS NOT NULL
                GROUP BY e.user_id, e.username, e.first_name, e.last_name, e.reply_to_user_id
                ORDER BY cnt DESC
                LIMIT 6
                """,
                (target_chat_id,),
            ).fetchall()
        for row in pair_rows:
            source = bridge.build_actor_name(row["user_id"], row["username"] or "", row["first_name"] or "", row["last_name"] or "", "user")
            target = bridge.state.resolve_chat_user(target_chat_id, str(int(row["reply_to_user_id"] or 0)))[1] or f"user_id={int(row['reply_to_user_id'] or 0)}"
            reply_pairs[f"{source} -> {target}"] = int(row["cnt"] or 0)
        title = bridge.state.get_chat_title(target_chat_id) or str(target_chat_id)
        lines = [f"Конфликты и трение: {title}", f"chat_id: {target_chat_id}"]
        if rough_counts:
            lines.append("")
            lines.append("Грубые/жёсткие реплики:")
            for name, count in sorted(rough_counts.items(), key=lambda item: (-item[1], item[0]))[:6]:
                lines.append(f"- {name}: {count}")
        if reply_pairs:
            lines.append("")
            lines.append("Самые напряжённые reply-пары:")
            for pair, count in sorted(reply_pairs.items(), key=lambda item: (-item[1], item[0]))[:6]:
                lines.append(f"- {pair}: {count}")
        if conflict_examples:
            lines.append("")
            lines.append("Примеры:")
            lines.extend(conflict_examples[:5])
        if len(lines) == 2:
            lines.extend(["", "Явных конфликтных сигналов в последних сообщениях не видно."])
        return self._append_truthfulness_scope(
            "\n".join(lines),
            scope_line="анализ конфликтов идёт только по последним 80 сообщениям и top reply-парам из базы, не по всей истории чата",
            evidence_lines=[
                "прямые наблюдения: грубая лексика в последних сообщениях и reply counts из chat_events",
                "напряжённые пары и конфликтность являются эвристикой, а не доказанным намерением участников",
            ],
        )

    def render_ownergraph_text(self, bridge: "TelegramBridge") -> str:
        cross_chat = bridge.state.get_owner_cross_chat_memory_context(limit=6)
        if not cross_chat:
            return "Граф владельца пока пуст."
        lines = [
            "Граф владельца:",
            "Это кросс-чат слой по Дмитрию: где он активен и с кем чаще всего пересекается.",
            "",
            cross_chat,
        ]
        return "\n".join(lines)

    def render_watchlist_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                """
                SELECT user_id, display_name, conflict_score, toxicity_score, spam_score, flood_score,
                       instability_score, helpfulness_score, credibility_score, risk_flags_json, notes_summary, message_count
                FROM participant_chat_profiles
                WHERE chat_id = ?
                ORDER BY (toxicity_score + conflict_score + spam_score + flood_score + instability_score) DESC,
                         helpfulness_score ASC,
                         credibility_score ASC,
                         message_count DESC
                LIMIT 12
                """,
                (target_chat_id,),
            ).fetchall()
        if not rows:
            return "По этому чату профили риска пока не собраны."
        lines = [f"Watchlist / Проблемные участники по чату {target_chat_id}:"]
        for row in rows:
            risk_total = int(row["conflict_score"] or 0) + int(row["toxicity_score"] or 0) + int(row["spam_score"] or 0) + int(row["flood_score"] or 0) + int(row["instability_score"] or 0)
            if risk_total <= 0:
                continue
            flags = ", ".join(_ru_flag(flag) for flag in __import__("json").loads(row["risk_flags_json"] or "[]")) or "нет"
            lines.append(
                f"- {truncate_text(row['display_name'] or str(int(row['user_id'] or 0)), 80)}: риск={risk_total}; конфликт={int(row['conflict_score'] or 0)}; токсичность={int(row['toxicity_score'] or 0)}; спам={int(row['spam_score'] or 0)}; флуд={int(row['flood_score'] or 0)}; флаги={flags}"
            )
            if row["notes_summary"]:
                lines.append(f"  {truncate_text(row['notes_summary'], 180)}")
        return "\n".join(lines) if len(lines) > 1 else f"По чату {target_chat_id} явных проблемных участников не видно."

    def render_reliable_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                """
                SELECT user_id, display_name, helpfulness_score, credibility_score, conflict_score, toxicity_score,
                       spam_score, flood_score, risk_flags_json, notes_summary
                FROM participant_chat_profiles
                WHERE chat_id = ?
                ORDER BY credibility_score DESC, helpfulness_score DESC, conflict_score ASC, toxicity_score ASC
                LIMIT 12
                """,
                (target_chat_id,),
            ).fetchall()
        if not rows:
            return "По этому чату профили надёжности пока не собраны."
        lines = [f"Reliable / Надёжные участники по чату {target_chat_id}:"]
        added = 0
        for row in rows:
            if int(row["credibility_score"] or 0) <= 0 and int(row["helpfulness_score"] or 0) <= 0:
                continue
            flags = ", ".join(_ru_flag(flag) for flag in __import__("json").loads(row["risk_flags_json"] or "[]")) or "нет"
            lines.append(
                f"- {truncate_text(row['display_name'] or str(int(row['user_id'] or 0)), 80)}: доверие={int(row['credibility_score'] or 0)}; полезность={int(row['helpfulness_score'] or 0)}; конфликт={int(row['conflict_score'] or 0)}; токсичность={int(row['toxicity_score'] or 0)}; флаги={flags}"
            )
            if row["notes_summary"]:
                lines.append(f"  {truncate_text(row['notes_summary'], 180)}")
            added += 1
        return "\n".join(lines) if added else f"По чату {target_chat_id} пока нет выраженно надёжных участников."

    def render_suspects_text(self, bridge: "TelegramBridge", target_chat_id: int) -> str:
        title = bridge.state.get_chat_title(target_chat_id)
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                """
                SELECT user_id, display_name, username, risk_flags_json, notes_summary,
                       message_count, spam_score, conflict_score, instability_score
                FROM participant_chat_profiles
                WHERE chat_id = ?
                ORDER BY
                    CASE
                        WHEN risk_flags_json LIKE '%scam_risk%' THEN 5
                        WHEN risk_flags_json LIKE '%likely_bot_like%' THEN 4
                        WHEN risk_flags_json LIKE '%sexual_bait%' THEN 3
                        WHEN risk_flags_json LIKE '%suspicious_visual%' THEN 2
                        ELSE 0
                    END DESC,
                    spam_score DESC,
                    conflict_score DESC,
                    instability_score DESC,
                    message_count DESC
                LIMIT 10
                """,
                (target_chat_id,),
            ).fetchall()
            visual_rows = bridge.state.db.execute(
                """
                SELECT user_id, analysis_text
                FROM participant_visual_signals
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT 32
                """,
                (target_chat_id,),
            ).fetchall()
        visual_map: Dict[int, str] = {}
        for row in visual_rows:
            uid = int(row["user_id"] or 0)
            if uid not in visual_map:
                visual_map[uid] = truncate_text(_ru_visual_text(row["analysis_text"] or ""), 180)
        lines = [f"Подозрительные участники: {title}", f"ID чата: {target_chat_id}"]
        added = 0
        for row in rows:
            flags = __import__("json").loads(row["risk_flags_json"] or "[]")
            if not any(flag in flags for flag in ("scam_risk", "likely_bot_like", "sexual_bait", "suspicious_visual")):
                continue
            label = row["display_name"] or (f"@{row['username']}" if row["username"] else str(int(row["user_id"] or 0)))
            ru_flags = ", ".join(_ru_flag(flag) for flag in flags[:6]) or "нет"
            lines.append(
                f"- {truncate_text(label, 80)}: флаги={ru_flags}; сообщений={int(row['message_count'] or 0)}; спам={int(row['spam_score'] or 0)}; конфликт={int(row['conflict_score'] or 0)}; нестабильность={int(row['instability_score'] or 0)}"
            )
            if row["notes_summary"]:
                lines.append(f"  {truncate_text(row['notes_summary'], 180)}")
            if int(row["user_id"] or 0) in visual_map:
                lines.append(f"  визуально: {visual_map[int(row['user_id'] or 0)]}")
            added += 1
        return "\n".join(lines) if added else f"По чату {target_chat_id} явных подозрительных/scam/bait сигналов пока не видно."

    def render_profilecheck_text(self, bridge: "TelegramBridge", chat_id: int, target_user_id: int) -> str:
        base = self.render_whois_text(bridge, chat_id, target_user_id)
        with bridge.state.db_lock:
            visual_rows = bridge.state.db.execute(
                """
                SELECT chat_id, analysis_text, risk_flags_json, media_sha256
                FROM participant_visual_signals
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 6
                """,
                (target_user_id,),
            ).fetchall()
            duplicate_rows = bridge.state.db.execute(
                """
                SELECT media_sha256, COUNT(*) AS cnt, COUNT(DISTINCT user_id) AS users
                FROM participant_visual_signals
                WHERE user_id = ? AND media_sha256 != ''
                GROUP BY media_sha256
                HAVING COUNT(*) >= 2 OR COUNT(DISTINCT user_id) >= 1
                ORDER BY users DESC, cnt DESC
                LIMIT 4
                """,
                (target_user_id,),
            ).fetchall()
        lines = [base, "", "Проверка профиля:"]
        if visual_rows:
            lines.append("Визуальная память:")
            for row in visual_rows[:3]:
                flags = ", ".join(_ru_flag(flag) for flag in __import__("json").loads(row["risk_flags_json"] or "[]")[:5]) or "нет"
                lines.append(f"- ID чата={int(row['chat_id'] or 0)}; флаги={flags}; {truncate_text(_ru_visual_text(row['analysis_text'] or ''), 180)}")
        if duplicate_rows:
            lines.append("")
            lines.append("Повторы медиа:")
            for row in duplicate_rows:
                lines.append(f"- sha256={str(row['media_sha256'])[:16]}...; повторов={int(row['cnt'] or 0)}")
        return "\n".join(lines)

    def render_achievement_audit_text(self, bridge: "TelegramBridge", payload: str) -> str:
        cleaned = (payload or "").strip()
        try:
            limit = max(5, min(50, int(cleaned or "12")))
        except ValueError:
            limit = 12
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                """
                SELECT se.user_id, se.chat_id, se.reason, se.metadata_json, se.created_at,
                       COALESCE(NULLIF(p.first_name, ''), NULLIF(p.username, ''), CAST(se.user_id AS TEXT)) AS actor_name,
                       COALESCE(NULLIF(c.chat_title, ''), CAST(se.chat_id AS TEXT)) AS chat_title
                FROM score_events se
                LEFT JOIN progression_profiles p ON p.user_id = se.user_id
                LEFT JOIN chat_runtime_cache c ON c.chat_id = se.chat_id
                WHERE se.event_type = 'achievement_unlock'
                ORDER BY se.created_at DESC, se.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        if not rows:
            return "Аудит ачивок пока пуст."
        lines = ["Аудит ачивок:", ""]
        for row in rows:
            created_at = int(row["created_at"] or 0)
            stamp = datetime.fromtimestamp(created_at).strftime("%m-%d %H:%M") if created_at else "--:--"
            try:
                metadata = __import__("json").loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            rarity = str(metadata.get("rarity") or "").strip()
            code = str(metadata.get("code") or "").strip()
            actor_name = truncate_text(str(row["actor_name"] or f"user_id={int(row['user_id'] or 0)}"), 48)
            chat_title = truncate_text(str(row["chat_title"] or str(int(row["chat_id"] or 0))), 48)
            lines.append(f"- [{stamp}] {actor_name} — {row['reason']}")
            lines.append(f"  Чат: {chat_title}")
            if code or rarity:
                lines.append(f"  code={code or '-'}; rarity={rarity or '-'}")
        lines.extend([
            "",
            "Если после рестарта здесь нет новой дублирующей записи, значит рестарт не переоткрывал ачивку, а проблема была только в старом announce/runtime слое."
        ])
        return "\n".join(lines)

    def _resolve_target_chat_id(self, bridge: "TelegramBridge", chat_id: int, payload: str) -> Optional[int]:
        cleaned = (payload or "").strip()
        if cleaned:
            try:
                return int(cleaned.split()[0])
            except ValueError:
                return None
        if chat_id < 0:
            return chat_id
        return None

    def _resolve_target_user_id(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        payload: str,
        message: Optional[dict],
    ) -> Optional[int]:
        cleaned = (payload or "").strip()
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if cleaned:
            if cleaned.startswith("@"):
                resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                return resolved_id
            try:
                return int(cleaned)
            except ValueError:
                resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                return resolved_id
        if reply_to and not reply_from.get("is_bot"):
            return reply_from.get("id")
        return None

    def handle_owner_report_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        payload = bridge.refresh_world_state_registry("owner_report", chat_id=chat_id)
        scores = bridge.recompute_drive_scores(payload)
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="owner_report",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested operational report",
            details=f"errors={payload.get('recent_errors_count', 0)}; git_dirty={payload.get('git_dirty_count', 0)}; runtime_risk={scores.get('runtime_risk_pressure', 0):.1f}",
            status="ok",
            importance=55,
            open_state="closed",
            tags="owner,report,runtime",
            observed_payload=payload,
        )
        bridge.safe_send_text(chat_id, self.render_owner_report_text(bridge, chat_id))
        return True

    def handle_repair_status_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self_heal_summary = bridge.run_self_heal_cycle("owner_repair_status", auto_execute=False)
        runtime_snapshot = bridge.inspect_runtime_log()
        recent_errors = bridge.read_recent_log_highlights(limit=10)
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=8)
        signals = detect_failure_signals(
            runtime_snapshot=runtime_snapshot,
            recent_errors=recent_errors,
            recent_routes=recent_routes,
            heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
        )
        playbooks = select_playbooks_for_signals(signals)
        if signals:
            for signal in signals:
                bridge.state.record_repair_journal(
                    signal_code=signal.signal_code,
                    playbook_id=signal.suggested_playbook,
                    status="detected",
                    summary=signal.summary,
                    evidence=signal.evidence,
                    verification_result="signal_detected_only",
                    notes="repair not executed automatically",
                )
        lines = [
            self_heal_summary,
            "",
            render_failure_signals(signals),
            "",
            render_playbook_summary(playbooks),
        ]
        recent_journal = bridge.state.get_recent_repair_journal(limit=6)
        if recent_journal:
            lines.extend(["", "Repair journal"])
            for row in recent_journal:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] signal={row['signal_code'] or '-'} playbook={row['playbook_id'] or '-'} status={row['status'] or '-'}"
                )
                if row["summary"]:
                    lines.append(f"  {truncate_text(row['summary'], 200)}")
        incidents = bridge.state.get_recent_self_heal_incidents(limit=6)
        if incidents:
            lines.extend(["", "Инциденты автовосстановления"])
            for row in incidents:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] incident={int(row['id'])} problem={row['problem_type']} state={row['state']} autonomy={row['autonomy_level']}"
                )
        bridge.safe_send_text(chat_id, "\n".join(lines))
        return True

    def handle_quality_report_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        display_timezone = ZoneInfo("Europe/Moscow")
        bridge.refresh_world_state_registry("quality_report", chat_id=chat_id)
        diagnostics_metrics = collect_diagnostics_metrics(bridge.state, window_seconds=86400)
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=8)
        world_state_context = bridge.state.get_world_state_context(limit=8)
        lines = [
            "ОТЧЁТ ПО КАЧЕСТВУ",
            f"Время: {datetime.now(display_timezone).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "",
            render_diagnostics_metrics(diagnostics_metrics),
        ]
        if world_state_context:
            lines.extend(["", world_state_context])
        if recent_routes:
            lines.extend(["", "Последние решения маршрутизации:", bridge.render_route_diagnostics_rows(recent_routes)])
        bridge.safe_send_text(chat_id, "\n".join(lines))
        return True

    def handle_self_heal_status_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        bridge.safe_send_text(chat_id, render_self_heal_status(bridge, limit=10))
        return True

    def handle_self_heal_run_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        cleaned = (payload or "").strip()
        if not cleaned:
            bridge.safe_send_text(chat_id, "Используй: /selfhealrun <playbook|incident_id> [dry-run|execute]")
            return True
        parts = cleaned.split()
        selector = parts[0]
        mode = parts[1].strip().lower() if len(parts) > 1 else "dry-run"
        execute = mode == "execute"
        bridge.safe_send_text(chat_id, run_self_heal_playbook(bridge, selector=selector, execute=execute))
        return True

    def handle_self_heal_approve_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        cleaned = (payload or "").strip()
        if not cleaned.isdigit():
            bridge.safe_send_text(chat_id, "Используй: /selfhealapprove <incident_id>")
            return True
        bridge.safe_send_text(chat_id, approve_self_heal_incident(bridge, incident_id=int(cleaned)))
        return True

    def handle_self_heal_deny_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        cleaned = (payload or "").strip()
        if not cleaned.isdigit():
            bridge.safe_send_text(chat_id, "Используй: /selfhealdeny <incident_id>")
            return True
        bridge.safe_send_text(chat_id, deny_self_heal_incident(bridge, incident_id=int(cleaned)))
        return True

    def render_owner_report_text(self, bridge: "TelegramBridge", chat_id: int) -> str:
        display_timezone = ZoneInfo("Europe/Moscow")
        operational_state = bridge.refresh_world_state_registry("owner_report_render", chat_id=chat_id)
        bridge.recompute_drive_scores(operational_state)
        status_snapshot = bridge.state.get_status_snapshot(chat_id)
        last_backup_raw = bridge.state.get_meta("last_backup_ts", "0")
        try:
            last_backup_value = float(last_backup_raw or "0")
        except ValueError:
            last_backup_value = 0.0
        backup_text = (
            datetime.fromtimestamp(last_backup_value, tz=display_timezone).strftime("%Y-%m-%d %H:%M:%S %Z")
            if last_backup_value > 0
            else "ещё не было"
        )
        backup_age_hours = ((time.time() - last_backup_value) / 3600.0) if last_backup_value > 0 else -1.0
        runtime_snapshot = bridge.inspect_runtime_log()
        recent_errors = bridge.read_recent_log_highlights(limit=8)
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=5)
        diagnostics_metrics = collect_diagnostics_metrics(bridge.state, window_seconds=86400)
        failure_signals = detect_failure_signals(
            runtime_snapshot=runtime_snapshot,
            recent_errors=recent_errors,
            recent_routes=recent_routes,
            heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
            heartbeat_exists=bridge.heartbeat_path.exists(),
        )
        repair_playbooks = select_playbooks_for_signals(failure_signals)
        repair_journal = bridge.state.get_recent_repair_journal(limit=4)
        self_heal_incidents = bridge.state.get_recent_self_heal_incidents(limit=4)
        lines = [
            "ОТЧЁТ ВЛАДЕЛЬЦА",
            f"Время: {datetime.now(display_timezone).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "",
            self.render_owner_identity_text(bridge),
            "",
            f"Режим чата: {bridge.state.get_mode(chat_id)}",
            f"События в этом чате: {status_snapshot['events_count']}",
            f"Факты в этом чате: {status_snapshot['facts_count']}",
            f"История в этом чате: {status_snapshot['history_count']}",
            f"Профили памяти пользователей в этом чате: {status_snapshot['user_memory_profiles']}",
            f"Связи relation-memory в этом чате: {status_snapshot['relation_memory_rows']}",
            f"Слепки summary memory в этом чате: {status_snapshot['summary_snapshots']}",
            f"Автобиографические события: {status_snapshot['autobiographical_rows']}",
            f"Рефлексии: {status_snapshot['reflections_rows']}",
            f"Записи world-state: {status_snapshot['world_state_rows']}",
            f"Всего событий в БД: {status_snapshot['total_events']}",
            f"Решения маршрутизации в БД: {status_snapshot['total_route_decisions']}",
            f"Upgrade активен: {'да' if bridge.state.global_upgrade_active else 'нет'}",
            f"Heartbeat: {bridge.config.heartbeat_path}",
            f"Heartbeat timeout: {bridge.config.heartbeat_timeout_seconds}с",
            f"Последний backup: {backup_text}",
            (
                f"Возраст backup: {backup_age_hours:.1f} ч"
                if backup_age_hours >= 0
                else "Возраст backup: n/a"
            ),
            "",
            "Ресурсы:",
            bridge.render_resource_summary(),
            "",
            bridge.render_bridge_runtime_watch(),
        ]
        world_state_context = bridge.state.get_world_state_context(limit=6)
        drive_context = bridge.state.get_drive_context()
        if world_state_context:
            lines.extend(["", world_state_context])
        if drive_context:
            lines.extend(["", drive_context])
        lines.extend(["", render_diagnostics_metrics(diagnostics_metrics)])
        if recent_routes:
            lines.extend(["", "Последние решения маршрутизации:", bridge.render_route_diagnostics_rows(recent_routes)])
        lines.extend(["", render_failure_signals(failure_signals), "", render_playbook_summary(repair_playbooks)])
        if repair_journal:
            lines.append("")
            lines.append("Последние записи repair journal:")
            for row in repair_journal:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] signal={row['signal_code'] or '-'} playbook={row['playbook_id'] or '-'} status={row['status'] or '-'}"
                )
        if self_heal_incidents:
            lines.append("")
            lines.append("Последние инциденты автовосстановления:")
            for row in self_heal_incidents:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] incident={int(row['id'])} problem={row['problem_type']} state={row['state']} playbook={row['suggested_playbook'] or '-'}"
                )
        if recent_errors:
            lines.extend(["", "Недавние ошибки/сбои:", *[f"- {item}" for item in recent_errors]])
        else:
            lines.extend(["", "Недавние ошибки/сбои:", "- Явных ошибок в хвосте лога не найдено."])
        if int(runtime_snapshot.get("warning_count", 0)):
            lines.extend(["", "Недавние восстанавливаемые предупреждения:", *[f"- {item}" for item in runtime_snapshot.get("recent_warning_lines", [])[-5:]]])
        return "\n".join(lines)

    def render_owner_identity_text(self, bridge: "TelegramBridge") -> str:
        owner_ids: List[int] = [int(bridge.owner_user_id)]
        for alias_id in getattr(bridge, "owner_alias_user_ids", ()):
            alias_int = int(alias_id)
            if alias_int not in owner_ids:
                owner_ids.append(alias_int)
        placeholders = ",".join("?" for _ in owner_ids)
        with bridge.state.db_lock:
            rows = bridge.state.db.execute(
                f"""
                SELECT chat_id, user_id, username, first_name, last_name, last_status
                FROM chat_participants
                WHERE user_id IN ({placeholders})
                ORDER BY chat_id ASC, user_id ASC
                """,
                tuple(owner_ids),
            ).fetchall()
        grouped: Dict[int, List[object]] = {}
        for row in rows:
            grouped.setdefault(int(row["user_id"]), []).append(row)
        lines = ["OWNER IDENTITY"]
        for owner_id in owner_ids:
            profile_rows = grouped.get(owner_id, [])
            label = None
            for row in profile_rows:
                label = bridge.build_actor_name(
                    owner_id,
                    row["username"] or "",
                    row["first_name"] or "",
                    row["last_name"] or "",
                    "user",
                )
                if label:
                    break
            if not label:
                label = f"user_id={owner_id}"
            role = "primary owner" if owner_id == int(bridge.owner_user_id) else "owner alias"
            lines.append(f"• {label} — {role}")
            if not profile_rows:
                lines.append("  Чаты: пока нет записей в chat_participants.")
                continue
            chat_lines: List[str] = []
            for row in profile_rows[:8]:
                chat_id = int(row["chat_id"])
                chat_title = bridge.state.get_chat_title(chat_id)
                if chat_title.startswith("chat_id=") and chat_id > 0:
                    chat_title = f"личка {chat_id}"
                status = (row["last_status"] or "member").strip() or "member"
                human_status = {
                    "creator": "создатель",
                    "administrator": "админ",
                    "member": "участник",
                }.get(status, status)
                moderation_note = " • бот не модерирует" if status in {"creator", "administrator"} else ""
                chat_lines.append(f"{truncate_text(chat_title, 42)} [{human_status}{moderation_note}]")
            lines.append("  Чаты: " + "; ".join(chat_lines))
        return "\n".join(lines)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
