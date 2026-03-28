from typing import Optional, Tuple

from utils.text_utils import normalize_whitespace


def normalize_mode(raw_mode: Optional[str], allowed_modes: set[str], default_mode: str) -> str:
    candidate = (raw_mode or default_mode).strip().lower()
    if candidate == "chat":
        candidate = "jarvis"
    if candidate in allowed_modes:
        return candidate
    return default_mode


def parse_mode_command(text: str, allowed_modes: set[str], default_mode: str) -> Optional[str]:
    if not text.startswith("/mode"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return ""
    return normalize_mode(parts[1], allowed_modes, default_mode)


def _parse_payload_command(text: str, command: str, default: Optional[str] = "") -> Optional[str]:
    if not text.startswith(command):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return default
    return parts[1].strip()


def parse_upgrade_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/upgrade", "")


def parse_remember_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/remember", "")


def parse_recall_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/recall", "")


def parse_search_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/search", "")


def parse_console_command(text: str) -> Optional[str]:
    payload = _parse_payload_command(text, "/console", None)
    if payload is not None:
        return payload
    return _parse_payload_command(text, "/sh", None)


def parse_sd_list_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/sdls", "")


def parse_sd_send_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/sdsend", "")


def parse_sd_save_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/sdsave", "")


def parse_who_said_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/who_said", "")


def parse_history_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/history", "")


def parse_daily_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/daily", "")


def parse_digest_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/digest", "")


def parse_owner_report_command(text: str) -> bool:
    return text.strip() == "/ownerreport"


def parse_self_heal_status_command(text: str) -> bool:
    return text.strip() == "/selfhealstatus"


def parse_self_heal_run_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/selfhealrun", "")


def parse_self_heal_approve_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/selfhealapprove", "")


def parse_self_heal_deny_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/selfhealdeny", "")


def parse_routes_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/routes", "")


def parse_memory_chat_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/memorychat", "")


def parse_memory_user_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/memoryuser", "")


def parse_memory_summary_command(text: str) -> bool:
    return text.strip() == "/memorysummary"


def parse_self_state_command(text: str) -> bool:
    return text.strip() == "/selfstate"


def parse_world_state_command(text: str) -> bool:
    return text.strip() == "/worldstate"


def parse_drives_command(text: str) -> bool:
    return text.strip() == "/drives"


def parse_autobio_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/autobio", "")


def parse_skills_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/skills", "")


def parse_reflections_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/reflections", "")


def parse_chat_digest_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/chatdigest", "")


def parse_chat_deep_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/chatdeep", "")


def parse_whois_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/whois", "")

def parse_profilecheck_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/profilecheck", "")


def parse_watchlist_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/watchlist", "")


def parse_reliable_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/reliable", "")


def parse_suspects_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/suspects", "")


def parse_achievement_audit_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/achaudit", "")


def parse_whats_happening_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/whatshappening", "")


def parse_summary24h_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/summary24h", "")


def parse_conflicts_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/conflicts", "")


def parse_ownergraph_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/ownergraph", "")


def parse_chat_watch_command(text: str) -> bool:
    cleaned = normalize_whitespace(text).lower().strip("!?.,:;()[]{}\"' ")
    if not cleaned:
        return False
    direct_matches = {
        "что тут происходит",
        "что здесь происходит",
        "что у вас тут происходит",
        "что у вас здесь происходит",
        "что у вас происходит",
    }
    if cleaned in direct_matches:
        return True
    return (
        "что" in cleaned
        and "происходит" in cleaned
        and any(marker in cleaned for marker in ("тут", "здесь", "у вас", "в чате", "в группе"))
    )


def parse_git_status_command(text: str) -> bool:
    return text.strip() == "/gitstatus"


def parse_git_last_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/gitlast", "")


def parse_errors_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/errors", "")


def parse_events_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/events", "")


def parse_export_command(text: str) -> Optional[str]:
    result = _parse_payload_command(text, "/export", "chat")
    return result


def parse_portrait_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/portrait", "")


def parse_owner_autofix_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/ownerautofix", "status")


def parse_password_command(text: str) -> Optional[str]:
    return _parse_payload_command(text, "/password", "")


def parse_moderation_command(text: str) -> Optional[Tuple[str, str]]:
    for command in ("ban", "unban", "mute", "unmute", "kick", "tban", "tmute"):
        prefix = f"/{command}"
        if text.startswith(prefix):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            return command, payload
    return None


def parse_warn_command(text: str) -> Optional[Tuple[str, str]]:
    for command in ("warnreasons", "setwarnlimit", "setwarnmode", "warntime", "resetwarn", "rmwarn", "warns", "warn", "dwarn", "swarn", "modlog"):
        prefix = f"/{command}"
        if text.startswith(prefix):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            return command, payload
    return None
