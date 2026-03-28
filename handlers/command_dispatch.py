import time
from typing import Optional

from handlers.command_parsers import (
    parse_achievement_audit_command,
    parse_autobio_command,
    parse_chat_watch_command,
    parse_chat_deep_command,
    parse_chat_digest_command,
    parse_console_command,
    parse_conflicts_command,
    parse_daily_command,
    parse_digest_command,
    parse_drives_command,
    parse_errors_command,
    parse_events_command,
    parse_git_last_command,
    parse_git_status_command,
    parse_history_command,
    parse_memory_chat_command,
    parse_memory_summary_command,
    parse_memory_user_command,
    parse_moderation_command,
    parse_owner_autofix_command,
    parse_ownergraph_command,
    parse_password_command,
    parse_profilecheck_command,
    parse_recall_command,
    parse_reflections_command,
    parse_remember_command,
    parse_routes_command,
    parse_sd_list_command,
    parse_sd_save_command,
    parse_sd_send_command,
    parse_search_command,
    parse_self_state_command,
    parse_self_heal_run_command,
    parse_self_heal_status_command,
    parse_self_heal_approve_command,
    parse_self_heal_deny_command,
    parse_skills_command,
    parse_suspects_command,
    parse_summary24h_command,
    parse_reliable_command,
    parse_upgrade_command,
    parse_warn_command,
    parse_watchlist_command,
    parse_whats_happening_command,
    parse_whois_command,
    parse_who_said_command,
    parse_world_state_command,
)


class CommandDispatcher:
    def __init__(self, *, owner_username: str, public_help_text: str, mode_prompts: dict[str, str]) -> None:
        self.owner_username = owner_username
        self.public_help_text = public_help_text
        self.mode_prompts = mode_prompts

    def handle_command(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        user_id: Optional[int],
        text: str,
        message: Optional[dict] = None,
        allow_followup_text: bool = False,
    ) -> bool:
        has_access = bridge.has_chat_access(bridge.state.authorized_user_ids, user_id)
        if text.startswith("/start"):
            if user_id is not None:
                bridge.open_control_panel(chat_id, user_id, "home")
            return True
        if text == "/rating" and user_id is not None:
            bridge.open_control_panel(chat_id, user_id, "profile")
            return True
        if text == "/top":
            if user_id is not None:
                bridge.open_control_panel(chat_id, user_id, "top_all")
            return True
        if text == "/topweek":
            if user_id is not None:
                bridge.open_control_panel(chat_id, user_id, "top_week")
            return True
        if text == "/topday":
            if user_id is not None:
                bridge.open_control_panel(chat_id, user_id, "top_day")
            return True
        if text == "/help":
            if user_id is not None and has_access:
                bridge.open_control_panel(chat_id, user_id, "home")
            return True
        if text == "/rules":
            if has_access:
                bridge.safe_send_text(chat_id, bridge.get_group_rules_text(message))
            return True
        if text == "/commands":
            if not has_access:
                return True
            return bridge.handle_commands_command(chat_id, user_id)
        if text == "/appeals":
            if has_access:
                return bridge.handle_appeal_admin_command(chat_id, user_id, text)
            if user_id is not None:
                bridge.open_control_panel(chat_id, user_id, "appeals")
            return True
        if text.startswith("/appeal_review") or text.startswith("/appeal_approve") or text.startswith("/appeal_reject"):
            if not has_access:
                return True
            return bridge.handle_appeal_admin_command(chat_id, user_id, text)
        owner_autofix_payload = parse_owner_autofix_command(text)
        if owner_autofix_payload is not None:
            return bridge.handle_owner_autofix_command(chat_id, user_id, owner_autofix_payload)
        password_value = parse_password_command(text)
        if password_value is not None:
            bridge.safe_send_text(chat_id, f"Вход по паролю отключён. Бот отвечает только владельцу {self.owner_username}.")
            return True
        if not has_access:
            if text.startswith("/appeal"):
                return bridge.handle_appeal_command(chat_id, user_id, text)
            return True
        if text == "/ping":
            bridge.safe_send_text(chat_id, f"pong\n\n🏓 {bridge.get_telegram_ping_text()}")
            return True
        if text == "/restart":
            return bridge.handle_restart_command(chat_id, user_id)
        if text == "/status":
            return bridge.handle_status_command(chat_id)
        if text == "/repairstatus":
            return bridge.handle_repair_status_command(chat_id, user_id)
        if parse_self_heal_status_command(text):
            return bridge.handle_self_heal_status_command(chat_id, user_id)
        self_heal_run_value = parse_self_heal_run_command(text)
        if self_heal_run_value is not None:
            return bridge.handle_self_heal_run_command(chat_id, user_id, self_heal_run_value)
        self_heal_approve_value = parse_self_heal_approve_command(text)
        if self_heal_approve_value is not None:
            return bridge.handle_self_heal_approve_command(chat_id, user_id, self_heal_approve_value)
        self_heal_deny_value = parse_self_heal_deny_command(text)
        if self_heal_deny_value is not None:
            return bridge.handle_self_heal_deny_command(chat_id, user_id, self_heal_deny_value)
        if text == "/qualityreport":
            return bridge.handle_quality_report_command(chat_id, user_id)
        if text == "/stats":
            bridge.safe_send_text(chat_id, bridge.legacy.render_stats())
            return True
        if text == "/achievements" and user_id is not None:
            bridge.open_control_panel(chat_id, user_id, "achievements")
            return True
        if text.startswith("/appeal"):
            return bridge.handle_appeal_command(chat_id, user_id, text)
        if parse_chat_watch_command(text):
            return bridge.handle_recent_chat_report_command(chat_id, user_id, text, message)
        remember_value = parse_remember_command(text)
        if remember_value is not None:
            return bridge.handle_remember_command(chat_id, user_id, remember_value)
        recall_value = parse_recall_command(text)
        if recall_value is not None:
            return bridge.handle_recall_command(chat_id, user_id, recall_value)
        search_value = parse_search_command(text)
        if search_value is not None:
            return bridge.handle_search_command(chat_id, search_value)
        console_value = parse_console_command(text)
        if console_value is not None:
            return bridge.handle_console_command(chat_id, user_id, console_value)
        if parse_git_status_command(text):
            return bridge.handle_git_status_command(chat_id, user_id)
        git_last_value = parse_git_last_command(text)
        if git_last_value is not None:
            return bridge.handle_git_last_command(chat_id, user_id, git_last_value)
        errors_value = parse_errors_command(text)
        if errors_value is not None:
            return bridge.handle_errors_command(chat_id, user_id, errors_value)
        events_value = parse_events_command(text)
        if events_value is not None:
            return bridge.handle_events_command(chat_id, user_id, events_value)
        if text == "/resources":
            return bridge.handle_resources_command(chat_id, user_id)
        if text == "/topproc":
            return bridge.handle_topproc_command(chat_id, user_id)
        if text == "/disk":
            return bridge.handle_disk_command(chat_id, user_id)
        if text == "/net":
            return bridge.handle_net_command(chat_id, user_id)
        sd_list_value = parse_sd_list_command(text)
        if sd_list_value is not None:
            return bridge.handle_sd_list_command(chat_id, user_id, sd_list_value)
        sd_send_value = parse_sd_send_command(text)
        if sd_send_value is not None:
            return bridge.handle_sd_send_command(chat_id, user_id, sd_send_value)
        sd_save_value = parse_sd_save_command(text)
        if sd_save_value is not None:
            return bridge.handle_sd_save_command(chat_id, user_id, sd_save_value, message)
        who_said_value = parse_who_said_command(text)
        if who_said_value is not None:
            return bridge.handle_who_said_command(chat_id, who_said_value)
        history_value = parse_history_command(text)
        if history_value is not None:
            return bridge.handle_history_command(chat_id, history_value, message)
        daily_value = parse_daily_command(text)
        if daily_value is not None:
            return bridge.handle_daily_command(chat_id, daily_value)
        digest_value = parse_digest_command(text)
        if digest_value is not None:
            return bridge.handle_digest_command(chat_id, digest_value)
        routes_value = parse_routes_command(text)
        if routes_value is not None:
            return bridge.handle_routes_command(chat_id, user_id, routes_value)
        memory_chat_value = parse_memory_chat_command(text)
        if memory_chat_value is not None:
            return bridge.handle_memory_chat_command(chat_id, user_id, memory_chat_value)
        memory_user_value = parse_memory_user_command(text)
        if memory_user_value is not None:
            return bridge.handle_memory_user_command(chat_id, user_id, memory_user_value, message)
        if parse_memory_summary_command(text):
            return bridge.handle_memory_summary_command(chat_id, user_id)
        if parse_self_state_command(text):
            return bridge.handle_self_state_command(chat_id, user_id)
        if parse_world_state_command(text):
            return bridge.handle_world_state_command(chat_id, user_id)
        if parse_drives_command(text):
            return bridge.handle_drives_command(chat_id, user_id)
        autobio_value = parse_autobio_command(text)
        if autobio_value is not None:
            return bridge.handle_autobio_command(chat_id, user_id, autobio_value)
        skills_value = parse_skills_command(text)
        if skills_value is not None:
            return bridge.handle_skills_command(chat_id, user_id, skills_value)
        reflections_value = parse_reflections_command(text)
        if reflections_value is not None:
            return bridge.handle_reflections_command(chat_id, user_id, reflections_value)
        chat_digest_value = parse_chat_digest_command(text)
        if chat_digest_value is not None:
            return bridge.handle_chat_digest_command(chat_id, user_id, chat_digest_value)
        chat_deep_value = parse_chat_deep_command(text)
        if chat_deep_value is not None:
            return bridge.handle_chat_deep_command(chat_id, user_id, chat_deep_value)
        whois_value = parse_whois_command(text)
        if whois_value is not None:
            return bridge.handle_whois_command(chat_id, user_id, whois_value, message)
        profilecheck_value = parse_profilecheck_command(text)
        if profilecheck_value is not None:
            return bridge.handle_profilecheck_command(chat_id, user_id, profilecheck_value, message)
        achievement_audit_value = parse_achievement_audit_command(text)
        if achievement_audit_value is not None:
            return bridge.handle_achievement_audit_command(chat_id, user_id, achievement_audit_value)
        watchlist_value = parse_watchlist_command(text)
        if watchlist_value is not None:
            return bridge.handle_watchlist_command(chat_id, user_id, watchlist_value)
        reliable_value = parse_reliable_command(text)
        if reliable_value is not None:
            return bridge.handle_reliable_command(chat_id, user_id, reliable_value)
        suspects_value = parse_suspects_command(text)
        if suspects_value is not None:
            return bridge.handle_suspects_command(chat_id, user_id, suspects_value)
        whats_happening_value = parse_whats_happening_command(text)
        if whats_happening_value is not None:
            return bridge.handle_whats_happening_command(chat_id, user_id, whats_happening_value)
        summary24h_value = parse_summary24h_command(text)
        if summary24h_value is not None:
            return bridge.handle_summary24h_command(chat_id, user_id, summary24h_value)
        conflicts_value = parse_conflicts_command(text)
        if conflicts_value is not None:
            return bridge.handle_conflicts_command(chat_id, user_id, conflicts_value)
        ownergraph_value = parse_ownergraph_command(text)
        if ownergraph_value is not None:
            return bridge.handle_ownergraph_command(chat_id, user_id, ownergraph_value)
        if bridge.parse_owner_report_command(text):
            return bridge.handle_owner_report_command(chat_id, user_id)
        export_scope = bridge.parse_export_command(text)
        if export_scope is not None:
            return bridge.handle_export_command(chat_id, export_scope)
        portrait_value = bridge.parse_portrait_command(text)
        if portrait_value is not None:
            return bridge.handle_portrait_command(chat_id, user_id, portrait_value, message)
        moderation = parse_moderation_command(text)
        if moderation is not None:
            return bridge.handle_moderation_command(chat_id, user_id, moderation, message)
        warn_command = parse_warn_command(text)
        if warn_command is not None:
            return bridge.handle_warn_command(chat_id, user_id, warn_command, message)
        welcome_command = bridge.parse_welcome_command(text)
        if welcome_command is not None:
            return bridge.handle_welcome_command(chat_id, user_id, welcome_command)
        if text == "/reset":
            bridge.state.reset_chat(chat_id)
            bridge.log(f"chat reset chat={chat_id}")
            bridge.safe_send_text(chat_id, "Контекст очищен.")
            return True

        upgrade_task = parse_upgrade_command(text)
        if upgrade_task is not None:
            return bridge.handle_upgrade_command(chat_id, user_id, upgrade_task, is_private_chat=(chat_id > 0))

        parsed_mode = bridge.parse_mode_command(text)
        if parsed_mode is None:
            return False
        if parsed_mode == "":
            bridge.safe_send_text(chat_id, f"Режим: {bridge.state.get_mode(chat_id)}")
            return True
        if parsed_mode not in self.mode_prompts:
            bridge.safe_send_text(chat_id, "Используй: /mode jarvis или /mode enterprise")
            return True

        bridge.state.set_mode(chat_id, parsed_mode)
        bridge.log(f"mode changed chat={chat_id} mode={parsed_mode}")
        bridge.safe_send_text(chat_id, f"Mode: {parsed_mode}")
        return True


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
