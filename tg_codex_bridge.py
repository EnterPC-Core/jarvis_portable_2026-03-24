import fcntl
import hashlib
import html
import json
import mimetypes
import os
import re
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
import secrets
from datetime import datetime
from difflib import SequenceMatcher
from threading import Event, Lock, RLock, Thread
from collections import OrderedDict, deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

from requests import Response, Session
from requests.exceptions import RequestException

from appeals_service import AppealsService
from handlers.control_panel_renderer import ControlPanelRenderer
from handlers.command_dispatch import CommandDispatcher
from handlers.telegram_handlers import TelegramMessageHandlers
from handlers.update_dispatcher import handle_reaction_update as dispatch_reaction_update, handle_telegram_update
from handlers.ui_handlers import UIHandlers
from handlers.command_parsers import (
    normalize_mode as _normalize_mode,
    parse_autobio_command as _parse_autobio_command,
    parse_chat_watch_command as _parse_chat_watch_command,
    parse_chat_digest_command as _parse_chat_digest_command,
    parse_daily_command as _parse_daily_command,
    parse_digest_command as _parse_digest_command,
    parse_drives_command as _parse_drives_command,
    parse_errors_command as _parse_errors_command,
    parse_events_command as _parse_events_command,
    parse_export_command as _parse_export_command,
    parse_git_last_command as _parse_git_last_command,
    parse_git_status_command as _parse_git_status_command,
    parse_history_command as _parse_history_command,
    parse_memory_chat_command as _parse_memory_chat_command,
    parse_memory_summary_command as _parse_memory_summary_command,
    parse_memory_user_command as _parse_memory_user_command,
    parse_mode_command as _parse_mode_command,
    parse_moderation_command as _parse_moderation_command,
    parse_owner_autofix_command as _parse_owner_autofix_command,
    parse_owner_report_command as _parse_owner_report_command,
    parse_password_command as _parse_password_command,
    parse_portrait_command as _parse_portrait_command,
    parse_recall_command as _parse_recall_command,
    parse_reflections_command as _parse_reflections_command,
    parse_remember_command as _parse_remember_command,
    parse_routes_command as _parse_routes_command,
    parse_sd_list_command as _parse_sd_list_command,
    parse_sd_save_command as _parse_sd_save_command,
    parse_sd_send_command as _parse_sd_send_command,
    parse_search_command as _parse_search_command,
    parse_self_state_command as _parse_self_state_command,
    parse_skills_command as _parse_skills_command,
    parse_upgrade_command as _parse_upgrade_command,
    parse_warn_command as _parse_warn_command,
    parse_who_said_command as _parse_who_said_command,
    parse_world_state_command as _parse_world_state_command,
)
from legacy_jarvis_adapter import LegacyJarvisAdapter
from utils.text_utils import (
    build_download_name as _build_download_name,
    normalize_whitespace as _normalize_whitespace,
    split_long_message as _split_long_message,
    trim_generic_followup as _trim_generic_followup,
    truncate_text as _truncate_text,
)
from utils.runtime_utils import (
    cleanup_temp_file as _cleanup_temp_file,
    prepare_tmp_dir as _prepare_tmp_dir,
    read_bool_env as _read_bool_env,
    read_int_env as _read_int_env,
    should_include_code_backup_file as _should_include_code_backup_file,
    split_file_parts as _split_file_parts,
)
from utils.chat_text import extract_assistant_persona as _extract_assistant_persona
from utils.report_utils import (
    extract_meminfo_value as _extract_meminfo_value,
    render_bridge_runtime_watch as _render_bridge_runtime_watch,
    render_enterprise_runtime_report as _render_enterprise_runtime_report,
    format_swap_line as _format_swap_line,
    render_disk_summary as _render_disk_summary,
    render_event_rows as _render_event_rows,
    render_network_summary as _render_network_summary,
    render_resource_summary as _render_resource_summary,
    render_route_diagnostics_rows as _render_route_diagnostics_rows,
    render_timeline_rows as _render_timeline_rows,
    render_top_processes as _render_top_processes,
)
from utils.help_utils import build_voice_transcription_help as _build_voice_transcription_help
from services.bridge_runtime_text import (
    build_help_panel_markup as _bridge_build_help_panel_markup,
    build_help_panel_text as _bridge_build_help_panel_text,
    build_user_autofix_label as _bridge_build_user_autofix_label,
    build_welcome_text as _bridge_build_welcome_text,
    can_owner_use_workspace_mode as _bridge_can_owner_use_workspace_mode,
    contains_profanity as _bridge_contains_profanity,
    contains_voice_trigger_name as _bridge_contains_voice_trigger_name,
    has_chat_access as _bridge_has_chat_access,
    has_public_callback_access as _bridge_has_public_callback_access,
    has_public_command_access as _bridge_has_public_command_access,
    is_owner_private_chat as _bridge_is_owner_private_chat,
    normalize_incoming_text as _bridge_normalize_incoming_text,
    should_attempt_owner_autofix as _bridge_should_attempt_owner_autofix,
    should_process_group_message as _bridge_should_process_group_message,
)
from services.bridge_file_helpers import (
    ensure_sdcard_save_target_writable as _bridge_ensure_sdcard_save_target_writable,
    extract_message_media_file as _bridge_extract_message_media_file,
    format_file_size as _bridge_format_file_size,
    normalize_sdcard_alias as _bridge_normalize_sdcard_alias,
    read_document_excerpt as _bridge_read_document_excerpt,
    resolve_sdcard_path as _bridge_resolve_sdcard_path,
    resolve_sdcard_save_target as _bridge_resolve_sdcard_save_target,
)
from services.bridge_ops_helpers import (
    inspect_runtime_log as _bridge_inspect_runtime_log,
    is_error_log_line as _bridge_is_error_log_line,
    is_operational_log_line as _bridge_is_operational_log_line,
    read_recent_log_highlights as _bridge_read_recent_log_highlights,
    read_recent_operational_highlights as _bridge_read_recent_operational_highlights,
    render_git_last_commits as _bridge_render_git_last_commits,
    render_git_status_summary as _bridge_render_git_status_summary,
    run_git_command as _bridge_run_git_command,
)
from utils.message_utils import (
    build_service_actor_name as _build_service_actor_name,
    describe_message_media_kind as _describe_message_media_kind,
    extract_forward_origin as _extract_forward_origin,
    format_reaction_count_payload as _format_reaction_count_payload,
    format_reaction_payload as _format_reaction_payload,
    summarize_message_for_pin as _summarize_message_for_pin,
)
from utils.memory_renderers import (
    render_autobiographical_context as _render_autobiographical_context,
    render_chat_memory_context as _render_chat_memory_context,
    render_drive_context as _render_drive_context,
    render_reflection_context as _render_reflection_context,
    render_relation_memory_context as _render_relation_memory_context,
    render_self_model_context as _render_self_model_context,
    render_skill_memory_context as _render_skill_memory_context,
    render_summary_memory_context as _render_summary_memory_context,
    render_user_memory_context as _render_user_memory_context,
    render_world_state_context as _render_world_state_context,
)
from prompts.builders import (
    build_fts_query as _build_fts_query,
    build_prompt as _build_prompt,
    dedupe_history as _dedupe_history,
    extract_keywords as _extract_keywords,
    format_history as _format_history,
    is_simple_greeting as _is_simple_greeting,
    resolve_prompt_profile_name as _resolve_prompt_profile_name,
)
from prompts.task_prompts import (
    build_grammar_fix_prompt as _build_grammar_fix_prompt,
    build_portrait_prompt as _build_portrait_prompt,
    build_upgrade_request_prompt as _build_upgrade_request_prompt,
    build_voice_cleanup_prompt as _build_voice_cleanup_prompt,
)
from prompts.runtime_profiles import RUNTIME_PROFILES
from services.orchestration_utils import (
    apply_self_check_contract as _apply_self_check_contract,
    build_guardrail_note as _build_guardrail_note,
    build_route_summary_text as _build_route_summary_text,
    classify_answer_outcome as _classify_answer_outcome,
    has_freshness_marker as _has_freshness_marker,
    validate_route_decision as _validate_route_decision,
)
from services.live_gateway import LiveGateway, LiveGatewayDeps
from pipeline.diagnostics import (
    build_persisted_self_check_report,
    enrich_self_check_report,
)
from pipeline.context_pipeline import ContextPipeline
from services.answer_postprocess import (
    collapse_duplicate_answer_blocks as _collapse_duplicate_answer_blocks,
    postprocess_answer as _postprocess_answer,
    strip_banned_openers as _strip_banned_openers,
    strip_meta_reply_wrapper as _strip_meta_reply_wrapper,
)
from models.contracts import (
    AttachmentBundle,
    ContextBundle,
    ExecutionTrace,
    LiveProviderRecord,
    RequestRoutePolicy,
    RouteDecision,
    SelfCheckReport,
    ROUTER_POLICY_MATRIX,
)
from services.auto_moderation import (
    AutoModerationDecision,
    get_group_rules_text as _get_group_rules_text,
)
from moderation.anti_abuse import AntiAbuseAdapter
from moderation.appeals import AppealsAdapter
from moderation.moderation_models import ModerationContext, ModerationPolicy
from moderation.moderation_orchestrator import ModerationOrchestrator
from moderation.modlog import ModlogAdapter
from moderation.policy import ModerationTextPolicy
from moderation.sanctions import SanctionsAdapter
from moderation.warnings import WarningAdapter
from owner.admin_registry import render_admin_command_catalog
from owner.handlers import OwnerCommandService
from router.request_router import (
    RouterRuntimeDeps,
    analyze_request_route as _analyze_request_route_module,
    classify_request_kind as _classify_request_kind_module,
    detect_intent as _detect_intent_module,
    detect_local_chat_query as _detect_local_chat_query_module,
    detect_owner_admin_request as _detect_owner_admin_request_module,
    detect_runtime_query as _detect_runtime_query_module,
    has_external_research_signal as _has_external_research_signal_module,
    is_comparison_request as _is_comparison_request_module,
    is_explicit_help_request as _is_explicit_help_request_module,
    is_local_project_meta_request as _is_local_project_meta_request_module,
    is_opinion_request as _is_opinion_request_module,
    is_product_selection_help_request as _is_product_selection_help_request_module,
    is_purchase_advice_request as _is_purchase_advice_request_module,
    is_recommendation_request as _is_recommendation_request_module,
    response_shape_hint as _response_shape_hint_module,
    should_include_database_context as _should_include_database_context_module,
    should_include_event_context as _should_include_event_context_module,
    should_use_web_research as _should_use_web_research_module,
)
from services.failure_detectors import detect_failure_signals, render_failure_signals
from services.repair_playbooks import render_playbook_summary, select_playbooks_for_signals
from services.conversation_state import GroupConversationState
from services.group_reply_policy import GroupReplyPolicy
from services.memory_service import MemoryService, MemoryServiceDeps
from services.moderation_execution_service import (
    ModerationExecutionService,
    ModerationExecutionServiceDeps,
)
from services.runtime_service import RuntimeService, RuntimeServiceDeps
from services.text_route_service import TextRouteService, TextRouteServiceDeps
from services.js_enterprise_service import JSEnterpriseService, JSEnterpriseServiceDeps
from services.enterprise_console_webapp import build_enterprise_console_html, run_enterprise_console_server
from services.ask_codex_service import ask_codex as _ask_codex_service
from services.reply_context_service import (
    build_active_subject_context as _build_active_subject_context_service,
    build_reply_context as _build_reply_context_service,
    message_refers_to_active_subject as _message_refers_to_active_subject_service,
)
from services.bridge_state_schema import (
    ensure_chat_events_columns,
    ensure_request_diagnostics_columns,
    ensure_user_memory_profile_columns,
    ensure_warn_settings_columns,
    ensure_warnings_columns,
    ensure_world_state_registry_columns,
    initialize_bridge_state_db,
    seed_drive_scores,
    seed_self_model_state,
    seed_skill_memory,
)
from services.bridge_memory_profiles import (
    analyze_participant_rows as _analyze_participant_rows_service,
    get_active_subject as _get_active_subject_service,
    get_message_subject as _get_message_subject_service,
    get_participant_behavior_context as _get_participant_behavior_context_service,
    get_user_memory_context as _get_user_memory_context_service,
    get_visual_signal_for_message as _get_visual_signal_for_message_service,
    record_message_subject as _record_message_subject_service,
    record_participant_visual_signal as _record_participant_visual_signal_service,
    refresh_participant_behavior_profile as _refresh_participant_behavior_profile_service,
    refresh_user_memory_profile as _refresh_user_memory_profile_service,
    set_active_subject as _set_active_subject_service,
)
from services.bridge_chat_state import (
    add_fact as _add_fact_service,
    append_history as _append_history_service,
    get_facts as _get_facts_service,
    get_history as _get_history_service,
    get_mode as _get_mode_service,
    get_summary as _get_summary_service,
    record_event as _record_event_service,
    render_facts as _render_facts_service,
    reset_chat as _reset_chat_service,
    set_mode as _set_mode_service,
    update_event_text as _update_event_text_service,
    update_summary as _update_summary_service,
)
from services.bridge_moderation_state import (
    add_moderation_action as _add_moderation_action_service,
    add_warning as _add_warning_service,
    complete_moderation_action as _complete_moderation_action_service,
    deactivate_active_moderation as _deactivate_active_moderation_service,
    finish_chat_task as _finish_chat_task_service,
    finish_upgrade as _finish_upgrade_service,
    get_active_moderations as _get_active_moderations_service,
    get_due_moderation_actions as _get_due_moderation_actions_service,
    get_latest_active_moderation as _get_latest_active_moderation_service,
    get_managed_group_chat_ids as _get_managed_group_chat_ids_service,
    get_warn_settings as _get_warn_settings_service,
    get_warning_count as _get_warning_count_service,
    get_warning_rows as _get_warning_rows_service,
    get_welcome_settings as _get_welcome_settings_service,
    is_duplicate_message as _is_duplicate_message_service,
    remove_last_warning as _remove_last_warning_service,
    reset_warnings as _reset_warnings_service,
    reset_welcome_template as _reset_welcome_template_service,
    set_warn_limit as _set_warn_limit_service,
    set_warn_mode as _set_warn_mode_service,
    set_warn_time as _set_warn_time_service,
    set_welcome_enabled as _set_welcome_enabled_service,
    set_welcome_template as _set_welcome_template_service,
    try_start_chat_task as _try_start_chat_task_service,
    try_start_upgrade as _try_start_upgrade_service,
)
from services.bridge_diagnostics_state import (
    count_self_heal_attempts as _count_self_heal_attempts_service,
    find_recent_self_heal_incident as _find_recent_self_heal_incident_service,
    get_recent_repair_journal as _get_recent_repair_journal_service,
    get_recent_request_diagnostics as _get_recent_request_diagnostics_service,
    get_recent_self_heal_incidents as _get_recent_self_heal_incidents_service,
    get_self_heal_incident as _get_self_heal_incident_service,
    get_world_state_rows as _get_world_state_rows_service,
    has_recent_self_heal_incident as _has_recent_self_heal_incident_service,
    record_repair_journal as _record_repair_journal_service,
    record_request_diagnostic as _record_request_diagnostic_service,
    record_self_heal_attempt as _record_self_heal_attempt_service,
    record_self_heal_incident as _record_self_heal_incident_service,
    record_self_heal_lesson as _record_self_heal_lesson_service,
    record_self_heal_verification as _record_self_heal_verification_service,
    update_self_heal_attempt as _update_self_heal_attempt_service,
    update_self_heal_incident_state as _update_self_heal_incident_state_service,
)
from services.bridge_task_state import (
    find_latest_task_id_by_request_trace as _find_latest_task_id_by_request_trace_service,
    get_task_context as _get_task_context_service,
    get_task_run as _get_task_run_service,
    record_task_event as _record_task_event_service,
    upsert_task_run as _upsert_task_run_service,
    update_task_run as _update_task_run_service,
)
from services.bridge_context_state import (
    get_database_context as _get_database_context_service,
    get_event_context as _get_event_context_service,
)
from services.text_task_service import (
    run_recent_chat_report_task as _run_recent_chat_report_task_service,
    run_text_task as _run_text_task_service,
)
from services.media_task_service import (
    ask_codex_with_document as _ask_codex_with_document_service,
    ask_codex_with_image as _ask_codex_with_image_service,
    run_audio_task as _run_audio_task_service,
    run_document_task as _run_document_task_service,
    run_photo_task as _run_photo_task_service,
    run_voice_task as _run_voice_task_service,
)

try:
    import psutil
except ImportError:
    psutil = None

TELEGRAM_TEXT_LIMIT = 4000
TELEGRAM_TIMEOUT = 30
CONSOLE_STREAM_UPDATE_SECONDS = 1.2
CONSOLE_STREAM_CHUNK_LIMIT = 3500
CONSOLE_DOCUMENT_THRESHOLD = 12000
GET_UPDATES_TIMEOUT = 25
ERROR_BACKOFF_SECONDS = 3
DEFAULT_CODEX_TIMEOUT = 180
DEFAULT_CHAT_ROUTE_TIMEOUT = 60
DEFAULT_HISTORY_LIMIT = 120
MIN_HISTORY_LIMIT = 10
MAX_HISTORY_LIMIT = 512
DEFAULT_MODE_NAME = "jarvis"
MAX_SEEN_MESSAGES = 500
MAX_HISTORY_ITEM_CHARS = 900
MAX_CODEX_OUTPUT_CHARS = 12000
DEFAULT_BRIDGE_CONTEXT_SOFT_LIMIT = 200000
MAX_BRIDGE_CONTEXT_SOFT_LIMIT = 400000
CODEX_PROGRESS_UPDATE_SECONDS = 6
DEFAULT_STT_BACKEND = "disabled"
DEFAULT_AUDIO_TRANSCRIBE_MODEL = ""
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_STT_LANGUAGE = "ru"
DEFAULT_SAFE_CHAT_ONLY = False
DEFAULT_BOT_USERNAME = ""
DEFAULT_TRIGGER_NAME = "jarvis"
DEFAULT_GROUP_SPONTANEOUS_REPLY_ENABLED = False
DEFAULT_GROUP_SPONTANEOUS_REPLY_CHANCE_PERCENT = 18
DEFAULT_GROUP_SPONTANEOUS_REPLY_COOLDOWN_SECONDS = 1800
DEFAULT_GROUP_FOLLOWUP_WINDOW_SECONDS = 300
DEFAULT_GROUP_DISCUSSION_MAX_TURNS_PER_USER = 4
DEFAULT_GROUP_DISCUSSION_COOLDOWN_SECONDS = 900
DEFAULT_DB_PATH = "jarvis_memory.db"
DEFAULT_LOCK_PATH = "tg_codex_bridge.lock"
DEFAULT_HEARTBEAT_PATH = "tg_codex_bridge.heartbeat"
DOC_RUNTIME_DRIFT_MARKERS = (
    "README.md",
    "PROJECT_RUN_INSTRUCTIONS.md",
    "PORTABLE_RUN_INSTRUCTIONS.md",
    "BOT_UI_GUIDE.md",
    "COMMANDS.md",
    "data/runtime_backups/",
)
DEFAULT_BACKUP_INTERVAL_DAYS = 7
DEFAULT_BACKUP_PART_SIZE_MB = 45
DEFAULT_OWNER_AUTOFIX = True
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90
DEFAULT_AUTO_SELF_HEAL_INTERVAL_SECONDS = 300
DEFAULT_AUTO_SELF_HEAL_COOLDOWN_SECONDS = 900
DEFAULT_AUTO_SELF_HEAL_REPORT_COOLDOWN_SECONDS = 1800
DEFAULT_AUTO_SELF_HEAL_MAX_RETRIES = 2
DEFAULT_ENTERPRISE_TASK_TIMEOUT = 0
DEFAULT_ENTERPRISE_WORKSPACE_TIMEOUT = 600  # 10 minutes
DEFAULT_OWNER_DAILY_DIGEST_HOUR_UTC = 7
DEFAULT_OWNER_WEEKLY_DIGEST_WEEKDAY_UTC = 0
DEFAULT_MEMORY_REFRESH_INTERVAL_SECONDS = 1800
DEFAULT_LEGACY_JARVIS_DB_PATH = str((Path(__file__).resolve().parent.parent / "jarvis_legacy_data" / "jarvis.db"))
DEFAULT_WEBAPP_BIND_HOST = "127.0.0.1"
DEFAULT_WEBAPP_PORT = 8765
DEFAULT_CODEX_APP_SERVER_URL = "ws://127.0.0.1:4599"
DEFAULT_ENTERPRISE_SERVER_BASE_URL = "http://127.0.0.1:8766"
DISPLAY_TIMEZONE = ZoneInfo("Europe/Moscow")
OWNER_USER_ID = int((os.getenv("OWNER_USER_ID", os.getenv("ADMIN_ID", "6102780373")) or "6102780373").strip())
OWNER_USERNAME = (os.getenv("OWNER_USERNAME", "@DmitryUnboxing") or "@DmitryUnboxing").strip()
OWNER_ALIAS_USER_IDS = tuple(
    int(part.strip())
    for part in (os.getenv("OWNER_ALIAS_USER_IDS", "7087071466") or "7087071466").split(",")
    if part.strip().isdigit()
)
OWNER_MEMORY_CHAT_ID = 0
ACCESS_DENIED_TEXT = (
    "Этот раздел недоступен."
)
CHAT_PARTICIPANTS_REFRESH_SECONDS = 6 * 60 * 60

TERMUX_LIB_DIR = "/data/data/com.termux/files/usr/lib"
DEFAULT_IMAGE_PROMPT = "Разбери изображение и кратко скажи, что на нём важно."
SAFE_MODE_REPLY = (
    "Сейчас режим ограничен анализом и общением. "
    "Я могу объяснить, проверить идею, разобрать код, фото, текст или ошибку, но не выполнять действия в системе."
)
UNSUPPORTED_FILE_REPLY = "Поддерживаются текст, фото, документы, voice/audio и базовый разбор video/gif/sticker."

UPGRADE_USAGE_TEXT = "Используй: /upgrade <что нужно изменить>"
UPGRADE_RUNNING_TEXT = "Upgrade выполняется..."
UPGRADE_TIMEOUT_TEXT = "Upgrade не завершился вовремя. Попробуй сузить задачу."
UPGRADE_FAILED_TEXT = "Upgrade завершился с ошибкой."
OWNER_AGENT_RUNNING_TEXT = "Выполняю запрос..."
JARVIS_AGENT_RUNNING_TEXT = "Готовлю ответ..."
UPGRADE_ALREADY_RUNNING_TEXT = "Upgrade уже выполняется. Дождись завершения текущей задачи."
UPGRADE_PRIVATE_ONLY_TEXT = "Upgrade выполняется только в личном чате с создателем."
UPGRADE_APPLIED_TEXT = "Изменения сохранены. Runtime больше не делает self-restart; новый код подхватится только после внешнего перезапуска supervisor."
RESTARTING_TEXT = "Enterprise Core перезапускается..."
RESTARTED_TEXT = "Enterprise Core перезапущен. Бот снова в сети."
REMEMBER_USAGE_TEXT = "Используй: /remember <что нужно запомнить>"
RECALL_USAGE_TEXT = "Используй: /recall [запрос]"
PORTRAIT_USAGE_TEXT = "Используй: /portrait @username или reply на сообщение участника"
SEARCH_USAGE_TEXT = "Используй: /search <запрос>"
CONSOLE_USAGE_TEXT = "Используй: /console <команда> или /sh <команда>"
SD_LIST_USAGE_TEXT = "Используй: /sdls [/sdcard/путь]"
SD_SEND_USAGE_TEXT = "Используй: /sdsend /sdcard/путь/к/файлу"
SD_SAVE_USAGE_TEXT = "Используй: /sdsave /sdcard/папка/или/файл и отправь команду reply на медиа либо подписью к документу"
DEFAULT_SD_SAVE_ALIAS = "/storage/emulated/0/Download/"
RESOURCES_USAGE_TEXT = "Используй: /resources"
TOPPROC_USAGE_TEXT = "Используй: /topproc"
DISK_USAGE_TEXT = "Используй: /disk"
NET_USAGE_TEXT = "Используй: /net"
GIT_STATUS_USAGE_TEXT = "Используй: /gitstatus"
GIT_LAST_USAGE_TEXT = "Используй: /gitlast [количество]"
ERRORS_USAGE_TEXT = "Используй: /errors [количество]"
EVENTS_USAGE_TEXT = "Используй: /events [restart|access|system|all] [количество]"
WHO_SAID_USAGE_TEXT = "Используй: /who_said <запрос>"
HISTORY_USAGE_TEXT = "Используй: /history @username, /history user_id или reply на сообщение участника"
DIGEST_USAGE_TEXT = "Используй: /digest [YYYY-MM-DD]"
CHAT_DIGEST_USAGE_TEXT = "Используй: /chatdigest <chat_id> [YYYY-MM-DD]"
CHAT_DEEP_USAGE_TEXT = "Используй: /chatdeep [chat_id]"
WHOIS_USAGE_TEXT = "Используй: /whois @username, /whois user_id или reply на сообщение участника"
WHATS_HAPPENING_USAGE_TEXT = "Используй: /whatshappening [chat_id]"
SUMMARY24H_USAGE_TEXT = "Используй: /summary24h [chat_id]"
CONFLICTS_USAGE_TEXT = "Используй: /conflicts [chat_id]"
OWNERGRAPH_USAGE_TEXT = "Используй: /ownergraph"
WATCHLIST_USAGE_TEXT = "Используй: /watchlist [chat_id]"
RELIABLE_USAGE_TEXT = "Используй: /reliable [chat_id]"
ACHIEVEMENT_AUDIT_USAGE_TEXT = "Используй: /achaudit [количество]"
OWNER_REPORT_USAGE_TEXT = "Используй: /ownerreport"
REPAIR_STATUS_USAGE_TEXT = "Используй: /repairstatus"
QUALITY_REPORT_USAGE_TEXT = "Используй: /qualityreport"
SELF_HEAL_STATUS_USAGE_TEXT = "Используй: /selfhealstatus"
SELF_HEAL_RUN_USAGE_TEXT = "Используй: /selfhealrun <playbook|incident_id> [dry-run|execute]"
SELF_HEAL_APPROVE_USAGE_TEXT = "Используй: /selfhealapprove <incident_id>"
SELF_HEAL_DENY_USAGE_TEXT = "Используй: /selfhealdeny <incident_id>"
ROUTES_USAGE_TEXT = "Используй: /routes [количество]"
MEMORY_CHAT_USAGE_TEXT = "Используй: /memorychat [запрос]"
MEMORY_USER_USAGE_TEXT = "Используй: /memoryuser @username, /memoryuser user_id или reply на сообщение участника"
MEMORY_SUMMARY_USAGE_TEXT = "Используй: /memorysummary"
SELF_STATE_USAGE_TEXT = "Используй: /selfstate"
WORLD_STATE_USAGE_TEXT = "Используй: /worldstate"
DRIVES_USAGE_TEXT = "Используй: /drives"
AUTOBIO_USAGE_TEXT = "Используй: /autobio [запрос]"
SKILLS_USAGE_TEXT = "Используй: /skills [запрос]"
REFLECTIONS_USAGE_TEXT = "Используй: /reflections [количество]"
EXPORT_USAGE_TEXT = "Используй: /export chat, /export today, /export @username или /export user_id"
APPEAL_USAGE_TEXT = "Используй: /appeal <текст апелляции>"
MODERATION_USAGE_TEXT = "Используй reply или: /ban @username [причина], /mute @username [причина], /tban 1d @username [причина], /tmute 1h @username [причина]"
WARN_USAGE_TEXT = "Используй reply или: /warn @username [причина], /dwarn @username [причина], /swarn @username [причина], /warns @username, /warnreasons @username, /rmwarn @username, /resetwarn @username, /setwarnlimit 3, /setwarnmode mute|tmute 1h|ban|tban 1d|kick, /warntime 7d, /modlog"
WELCOME_USAGE_TEXT = "Используй: /welcome on|off|status, /setwelcome <текст>, /resetwelcome. Переменные: {first_name} {last_name} {full_name} {username} {chat_title}"
WELCOME_DEFAULT_TEMPLATE = "Добро пожаловать, {full_name}!"
RUNTIME_QUERY_MARKERS = (
    "ram", "mem", "memory", "swap", "uptime", "cpu", "disk", "storage", "load average",
    "ресурс", "ресурсы", "памят", "оператив", "озу", "своп", "аптайм", "загрузка", "диск",
    "место", "процесс", "процессы", "среде", "среда", "характеристик", "характеристики",
    "topproc", "resources", "disk usage", "system status",
)
FRESHNESS_MARKERS = (
    "сейчас", "сегодня", "на момент запроса", "актуаль", "обнов", "live",
    "today", "latest", "current",
)
ROUTER_POLICY_LESSONS = (
    "explicit-persona-priority",
    "runtime-needs-workspace-verification",
    "live-data-needs-fresh-source",
    "do-not-claim-actions-without-tool-proof",
)
ENTERPRISE_PROGRESS_STEPS = [
    ("Вхожу в задачу", "Сначала разбираю, что именно нужно проверить и где искать причину."),
    ("Шерстю код и логи", "Собираю сигналы из кода, логов и runtime, без догадок наугад."),
    ("Проверяю среду", "Смотрю, нет ли проблемы в окружении, процессах или конфиге."),
    ("Проверяю гипотезы", "Отбрасываю шум и оставляю только рабочие версии."),
    ("Чищу лишнее", "Отделяю симптом от причины, чтобы ответ был по делу."),
    ("Дожимаю детали", "Проверяю граничные случаи и слабые места."),
    ("Собираю результат", "Формирую итог без лишней воды."),
]
ENTERPRISE_PROGRESS_SPINNERS = ("◜", "◠", "◝", "◞", "◡", "◟")
ENTERPRISE_PROGRESS_MICRO_JOKES = [
    "Код шевелится, я тоже. Смотрю, кто кого переиграет.",
    "Система делает вид, что всё под контролем. Проверяю это заявление.",
    "Похоже, стек уже вспотел. Продолжаю спокойно.",
    "Кто-то тут накодил с фантазией. Разматываю аккуратно.",
    "Идёт инженерная работа без шаманства и жестов руками.",
    "Если сейчас что-то хрустнет, хотя бы будет ясно почему.",
    "Дальше уже не поверхностный взгляд, а нормальная раскопка.",
    "Код не паникует. Я тоже. Но вопросы к нему уже есть.",
    "Внутри всё как обычно: зависимости, допущения и последствия решений.",
    "Держу курс на результат, а не на красивое объяснение без пользы.",
]
ENTERPRISE_PROGRESS_LONG_NOTES = [
    (60, "☕ Уже минута. Это не разминочный прогон, а нормальная раскопка."),
    (180, "🛠 Три минуты внутри. Значит, задача либо объёмная, либо с творческим наследием."),
    (300, "🚧 Пять минут в работе. Я всё ещё внутри и продолжаю разбирать корень проблемы."),
    (480, "🫡 Восемь минут. Это уже полноценная экспедиция, а не быстрая проверка."),
]
JARVIS_PROGRESS_STEPS = [
    ("Слушаю запрос", "Сначала уточняю смысл запроса, потом уже формирую ответ."),
    ("Собираю контекст", "Поднимаю нужные куски памяти и релевантные детали."),
    ("Думаю над ответом", "Ищу короткий и полезный вариант без лишней болтовни."),
    ("Перепроверяю детали", "Проверяю, чтобы ответ держался на фактах и контексте."),
    ("Упаковываю результат", "Сейчас будет аккуратно, понятно и по делу."),
]
JARVIS_PROGRESS_SPINNERS = ("✦", "✧", "✦", "✧")
JARVIS_PROGRESS_MICRO_JOKES = [
    "Я уже в процессе. Паниковать рано, скучать тоже.",
    "Запрос принят, ответ постепенно собирается.",
    "Если что-то и тормозит, то точно не желание помочь.",
    "Аккуратно перекладываю хаос в понятный ответ.",
    "Сейчас всё будет: и смысл, и форма, и без лишней духоты.",
    "Я не пропал, просто занят полезным.",
    "Держу фокус. Ответ будет с содержанием.",
]
JARVIS_PROGRESS_LONG_NOTES = [
    (60, "☕ Уже минута. Значит, запрос требует не ответа на бегу, а нормальной сборки."),
    (180, "🧠 Три минуты. Здесь уже идёт не набросок, а полноценная мыслительная работа."),
    (300, "🎭 Пять минут. Ответ получается объёмнее обычного, дожимаю его до внятного вида."),
    (480, "🌌 Восемь минут. Я всё ещё в деле и веду ответ к нормальному финалу."),
]
COMMANDS_LIST_TEXT = (
    "Команды:\n"
    "/start\n"
    "/help\n"
    "/rules\n"
    "/commands\n"
    "/reset\n"
    "/ping\n"
    "/restart\n"
    "/status\n"
    "/rating\n"
    "/top\n"
    "/topweek\n"
    "/topday\n"
    "/stats\n"
    "/achievements\n"
    "/appeal <текст>\n"
    "/appeals\n"
    "/appeal_review <id>\n"
    "/appeal_approve <id> [решение]\n"
    "/appeal_reject <id> [решение]\n"
    "/remember <факт>\n"
    "/recall [запрос]\n"
    "/search <запрос>\n"
    "/console <команда>\n"
    "/sh <команда>\n"
    "/resources\n"
    "/topproc\n"
    "/disk\n"
    "/net\n"
    "/gitstatus\n"
    "/gitlast [количество]\n"
    "/errors [количество]\n"
    "/events [restart|access|system|all] [количество]\n"
    "/routes [количество]\n"
    "/memorychat [запрос]\n"
    "/memoryuser [@username|user_id]\n"
    "/memorysummary\n"
    "/selfstate\n"
    "/worldstate\n"
    "/drives\n"
    "/autobio [запрос]\n"
    "/skills [запрос]\n"
    "/reflections [количество]\n"
    "/sdls [/sdcard/путь]\n"
    "/sdsend /sdcard/путь/к/файлу\n"
    "/sdsave /sdcard/папка/или/файл\n"
    "/who_said <запрос>\n"
    "/history [@username|user_id]\n"
    "/daily [YYYY-MM-DD]\n"
    "/digest [YYYY-MM-DD]\n"
    "/chatdigest <chat_id> [YYYY-MM-DD]\n"
    "/chatdeep [chat_id]\n"
    "/whois [@username|user_id]\n"
    "/watchlist [chat_id]\n"
    "/reliable [chat_id]\n"
    "/achaudit [количество]\n"
    "/whatshappening [chat_id]\n"
    "/summary24h [chat_id]\n"
    "/conflicts [chat_id]\n"
    "/ownergraph\n"
    "/ownerreport\n"
    "/repairstatus\n"
    "/export [chat|today|@username|user_id]\n"
    "/portrait [@username]\n"
    "/mode jarvis\n"
    "/mode code\n"
    "/mode strict\n"
    "/upgrade <что изменить>\n"
    "/ownerautofix on|off|status\n"
    "/welcome on|off|status\n"
    "/setwelcome <текст>\n"
    "/resetwelcome\n"
    "/ban /unban /mute /unmute /kick /tban /tmute\n"
    "/warn /dwarn /swarn /warns /warnreasons /rmwarn /resetwarn\n"
    "/setwarnlimit /setwarnmode /warntime /modlog\n\n"
    "Модерация сейчас:\n"
    "• auto-ban отключён: бот сам даёт только warn или временный mute\n"
    "• тяжёлые кейсы уходят владельцу отдельным owner-report в ЛС\n"
    "• /rules показывает правила группы\n"
    "• owner override: «сними», «сними мут», «сними бан», «размуть», «разбань»\n"
    "• если активных санкций несколько, снимать лучше reply-командой на нужного участника\n\n"
    f"Создатель с ID {OWNER_USER_ID} отвечает без пароля.\n"
    f"Остальным пароль выдаёт только {OWNER_USERNAME}"
)
SELF_MODEL_DEFAULTS = {
    "identity": "Enterprise Core",
    "capabilities": "local chat reasoning; persistent SQLite memory; runtime verification; owner operations; live-data routing; file/image/voice analysis",
    "hard_limitations": "не придумывает результат без выполнения; не видит всех участников Telegram напрямую; live-data зависит от сети и источников; не симулирует сознание и переживания",
    "trusted_tools": "SQLite memory; Telegram Bot API; Enterprise Core runtime; local filesystem/runtime probes; whitelisted live sources",
    "confidence_policy": "observed > inferred > uncertain; при нехватке подтверждения явно маркирует ограничение",
    "current_goals": "держать continuity; отвечать честно; сохранять operational stability; улучшать локальную grounding-память",
    "active_constraints": "full-enterprise-access for owner; no fake consciousness; no hidden tool claims",
    "honesty_rules": "не придумывать выполненные действия; различать observed/inferred/uncertain; не выдавать roleplay за системное состояние",
    "jarvis_style_invariants": "кратко, живо, без официоза и без фальшивых эмоций",
    "enterprise_style_invariants": "инженерно, точно, action-first, без лишних самоограничивающих шаблонов",
}
DEFAULT_SKILL_LIBRARY: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "runtime_triage",
        "runtime, health, status, errors, owner",
        "1) собрать resource summary; 2) посмотреть recent errors/events; 3) сверить heartbeat/backup/runtime state; 4) ответить только по подтверждённым данным",
        "built-in",
    ),
    (
        "doc_sync",
        "docs, backups, sync, drift, repo",
        "1) прогнать refresh_repo_state.sh; 2) проверить git status; 3) синхронизировать docs/runtime_backups; 4) только потом commit/push",
        "built-in",
    ),
    (
        "chat_grounding",
        "chat, context, participants, dynamics, relation",
        "1) поднять local chat query route; 2) собрать events/user memory/relation memory/chat dynamics; 3) отвечать по локальному контексту, а не по web/live",
        "built-in",
    ),
    (
        "live_verification",
        "latest, current, weather, fx, crypto, stocks, news",
        "1) выбрать профильный live-route; 2) приложить source+freshness; 3) при сетевом сбое честно вернуть fallback без выдуманных фактов",
        "built-in",
    ),
    (
        "safe_restart",
        "restart, supervisor, polling, single-instance",
        "1) не плодить второй polling; 2) перезапускать через supervisor; 3) после рестарта проверить log startup markers и single-instance lock",
        "built-in",
    ),
)
DRIVE_NAMES: Tuple[str, ...] = (
    "uncertainty_pressure",
    "inconsistency_pressure",
    "stale_memory_pressure",
    "unresolved_task_pressure",
    "doc_sync_pressure",
    "runtime_risk_pressure",
)
WEATHER_CODE_LABELS = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "слабая морось",
    53: "морось",
    55: "сильная морось",
    56: "ледяная морось",
    57: "сильная ледяная морось",
    61: "слабый дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "сильный ледяной дождь",
    71: "слабый снег",
    73: "снег",
    75: "сильный снег",
    77: "снежные зёрна",
    80: "ливень",
    81: "сильный ливень",
    82: "очень сильный ливень",
    85: "слабый снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}
CURRENCY_ALIASES = {
    "доллар": "USD",
    "доллара": "USD",
    "доллару": "USD",
    "доллары": "USD",
    "usd": "USD",
    "евро": "EUR",
    "eur": "EUR",
    "руб": "RUB",
    "рубль": "RUB",
    "рубля": "RUB",
    "рублей": "RUB",
    "ruble": "RUB",
    "rub": "RUB",
    "тенге": "KZT",
    "kzt": "KZT",
    "гривна": "UAH",
    "гривны": "UAH",
    "uah": "UAH",
    "юань": "CNY",
    "юаня": "CNY",
    "cny": "CNY",
    "лира": "TRY",
    "try": "TRY",
    "фунт": "GBP",
    "gbp": "GBP",
}
CRYPTO_ALIASES = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "биткоин": "bitcoin",
    "биток": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "эфир": "ethereum",
    "эфириум": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "солана": "solana",
    "ton": "the-open-network",
    "toncoin": "the-open-network",
    "тон": "the-open-network",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "дог": "dogecoin",
}
STOCK_ALIASES = {
    "aapl": "AAPL",
    "apple": "AAPL",
    "эппл": "AAPL",
    "tsla": "TSLA",
    "tesla": "TSLA",
    "тесла": "TSLA",
    "nvda": "NVDA",
    "nvidia": "NVDA",
    "энвидиа": "NVDA",
    "amd": "AMD",
    "amzn": "AMZN",
    "amazon": "AMZN",
    "msft": "MSFT",
    "microsoft": "MSFT",
    "meta": "META",
    "googl": "GOOGL",
    "google": "GOOGL",
}

OWNER_AUTOFIX_USAGE = "Используй: /ownerautofix on|off|status"
JARVIS_OFFLINE_TEXT = "Enterprise Core выключен."
JARVIS_NETWORK_ERROR_TEXT = "Enterprise Core недоступен. Похоже, пропал интернет или внешний сервис не отвечает. Попробуй повторить запрос, когда сеть стабилизируется."
ADMIN_HELP_PANEL_SECTIONS = ("main", "access", "memory", "moderation", "warns", "welcome", "creator")
PUBLIC_HELP_PANEL_SECTIONS = ("public", "public_achievements", "public_appeal")
CONTROL_PANEL_SECTIONS = (
    "home",
    "profile",
    "achievements",
    "top_menu",
    "top_all",
    "top_history",
    "top_week",
    "top_day",
    "top_social",
    "top_season",
    "top_reactions_received",
    "top_reactions_given",
    "top_activity",
    "top_behavior",
    "top_achievements",
    "top_messages",
    "top_helpful",
    "top_streak",
    "appeals",
    "appeal_history",
    "admin_appeals",
    "admin_appeal_detail",
    "admin_moderation",
    "admin_warns",
    "owner_root",
    "owner_identity",
    "owner_runtime",
    "owner_git",
    "owner_jarvis",
    "owner_system_map",
    "owner_capabilities",
    "owner_automation",
    "owner_memory",
    "owner_overview",
    "owner_people",
    "owner_watchlist",
    "owner_suspects",
    "owner_reliable",
    "owner_files",
    "owner_live",
    "owner_moderation",
    "owner_selfheal",
    "owner_selfheal_queue",
    "owner_commands",
)
UI_PENDING_APPEAL = "await_appeal_text"
UI_PENDING_APPROVE_COMMENT = "await_appeal_approve_comment"
UI_PENDING_REJECT_COMMENT = "await_appeal_reject_comment"
UI_PENDING_CLOSE_COMMENT = "await_appeal_close_comment"


MODE_PROMPTS = {name: profile.system_prompt for name, profile in RUNTIME_PROFILES.items()}

JARVIS_ASSISTANT_PERSONA_NOTE = "Профиль Jarvis активен: отвечай как user-facing ассистент Дмитрия, без внутренней кухни."
OWNER_PRIORITY_NOTE = (
    "Это сообщение от создателя системы. "
    "Держи максимальный приоритет по вниманию, глубине и качеству. "
    "Отвечай собраннее, точнее и с чуть большим акцентом на его формулировку, скрытый смысл и реальные приоритеты запроса. "
    "Можно быть немного более персональным и уважительным по тону, чем с остальными, но без лести, кринжа, подхалимства и без слащавого стиля. "
    "Если есть несколько хороших вариантов ответа, для владельца выбирай самый сильный, полезный и точно сфокусированный. "
    "Фокус: точность, внимание к деталям, ясный вывод, меньше шаблонности, больше ощущения, что запрос владельца действительно стоит выше остальных."
)

ENTERPRISE_ASSISTANT_PERSONA_NOTE = ""

BASE_SYSTEM_PROMPT = ""

HELP_TEXT = COMMANDS_LIST_TEXT
PUBLIC_HELP_TEXT = (
    "JARVIS • PUBLIC ENTRY\n\n"
    "Открыт пользовательский контур: профиль, рейтинги и апелляции.\n"
    "Доступно: /start, /rating, /top, /topweek, /topday, /appeal, /appeals.\n"
    "Обычный диалог с Jarvis доступен только владельцу."
)

START_TEXT = (
    "JARVIS online. Открыты профиль, рейтинги и апелляции. /start"
)

PUBLIC_HOME_TEXT = (
    "JARVIS • PUBLIC ENTRY\n\n"
    "Здесь открыт пользовательский контур проекта:\n"
    "• личный профиль и текущий рейтинг\n"
    "• общие топы и срезы по времени\n"
    "• подача и просмотр апелляций\n\n"
    "Рейтинг помогает видеть динамику участия и вклад в сообщество.\n\n"
    "Свободный диалог с Jarvis доступен только владельцу."
)

PUBLIC_ACHIEVEMENTS_HELP_TEXT = PUBLIC_HOME_TEXT

PUBLIC_APPEAL_HELP_TEXT = (
    "JARVIS • АПЕЛЛЯЦИИ\n\n"
    "Если вы считаете санкцию ошибочной или уже неактуальной, используйте /appeal <текст> "
    "или откройте экран апелляций через /appeals.\n"
    "Система покажет текущие основания и историю прошлых решений."
)

PUBLIC_ALLOWED_COMMANDS: Set[str] = {"/start", "/rating", "/top", "/topweek", "/topday", "/appeal", "/appeals"}
PUBLIC_ALLOWED_CALLBACKS: Set[str] = {
    "ui:home",
    "ui:profile",
    "ui:achievements",
    "ui:top",
    "ui:top:all",
    "ui:top:history",
    "ui:top:week",
    "ui:top:day",
    "ui:top:social",
    "ui:top:season",
    "ui:top:reactions",
    "ui:top:given",
    "ui:top:activity",
    "ui:top:behavior",
    "ui:top:achievements",
    "ui:top:messages",
    "ui:top:helpful",
    "ui:top:streak",
    "ui:appeals",
    "ui:appeal:history",
    "ui:appeal:new",
}


class BotConfig:
    def __init__(self) -> None:
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN is required")

        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self.codex_timeout = read_int_env("CODEX_TIMEOUT", DEFAULT_CODEX_TIMEOUT, minimum=30, maximum=600)
        self.history_limit = read_int_env(
            "HISTORY_LIMIT",
            DEFAULT_HISTORY_LIMIT,
            minimum=MIN_HISTORY_LIMIT,
            maximum=MAX_HISTORY_LIMIT,
        )
        self.bridge_context_soft_limit = read_int_env(
            "BRIDGE_CONTEXT_SOFT_LIMIT",
            DEFAULT_BRIDGE_CONTEXT_SOFT_LIMIT,
            minimum=16000,
            maximum=MAX_BRIDGE_CONTEXT_SOFT_LIMIT,
        )
        self.default_mode = normalize_mode(os.getenv("DEFAULT_MODE", DEFAULT_MODE_NAME))
        self.safe_chat_only = read_bool_env("SAFE_CHAT_ONLY", DEFAULT_SAFE_CHAT_ONLY)
        self.bot_username = (os.getenv("BOT_USERNAME", DEFAULT_BOT_USERNAME).strip().lstrip("@")).lower()
        self.trigger_name = (os.getenv("TRIGGER_NAME", DEFAULT_TRIGGER_NAME).strip() or DEFAULT_TRIGGER_NAME).lower()
        self.group_spontaneous_reply_enabled = read_bool_env("GROUP_SPONTANEOUS_REPLY_ENABLED", DEFAULT_GROUP_SPONTANEOUS_REPLY_ENABLED)
        self.group_spontaneous_reply_chance_percent = read_int_env(
            "GROUP_SPONTANEOUS_REPLY_CHANCE_PERCENT",
            DEFAULT_GROUP_SPONTANEOUS_REPLY_CHANCE_PERCENT,
            minimum=0,
            maximum=100,
        )
        self.group_spontaneous_reply_cooldown_seconds = read_int_env(
            "GROUP_SPONTANEOUS_REPLY_COOLDOWN_SECONDS",
            DEFAULT_GROUP_SPONTANEOUS_REPLY_COOLDOWN_SECONDS,
            minimum=60,
            maximum=86400,
        )
        self.group_followup_window_seconds = read_int_env(
            "GROUP_FOLLOWUP_WINDOW_SECONDS",
            DEFAULT_GROUP_FOLLOWUP_WINDOW_SECONDS,
            minimum=30,
            maximum=3600,
        )
        self.group_discussion_max_turns_per_user = read_int_env(
            "GROUP_DISCUSSION_MAX_TURNS_PER_USER",
            DEFAULT_GROUP_DISCUSSION_MAX_TURNS_PER_USER,
            minimum=1,
            maximum=20,
        )
        self.group_discussion_cooldown_seconds = read_int_env(
            "GROUP_DISCUSSION_COOLDOWN_SECONDS",
            DEFAULT_GROUP_DISCUSSION_COOLDOWN_SECONDS,
            minimum=60,
            maximum=86400,
        )
        self.tmp_dir = prepare_tmp_dir(os.getenv("TMP_DIR", "").strip())
        self.stt_backend = (os.getenv("STT_BACKEND", DEFAULT_STT_BACKEND).strip() or DEFAULT_STT_BACKEND).lower()
        self.audio_transcribe_model = os.getenv("AUDIO_TRANSCRIBE_MODEL", DEFAULT_AUDIO_TRANSCRIBE_MODEL).strip() or DEFAULT_AUDIO_TRANSCRIBE_MODEL
        self.stt_language = (os.getenv("STT_LANGUAGE", DEFAULT_STT_LANGUAGE).strip() or DEFAULT_STT_LANGUAGE).lower()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url = (os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self.db_path = os.getenv("DB_PATH", DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH
        self.lock_path = os.getenv("LOCK_PATH", DEFAULT_LOCK_PATH).strip() or DEFAULT_LOCK_PATH
        self.heartbeat_path = os.getenv("HEARTBEAT_PATH", DEFAULT_HEARTBEAT_PATH).strip() or DEFAULT_HEARTBEAT_PATH
        self.heartbeat_timeout_seconds = read_int_env("HEARTBEAT_TIMEOUT_SECONDS", DEFAULT_HEARTBEAT_TIMEOUT_SECONDS, minimum=30, maximum=600)
        self.backup_interval_days = read_int_env("BACKUP_INTERVAL_DAYS", DEFAULT_BACKUP_INTERVAL_DAYS, minimum=1, maximum=365)
        self.backup_part_size_mb = read_int_env("BACKUP_PART_SIZE_MB", DEFAULT_BACKUP_PART_SIZE_MB, minimum=5, maximum=49)
        self.backup_chat_id = int(os.getenv("BACKUP_CHAT_ID", str(OWNER_USER_ID)).strip() or str(OWNER_USER_ID))
        self.owner_autofix = read_bool_env("OWNER_AUTOFIX", DEFAULT_OWNER_AUTOFIX)
        self.auto_self_heal_interval_seconds = read_int_env(
            "AUTO_SELF_HEAL_INTERVAL_SECONDS",
            DEFAULT_AUTO_SELF_HEAL_INTERVAL_SECONDS,
            minimum=60,
            maximum=3600,
        )
        self.auto_self_heal_cooldown_seconds = read_int_env(
            "AUTO_SELF_HEAL_COOLDOWN_SECONDS",
            DEFAULT_AUTO_SELF_HEAL_COOLDOWN_SECONDS,
            minimum=60,
            maximum=86400,
        )
        self.auto_self_heal_report_cooldown_seconds = read_int_env(
            "AUTO_SELF_HEAL_REPORT_COOLDOWN_SECONDS",
            DEFAULT_AUTO_SELF_HEAL_REPORT_COOLDOWN_SECONDS,
            minimum=60,
            maximum=86400,
        )
        self.auto_self_heal_max_retries = read_int_env(
            "AUTO_SELF_HEAL_MAX_RETRIES",
            DEFAULT_AUTO_SELF_HEAL_MAX_RETRIES,
            minimum=1,
            maximum=2,
        )
        self.legacy_jarvis_db_path = os.getenv("LEGACY_JARVIS_DB_PATH", DEFAULT_LEGACY_JARVIS_DB_PATH).strip() or DEFAULT_LEGACY_JARVIS_DB_PATH
        self.codex_app_server_url = (os.getenv("CODEX_APP_SERVER_URL", DEFAULT_CODEX_APP_SERVER_URL).strip() or DEFAULT_CODEX_APP_SERVER_URL)
        self.enterprise_server_base_url = (os.getenv("ENTERPRISE_SERVER_BASE_URL", DEFAULT_ENTERPRISE_SERVER_BASE_URL).strip() or DEFAULT_ENTERPRISE_SERVER_BASE_URL).rstrip("/")
        raw_enterprise_timeout = (os.getenv("ENTERPRISE_TASK_TIMEOUT", str(DEFAULT_ENTERPRISE_TASK_TIMEOUT)) or str(DEFAULT_ENTERPRISE_TASK_TIMEOUT)).strip()
        try:
            parsed_enterprise_timeout = int(raw_enterprise_timeout)
        except ValueError:
            parsed_enterprise_timeout = DEFAULT_ENTERPRISE_TASK_TIMEOUT
        self.enterprise_task_timeout = None if parsed_enterprise_timeout <= 0 else max(60, min(parsed_enterprise_timeout, 86400))
        self.owner_daily_digest_hour_utc = read_int_env("OWNER_DAILY_DIGEST_HOUR_UTC", DEFAULT_OWNER_DAILY_DIGEST_HOUR_UTC, minimum=0, maximum=23)
        self.owner_weekly_digest_weekday_utc = read_int_env("OWNER_WEEKLY_DIGEST_WEEKDAY_UTC", DEFAULT_OWNER_WEEKLY_DIGEST_WEEKDAY_UTC, minimum=0, maximum=6)


class BridgeState:
    def __init__(self, history_limit: int, default_mode: str, db_path: str) -> None:
        self.history_limit = history_limit
        self.default_mode = default_mode
        self.seen_message_keys: OrderedDict[Tuple[int, int], float] = OrderedDict()
        self.authorized_user_ids: Set[int] = set()
        self.upgrade_in_progress: Set[int] = set()
        self.global_upgrade_active = False
        self.upgrade_lock = Lock()
        self.chat_tasks_in_progress: Set[int] = set()
        self.chat_task_lock = Lock()
        self.db_lock = RLock()
        self.db_path = db_path
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_db()
        self.last_update_id = self.get_last_update_id()

    def _init_db(self) -> None:
        with self.db_lock:
            initialize_bridge_state_db(
                self,
                normalize_visual_analysis_text_func=normalize_visual_analysis_text,
                self_model_defaults=SELF_MODEL_DEFAULTS,
                default_skill_library=DEFAULT_SKILL_LIBRARY,
                drive_names=DRIVE_NAMES,
            )
            self.db.commit()

    def _ensure_warn_settings_columns(self) -> None:
        ensure_warn_settings_columns(self)

    def _ensure_warnings_columns(self) -> None:
        ensure_warnings_columns(self)

    def _ensure_chat_events_columns(self) -> None:
        ensure_chat_events_columns(self)

    def _ensure_user_memory_profile_columns(self) -> None:
        ensure_user_memory_profile_columns(self)

    def _ensure_world_state_registry_columns(self) -> None:
        ensure_world_state_registry_columns(self)

    def _ensure_request_diagnostics_columns(self) -> None:
        ensure_request_diagnostics_columns(self)

    def _seed_self_model_state(self) -> None:
        seed_self_model_state(self, self_model_defaults=SELF_MODEL_DEFAULTS)

    def _seed_skill_memory(self) -> None:
        seed_skill_memory(self, default_skill_library=DEFAULT_SKILL_LIBRARY)

    def _seed_drive_scores(self) -> None:
        seed_drive_scores(self, drive_names=DRIVE_NAMES)

    def upsert_chat_participant(
        self,
        chat_id: int,
        user_id: Optional[int],
        *,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        is_bot: bool = False,
        last_status: str = "",
        is_admin: Optional[bool] = None,
        mark_join: bool = False,
        mark_leave: bool = False,
    ) -> None:
        if user_id is None:
            return
        now = int(time.time())
        with self.db_lock:
            self.db.execute(
                """INSERT INTO chat_participants(
                    chat_id, user_id, username, first_name, last_name, is_bot, is_admin, last_status,
                    first_seen_at, last_seen_at, last_join_at, last_leave_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username = CASE WHEN excluded.username != '' THEN excluded.username ELSE chat_participants.username END,
                    first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE chat_participants.first_name END,
                    last_name = CASE WHEN excluded.last_name != '' THEN excluded.last_name ELSE chat_participants.last_name END,
                    is_bot = excluded.is_bot,
                    is_admin = CASE
                        WHEN excluded.is_admin != chat_participants.is_admin THEN excluded.is_admin
                        ELSE chat_participants.is_admin
                    END,
                    last_status = CASE
                        WHEN excluded.last_status != '' THEN excluded.last_status
                        ELSE chat_participants.last_status
                    END,
                    last_seen_at = excluded.last_seen_at,
                    last_join_at = CASE
                        WHEN excluded.last_join_at IS NOT NULL THEN excluded.last_join_at
                        ELSE chat_participants.last_join_at
                    END,
                    last_leave_at = CASE
                        WHEN excluded.last_leave_at IS NOT NULL THEN excluded.last_leave_at
                        ELSE chat_participants.last_leave_at
                    END""",
                (
                    chat_id,
                    user_id,
                    username or "",
                    first_name or "",
                    last_name or "",
                    1 if is_bot else 0,
                    1 if is_admin else 0,
                    last_status or "",
                    now,
                    now,
                    now if mark_join else None,
                    now if mark_leave else None,
                ),
            )
            self.db.commit()

    def save_chat_member_count(self, chat_id: int, member_count: int) -> None:
        with self.db_lock:
            self.db.execute(
                """INSERT INTO chat_runtime_cache(chat_id, member_count, member_count_synced_at, updated_at)
                VALUES(?, ?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(chat_id) DO UPDATE SET
                    member_count = excluded.member_count,
                    member_count_synced_at = excluded.member_count_synced_at,
                    updated_at = excluded.updated_at""",
                (chat_id, int(member_count)),
            )
            self.db.commit()

    def save_chat_title(self, chat_id: int, chat_title: str) -> None:
        normalized_title = normalize_whitespace(chat_title)
        if not normalized_title:
            return
        with self.db_lock:
            self.db.execute(
                """INSERT INTO chat_runtime_cache(chat_id, chat_title, updated_at)
                VALUES(?, ?, strftime('%s','now'))
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_title = excluded.chat_title,
                    updated_at = excluded.updated_at""",
                (chat_id, normalized_title),
            )
            self.db.commit()

    def mark_admins_synced(
        self,
        chat_id: int,
        admin_rows: List[Tuple[int, str, str, str, int, str]],
    ) -> None:
        synced_at = int(time.time())
        with self.db_lock:
            self.db.execute("UPDATE chat_participants SET is_admin = 0 WHERE chat_id = ?", (chat_id,))
            for user_id, username, first_name, last_name, is_bot, status in admin_rows:
                self.db.execute(
                    """INSERT INTO chat_participants(
                        chat_id, user_id, username, first_name, last_name, is_bot, is_admin, last_status,
                        first_seen_at, last_seen_at, last_join_at, last_leave_at
                    ) VALUES(?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, NULL)
                    ON CONFLICT(chat_id, user_id) DO UPDATE SET
                        username = CASE WHEN excluded.username != '' THEN excluded.username ELSE chat_participants.username END,
                        first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE chat_participants.first_name END,
                        last_name = CASE WHEN excluded.last_name != '' THEN excluded.last_name ELSE chat_participants.last_name END,
                        is_bot = excluded.is_bot,
                        is_admin = 1,
                        last_status = CASE WHEN excluded.last_status != '' THEN excluded.last_status ELSE chat_participants.last_status END,
                        last_seen_at = excluded.last_seen_at""",
                    (
                        chat_id,
                        user_id,
                        username or "",
                        first_name or "",
                        last_name or "",
                        int(is_bot or 0),
                        status or "",
                        synced_at,
                        synced_at,
                    ),
                )
            self.db.execute(
                """INSERT INTO chat_runtime_cache(chat_id, admins_synced_at, updated_at)
                VALUES(?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(chat_id) DO UPDATE SET
                    admins_synced_at = excluded.admins_synced_at,
                    updated_at = excluded.updated_at""",
                (chat_id,),
            )
            self.db.commit()

    def get_chat_runtime_snapshot(self, chat_id: int) -> sqlite3.Row:
        with self.db_lock:
            row = self.db.execute(
                """SELECT chat_title, member_count, admins_synced_at, member_count_synced_at, updated_at
                FROM chat_runtime_cache
                WHERE chat_id = ?""",
                (chat_id,),
            ).fetchone()
        return row

    def get_chat_title(self, chat_id: int, fallback_title: str = "") -> str:
        normalized_fallback = normalize_whitespace(fallback_title)
        if normalized_fallback:
            self.save_chat_title(chat_id, normalized_fallback)
            return normalized_fallback
        with self.db_lock:
            row = self.db.execute(
                "SELECT chat_title FROM chat_runtime_cache WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row and row["chat_title"]:
            return str(row["chat_title"])
        return f"chat_id={chat_id}"

    def get_chat_participants_context(self, chat_id: int, query: str = "", limit: int = 12) -> str:
        lowered = (query or "").lower()
        include = any(
            token in lowered for token in (
                "участ", "люд", "кто в чате", "кто есть", "админ", "мембер", "member", "members",
                "состав", "кто тут", "кто здесь", "пользоват"
            )
        )
        if not include:
            return ""
        with self.db_lock:
            stats = self.db.execute(
                """SELECT
                    COUNT(*) AS known_participants,
                    SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END) AS admins_count,
                    SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END) AS bots_count
                FROM chat_participants
                WHERE chat_id = ?""",
                (chat_id,),
            ).fetchone()
            runtime_row = self.db.execute(
                "SELECT chat_title, member_count, admins_synced_at, member_count_synced_at FROM chat_runtime_cache WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            recent_rows = self.db.execute(
                """SELECT user_id, username, first_name, last_name, is_admin, last_status, last_seen_at
                FROM chat_participants
                WHERE chat_id = ?
                ORDER BY is_admin DESC, last_seen_at DESC
                LIMIT ?""",
                (chat_id, limit),
            ).fetchall()
        lines = ["Participants registry:"]
        known_count = int((stats[0] or 0) if stats else 0)
        admins_count = int((stats[1] or 0) if stats else 0)
        bots_count = int((stats[2] or 0) if stats else 0)
        member_count = int(runtime_row[1] or 0) if runtime_row else 0
        lines.append(
            f"- known_participants={known_count}; admins_known={admins_count}; bots_known={bots_count}; member_count={member_count}"
        )
        if runtime_row:
            lines.append(
                f"- admins_synced_at={int(runtime_row[2] or 0)}; member_count_synced_at={int(runtime_row[3] or 0)}"
            )
        if recent_rows:
            lines.append("recent_known_participants:")
            for row in recent_rows:
                label = build_actor_name(row[0], row[1] or "", row[2] or "", row[3] or "", "user")
                status_bits = []
                if int(row[4] or 0):
                    status_bits.append("admin")
                if row[5]:
                    status_bits.append(str(row[5]))
                status_text = ", ".join(status_bits) or "seen"
                lines.append(f"- {label}; {status_text}; last_seen_at={int(row[6] or 0)}")
        return "\n".join(lines)

    def _rebuild_chat_events_fts(self) -> None:
        self.db.execute("INSERT INTO chat_events_fts(chat_events_fts) VALUES('rebuild')")

    def get_last_update_id(self) -> Optional[int]:
        with self.db_lock:
            row = self.db.execute(
                "SELECT value FROM bot_meta WHERE key = ?",
                ("last_update_id",),
            ).fetchone()
        if not row or row[0] is None:
            return None
        try:
            return int(str(row[0]).strip())
        except (TypeError, ValueError):
            return None

    def set_last_update_id(self, update_id: Optional[int]) -> None:
        self.last_update_id = update_id
        if update_id is None:
            return
        with self.db_lock:
            self.db.execute(
                "INSERT INTO bot_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("last_update_id", str(int(update_id))),
            )
            self.db.commit()

    def get_history(self, chat_id: int) -> Deque[Tuple[str, str]]:
        return _get_history_service(self, chat_id)

    def get_summary(self, chat_id: int) -> str:
        return _get_summary_service(self, chat_id)

    def update_summary(self, chat_id: int) -> None:
        _update_summary_service(
            self,
            chat_id,
            truncate_text_func=truncate_text,
            build_actor_name_func=build_actor_name,
        )

    def update_group_deep_profile(self, chat_id: int, limit: int = 120) -> None:
        with self.db_lock:
            rows = self.db.execute(
                """
                SELECT created_at, user_id, username, first_name, last_name, role, message_type, text
                FROM chat_events
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
            runtime_row = self.db.execute(
                """
                SELECT chat_title, member_count
                FROM chat_runtime_cache
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if not rows:
            return
        recent_rows = list(reversed(rows))
        user_rows = [row for row in recent_rows if (row["role"] or "") == "user"]
        actor_counts: Dict[str, int] = {}
        topic_counts: Dict[str, int] = {}
        rough_markers = 0
        laugh_markers = 0
        duplicate_markers = 0
        previous_actor = ""
        streak = 0
        max_streak = 0
        last_text_by_actor: Dict[str, str] = {}
        for row in user_rows:
            actor = build_actor_name(
                row["user_id"],
                row["username"] or "",
                row["first_name"] or "",
                row["last_name"] or "",
                "user",
            )
            actor_counts[actor] = actor_counts.get(actor, 0) + 1
            text = normalize_whitespace(row["text"] or "")
            lowered = text.lower()
            for keyword in extract_keywords(text):
                if keyword.isdigit():
                    continue
                topic_counts[keyword] = topic_counts.get(keyword, 0) + 1
            if any(token in lowered for token in ("ахах", "хаха", "))))", "😂", "😁", "😄")):
                laugh_markers += 1
            if any(token in lowered for token in ("нах", "охуе", "говно", "заеб", "пизд", "заткнись")):
                rough_markers += 1
            if len(lowered) >= 8 and last_text_by_actor.get(actor, "") == lowered:
                duplicate_markers += 1
            last_text_by_actor[actor] = lowered
            if actor == previous_actor:
                streak += 1
            else:
                previous_actor = actor
                streak = 1
            max_streak = max(max_streak, streak)
        top_speakers = ", ".join(
            f"{name}={count}" for name, count in sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        )
        top_topics = ", ".join(
            f"{name}={count}" for name, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        )
        tone_bits: List[str] = []
        if laugh_markers >= 3:
            tone_bits.append("ирония/смех")
        if rough_markers >= 2:
            tone_bits.append("жёсткий или конфликтный тон")
        if duplicate_markers >= 2:
            tone_bits.append("повторы")
        if max_streak >= 3:
            tone_bits.append("серии сообщений подряд")
        lines = ["Group deep profile:"]
        if runtime_row:
            chat_title = normalize_whitespace(runtime_row["chat_title"] or "")
            if chat_title:
                lines.append(f"- title: {truncate_text(chat_title, 120)}")
            if int(runtime_row["member_count"] or 0) > 0:
                lines.append(f"- member_count: {int(runtime_row['member_count'] or 0)}")
        if top_speakers:
            lines.append(f"- top_speakers: {truncate_text(top_speakers, 320)}")
        if top_topics:
            lines.append(f"- recurring_topics: {truncate_text(top_topics, 360)}")
        if tone_bits:
            lines.append(f"- tone: {', '.join(tone_bits)}")
        if user_rows:
            recent_examples = [
                truncate_text(normalize_whitespace(row["text"] or ""), 140)
                for row in user_rows[-8:]
                if normalize_whitespace(row["text"] or "")
            ]
            if recent_examples:
                lines.append("- recent_examples:")
                lines.extend(f"  • {item}" for item in recent_examples[:5])
        profile_text = truncate_text("\n".join(lines), 2200)
        with self.db_lock:
            recent_snapshot = self.db.execute(
                "SELECT summary, created_at FROM summary_snapshots WHERE chat_id = ? AND scope = 'group_deep_profile' ORDER BY id DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
            should_snapshot = True
            if recent_snapshot:
                previous_summary = recent_snapshot[0] or ""
                previous_ts = int(recent_snapshot[1] or 0)
                if previous_summary == profile_text and previous_ts >= int(time.time()) - 1800:
                    should_snapshot = False
            if should_snapshot:
                self.db.execute(
                    "INSERT INTO summary_snapshots(chat_id, scope, summary) VALUES(?, 'group_deep_profile', ?)",
                    (chat_id, profile_text),
                )
                self.db.commit()

    def add_fact(self, chat_id: int, fact: str, created_by_user_id: Optional[int]) -> None:
        _add_fact_service(self, chat_id, fact, created_by_user_id, normalize_whitespace_func=normalize_whitespace)

    def get_facts(self, chat_id: int, query: str = "", limit: int = 12) -> List[str]:
        return _get_facts_service(self, chat_id, query=query, limit=limit, extract_keywords_func=extract_keywords)

    def render_facts(self, chat_id: int, query: str = "", limit: int = 12) -> str:
        return _render_facts_service(
            self,
            chat_id,
            query=query,
            limit=limit,
            truncate_text_func=truncate_text,
            extract_keywords_func=extract_keywords,
        )

    def get_mode(self, chat_id: int) -> str:
        return _get_mode_service(self, chat_id, normalize_mode_func=normalize_mode)

    def normalize_whitespace(self, text: str) -> str:
        return normalize_whitespace(text)

    def set_mode(self, chat_id: int, mode: str) -> None:
        _set_mode_service(self, chat_id, mode)

    def reset_chat(self, chat_id: int) -> None:
        _reset_chat_service(self, chat_id)

    def append_history(self, chat_id: int, role: str, text: str) -> None:
        _append_history_service(self, chat_id, role, text, normalize_whitespace_func=normalize_whitespace)

    def update_event_text(
        self,
        chat_id: int,
        message_id: Optional[int],
        text: str,
        message_type: Optional[str] = None,
        has_media: Optional[int] = None,
        file_kind: Optional[str] = None,
    ) -> bool:
        return _update_event_text_service(
            self,
            chat_id,
            message_id,
            text,
            message_type=message_type,
            has_media=has_media,
            file_kind=file_kind,
            normalize_whitespace_func=normalize_whitespace,
        )

    def record_event(
        self,
        chat_id: int,
        user_id: Optional[int],
        role: str,
        message_type: str,
        text: str,
        message_id: Optional[int] = None,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        chat_type: str = "",
        reply_to_message_id: Optional[int] = None,
        reply_to_user_id: Optional[int] = None,
        reply_to_username: str = "",
        forward_origin: str = "",
        has_media: int = 0,
        file_kind: str = "",
        is_edited: int = 0,
    ) -> None:
        _record_event_service(
            self,
            chat_id,
            user_id,
            role,
            message_type,
            text,
            message_id=message_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            chat_type=chat_type,
            reply_to_message_id=reply_to_message_id,
            reply_to_user_id=reply_to_user_id,
            reply_to_username=reply_to_username,
            forward_origin=forward_origin,
            has_media=has_media,
            file_kind=file_kind,
            is_edited=is_edited,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_participant_profile_context(self, chat_id: int, target_user_id: Optional[int] = None, target_username: str = "", limit: int = 40) -> Tuple[str, str]:
        username_filter = target_username.lstrip("@").lower()
        if target_user_id is not None:
            self.refresh_participant_behavior_profile(target_user_id, chat_id=chat_id)
        with self.db_lock:
            if target_user_id is not None:
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'user' AND user_id = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, target_user_id, limit),
                ).fetchall()
            elif username_filter:
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'user' AND lower(username) = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, username_filter, limit),
                ).fetchall()
            else:
                rows = []
        if not rows:
            return "", ""
        latest = rows[0]
        label = build_actor_name(latest[1], latest[2] or "", latest[3] or "", latest[4] or "", "user")
        lines = []
        type_counts = {}
        for created_at, user_id, username, first_name, last_name, message_type, content in reversed(rows):
            stamp = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
            lines.append(f"[{stamp}] ({message_type}) {truncate_text(content, 320)}")
            type_counts[message_type] = type_counts.get(message_type, 0) + 1
        stats = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))
        behavior_context = self.get_participant_behavior_context(chat_id, target_user_id=target_user_id)
        context_parts = [f"Participant: {label}", f"Messages sampled: {len(rows)}", f"Types: {stats}"]
        if behavior_context:
            context_parts.extend(["", behavior_context])
        context = "\n".join(context_parts) + "\n\n" + "\n".join(lines)
        return label, context

    def _analyze_participant_rows(self, rows: Sequence[sqlite3.Row], owner_user_id: int = OWNER_USER_ID) -> Dict[str, object]:
        return _analyze_participant_rows_service(
            rows,
            build_actor_name_func=build_actor_name,
            is_owner_identity_func=is_owner_identity,
            normalize_whitespace_func=normalize_whitespace,
        )

    def refresh_participant_behavior_profile(self, user_id: int, chat_id: Optional[int] = None) -> None:
        _refresh_participant_behavior_profile_service(
            self,
            user_id,
            chat_id=chat_id,
            truncate_text_func=truncate_text,
            normalize_visual_analysis_text_func=normalize_visual_analysis_text,
            build_actor_name_func=build_actor_name,
            is_owner_identity_func=is_owner_identity,
        )

    def get_participant_behavior_context(self, chat_id: int, target_user_id: Optional[int] = None) -> str:
        return _get_participant_behavior_context_service(
            self,
            chat_id,
            target_user_id=target_user_id,
            translate_risk_flag_func=translate_risk_flag,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
            normalize_visual_analysis_text_func=normalize_visual_analysis_text,
        )

    def record_participant_visual_signal(
        self,
        *,
        chat_id: int,
        user_id: int,
        message_id: int,
        file_unique_id: str,
        media_sha256: str,
        caption: str,
        analysis_text: str,
        risk_flags: List[str],
    ) -> None:
        _record_participant_visual_signal_service(
            self,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            file_unique_id=file_unique_id,
            media_sha256=media_sha256,
            caption=caption,
            analysis_text=analysis_text,
            risk_flags=risk_flags,
            truncate_text_func=truncate_text,
            normalize_visual_analysis_text_func=normalize_visual_analysis_text,
        )

    def get_visual_signal_for_message(self, chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
        return _get_visual_signal_for_message_service(self, chat_id, message_id)

    def record_message_subject(
        self,
        *,
        chat_id: int,
        message_id: int,
        subject_type: str,
        source_kind: str,
        user_id: int = 0,
        summary: str = "",
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        _record_message_subject_service(
            self,
            chat_id=chat_id,
            message_id=message_id,
            subject_type=subject_type,
            source_kind=source_kind,
            user_id=user_id,
            summary=summary,
            details=details,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_message_subject(self, chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
        return _get_message_subject_service(self, chat_id, message_id)

    def set_active_subject(
        self,
        *,
        chat_id: int,
        user_id: Optional[int],
        message_id: int,
        subject_type: str,
        source: str = "",
    ) -> None:
        _set_active_subject_service(
            self,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            subject_type=subject_type,
            source=source,
        )

    def get_active_subject(self, chat_id: int, user_id: Optional[int]) -> Optional[Dict[str, object]]:
        return _get_active_subject_service(self, chat_id, user_id)

    def refresh_user_memory_profile(
        self,
        chat_id: int,
        user_id: Optional[int],
        username: str = "",
        first_name: str = "",
        last_name: str = "",
    ) -> None:
        _refresh_user_memory_profile_service(
            self,
            chat_id,
            user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            owner_user_id=OWNER_USER_ID,
            owner_memory_chat_id=OWNER_MEMORY_CHAT_ID,
            build_actor_name_func=build_actor_name,
            truncate_text_func=truncate_text,
        )

    def get_user_memory_context(
        self,
        chat_id: int,
        user_id: Optional[int] = None,
        reply_to_user_id: Optional[int] = None,
        limit: int = 2,
    ) -> str:
        return _get_user_memory_context_service(
            self,
            chat_id,
            user_id=user_id,
            reply_to_user_id=reply_to_user_id,
            limit=limit,
            render_user_memory_context_func=_render_user_memory_context,
            owner_user_id=OWNER_USER_ID,
            owner_memory_chat_id=OWNER_MEMORY_CHAT_ID,
            build_actor_name_func=build_actor_name,
            truncate_text_func=truncate_text,
        )

    def get_owner_cross_chat_memory_context(self, limit: int = 4) -> str:
        with self.db_lock:
            event_rows = self.db.execute(
                """
                SELECT e.chat_id, COALESCE(MAX(NULLIF(c.chat_title, '')), '') AS chat_title, COUNT(*) AS cnt, MAX(e.created_at) AS last_ts
                FROM chat_events e
                LEFT JOIN chat_runtime_cache c ON c.chat_id = e.chat_id
                WHERE e.role = 'user' AND e.user_id = ? AND e.chat_id < 0
                GROUP BY e.chat_id
                ORDER BY last_ts DESC
                LIMIT ?
                """,
                (OWNER_USER_ID, max(2, limit * 2)),
            ).fetchall()
            relation_rows = self.db.execute(
                """
                SELECT
                    other.user_id AS other_user_id,
                    COALESCE(MAX(NULLIF(other.username, '')), '') AS username,
                    COALESCE(MAX(NULLIF(other.first_name, '')), '') AS first_name,
                    COALESCE(MAX(NULLIF(other.last_name, '')), '') AS last_name,
                    COUNT(*) AS overlap_count,
                    COUNT(DISTINCT owner.chat_id) AS shared_chat_count,
                    MAX(owner.created_at) AS last_ts
                FROM chat_events owner
                JOIN chat_events other
                  ON other.chat_id = owner.chat_id
                 AND other.role = 'user'
                 AND other.user_id IS NOT NULL
                 AND owner.user_id IS NOT NULL
                 AND other.user_id != owner.user_id
                WHERE owner.role = 'user'
                  AND owner.user_id = ?
                  AND owner.chat_id < 0
                GROUP BY other.user_id
                ORDER BY shared_chat_count DESC, overlap_count DESC, last_ts DESC
                LIMIT ?
                """,
                (OWNER_USER_ID, max(3, limit)),
            ).fetchall()
            summary_rows = self.db.execute(
                """
                SELECT s.chat_id, s.scope, s.summary, s.created_at
                FROM summary_snapshots s
                WHERE s.chat_id IN (
                    SELECT DISTINCT chat_id
                    FROM chat_events
                    WHERE role = 'user' AND user_id = ? AND chat_id < 0
                )
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (OWNER_USER_ID, max(4, limit * 3)),
            ).fetchall()
        if not event_rows:
            return ""
        lines = ["Owner cross-chat memory:"]
        top_chats = []
        for row in event_rows[:limit]:
            chat_id_value = int(row["chat_id"] or 0)
            chat_title = normalize_whitespace(row["chat_title"] or "") or str(chat_id_value)
            top_chats.append(chat_id_value)
            lines.append(
                f"- active_chat: {truncate_text(chat_title, 80)}; messages={int(row['cnt'] or 0)}; chat_id={chat_id_value}"
            )
        if relation_rows:
            lines.append("Owner relation layer:")
            for row in relation_rows[:limit]:
                actor = build_actor_name(
                    int(row["other_user_id"] or 0),
                    row["username"] or "",
                    row["first_name"] or "",
                    row["last_name"] or "",
                    "user",
                )
                lines.append(
                    f"- {actor}: shared_chats={int(row['shared_chat_count'] or 0)}; overlap={int(row['overlap_count'] or 0)}"
                )
        added = 0
        for row in summary_rows:
            chat_id_value = int(row["chat_id"] or 0)
            if chat_id_value not in top_chats:
                continue
            stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
            summary_text = normalize_whitespace(row["summary"] or "")
            if not summary_text:
                continue
            lines.append(
                f"- recent_group_summary [{stamp}] chat_id={chat_id_value}: {truncate_text(summary_text, 220)}"
            )
            added += 1
            if added >= limit:
                break
        return "\n".join(lines)

    def get_chat_profile_context(self, chat_id: int, limit: int = 6) -> str:
        with self.db_lock:
            runtime_row = self.db.execute(
                """
                SELECT chat_title, member_count, admins_synced_at, member_count_synced_at
                FROM chat_runtime_cache
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            participant_rows = self.db.execute(
                """
                SELECT user_id, username, first_name, last_name, is_admin, last_status, last_seen_at
                FROM chat_participants
                WHERE chat_id = ?
                ORDER BY is_admin DESC, last_seen_at DESC
                LIMIT ?
                """,
                (chat_id, max(4, limit)),
            ).fetchall()
            top_rows = self.db.execute(
                """
                SELECT user_id, username, first_name, last_name, COUNT(*) AS cnt
                FROM chat_events
                WHERE chat_id = ? AND role = 'user'
                GROUP BY user_id, username, first_name, last_name
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (chat_id, max(4, limit)),
            ).fetchall()
            deep_profile_row = self.db.execute(
                """
                SELECT summary
                FROM summary_snapshots
                WHERE chat_id = ? AND scope = 'group_deep_profile'
                ORDER BY id DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        lines = ["Group profile:"]
        if runtime_row:
            chat_title = normalize_whitespace(runtime_row["chat_title"] or "")
            if chat_title:
                lines.append(f"- title: {truncate_text(chat_title, 100)}")
            if int(runtime_row["member_count"] or 0) > 0:
                lines.append(f"- member_count: {int(runtime_row['member_count'] or 0)}")
        if top_rows:
            active = ", ".join(
                f"{build_actor_name(row['user_id'], row['username'] or '', row['first_name'] or '', row['last_name'] or '', 'user')}={int(row['cnt'] or 0)}"
                for row in top_rows[:limit]
            )
            lines.append(f"- top_speakers: {truncate_text(active, 320)}")
        if participant_rows:
            admins = [
                build_actor_name(row["user_id"], row["username"] or "", row["first_name"] or "", row["last_name"] or "", "user")
                for row in participant_rows
                if int(row["is_admin"] or 0)
            ]
            if admins:
                lines.append(f"- known_admins: {truncate_text(', '.join(admins[:limit]), 220)}")
        if deep_profile_row and deep_profile_row["summary"]:
            lines.append(truncate_text(normalize_whitespace(deep_profile_row["summary"] or ""), 900))
        return "\n".join(lines) if len(lines) > 1 else ""

    def get_actor_labels(self, chat_id: int, user_ids: List[int]) -> Dict[int, str]:
        normalized_ids = sorted({int(user_id) for user_id in user_ids if user_id is not None})
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        params: List[object] = [chat_id, *normalized_ids]
        with self.db_lock:
            participant_rows = self.db.execute(
                f"""SELECT user_id, username, first_name, last_name
                FROM chat_participants
                WHERE chat_id = ? AND user_id IN ({placeholders})""",
                params,
            ).fetchall()
            event_rows = self.db.execute(
                f"""SELECT user_id, username, first_name, last_name
                FROM chat_events
                WHERE chat_id = ? AND user_id IN ({placeholders})
                ORDER BY id DESC
                LIMIT {max(12, len(normalized_ids) * 3)}""",
                params,
            ).fetchall()
        labels: Dict[int, str] = {}
        for row in participant_rows:
            if row[0] is None:
                continue
            labels[int(row[0])] = build_actor_name(int(row[0]), row[1] or "", row[2] or "", row[3] or "", "user")
        for row in event_rows:
            if row[0] is None:
                continue
            labels.setdefault(int(row[0]), build_actor_name(int(row[0]), row[1] or "", row[2] or "", row[3] or "", "user"))
        for user_id in normalized_ids:
            labels.setdefault(user_id, build_actor_name(user_id, "", "", "", "user"))
        return labels

    def refresh_relation_memory(self, chat_id: int, limit_pairs: int = 12, sample_limit: int = 180) -> bool:
        with self.db_lock:
            rows = self.db.execute(
                """SELECT created_at, user_id, username, first_name, last_name, reply_to_user_id, text
                FROM chat_events
                WHERE chat_id = ? AND role = 'user'
                ORDER BY id DESC
                LIMIT ?""",
                (chat_id, max(60, sample_limit)),
            ).fetchall()
            bot_rows = self.db.execute(
                "SELECT user_id FROM chat_participants WHERE chat_id = ? AND is_bot = 1",
                (chat_id,),
            ).fetchall()
        if len(rows) < 8:
            return False
        bot_user_ids = {int(row[0]) for row in bot_rows if row[0] is not None}
        recent_rows = list(reversed(rows))
        pair_stats: Dict[Tuple[int, int], Dict[str, object]] = {}
        recent_window: List[int] = []
        for created_at, user_id, username, first_name, last_name, reply_to_user_id, text in recent_rows:
            if user_id is None:
                continue
            actor_id = int(user_id)
            if actor_id in bot_user_ids:
                continue
            cleaned = (text or "").lower()
            distinct_recent = []
            for seen_user_id in reversed(recent_window):
                if seen_user_id == actor_id or seen_user_id in distinct_recent:
                    continue
                distinct_recent.append(seen_user_id)
                if len(distinct_recent) >= 4:
                    break
            for peer_id in distinct_recent:
                low_id, high_id = sorted((actor_id, peer_id))
                stats = pair_stats.setdefault(
                    (low_id, high_id),
                    {
                        "reply_low_to_high": 0,
                        "reply_high_to_low": 0,
                        "co_presence": 0,
                        "humor": 0,
                        "rough": 0,
                        "support": 0,
                        "topics": {},
                        "last_interaction_at": 0,
                    },
                )
                stats["co_presence"] = int(stats["co_presence"]) + 1
                stats["last_interaction_at"] = max(int(stats["last_interaction_at"]), int(created_at or 0))
                if any(token in cleaned for token in ("ахах", "хаха", "))))", "😂", "😁", "😄")):
                    stats["humor"] = int(stats["humor"]) + 1
                if any(token in cleaned for token in ("нах", "охуе", "говно", "заеб", "пизд")):
                    stats["rough"] = int(stats["rough"]) + 1
                if any(token in cleaned for token in ("спасибо", "красава", "норм", "хорош", "поддерж", "молодец")):
                    stats["support"] = int(stats["support"]) + 1
                topics = stats["topics"]
                for marker in ("бот", "jarvis", "осознан", "контекст", "стиль", "тест", "чат", "памят", "серьез", "цикл"):
                    if marker in cleaned:
                        topics[marker] = int(topics.get(marker, 0)) + 1
            recent_window.append(actor_id)
            if len(recent_window) > 8:
                recent_window = recent_window[-8:]
            if reply_to_user_id is None:
                continue
            target_id = int(reply_to_user_id)
            if target_id == actor_id or target_id in bot_user_ids:
                continue
            low_id, high_id = sorted((actor_id, target_id))
            stats = pair_stats.setdefault(
                (low_id, high_id),
                {
                    "reply_low_to_high": 0,
                    "reply_high_to_low": 0,
                    "co_presence": 0,
                    "humor": 0,
                    "rough": 0,
                    "support": 0,
                    "topics": {},
                    "last_interaction_at": 0,
                },
            )
            if actor_id == low_id and target_id == high_id:
                stats["reply_low_to_high"] = int(stats["reply_low_to_high"]) + 1
            else:
                stats["reply_high_to_low"] = int(stats["reply_high_to_low"]) + 1
            stats["last_interaction_at"] = max(int(stats["last_interaction_at"]), int(created_at or 0))
        ranked_pairs: List[Tuple[Tuple[int, int], Dict[str, object], int]] = []
        for pair_key, stats in pair_stats.items():
            reply_total = int(stats["reply_low_to_high"]) + int(stats["reply_high_to_low"])
            co_presence = int(stats["co_presence"])
            score = reply_total * 4 + min(co_presence, 8)
            if score <= 0:
                continue
            ranked_pairs.append((pair_key, stats, score))
        ranked_pairs.sort(key=lambda item: (-item[2], -int(item[1]["last_interaction_at"]), item[0][0], item[0][1]))
        if not ranked_pairs:
            return False
        user_ids: List[int] = []
        for (low_id, high_id), _stats, _score in ranked_pairs[:limit_pairs]:
            user_ids.extend([low_id, high_id])
        labels = self.get_actor_labels(chat_id, user_ids)
        payload_rows: List[Tuple[int, int, int, int, int, int, int, int, str, str, int, float]] = []
        for (low_id, high_id), stats, score in ranked_pairs[:limit_pairs]:
            reply_low_to_high = int(stats["reply_low_to_high"])
            reply_high_to_low = int(stats["reply_high_to_low"])
            co_presence = int(stats["co_presence"])
            humor = int(stats["humor"])
            rough = int(stats["rough"])
            support = int(stats["support"])
            topic_items = sorted(
                ((str(name), int(count)) for name, count in dict(stats["topics"]).items()),
                key=lambda item: (-item[1], item[0]),
            )[:5]
            topic_markers = ", ".join(f"{name}={count}" for name, count in topic_items)
            summary_bits: List[str] = []
            if reply_low_to_high and reply_high_to_low:
                summary_bits.append("взаимные ответы")
            elif reply_low_to_high:
                summary_bits.append(f"{labels.get(low_id, f'user_id={low_id}')} чаще отвечает {labels.get(high_id, f'user_id={high_id}')}")
            elif reply_high_to_low:
                summary_bits.append(f"{labels.get(high_id, f'user_id={high_id}')} чаще отвечает {labels.get(low_id, f'user_id={low_id}')}")
            if co_presence >= 4:
                summary_bits.append("часто пересекаются в одном фрагменте диалога")
            if humor >= 2:
                summary_bits.append("в связке заметна ирония/смех")
            if rough >= 1:
                summary_bits.append("бывает грубоватый дружеский тон")
            if support >= 2:
                summary_bits.append("заметны поддерживающие реакции")
            if topic_markers:
                summary_bits.append(f"общие маркеры: {topic_markers}")
            summary = truncate_text(". ".join(summary_bits), 380)
            confidence = min(1.0, round(score / 16.0, 2))
            payload_rows.append(
                (
                    chat_id,
                    low_id,
                    high_id,
                    reply_low_to_high,
                    reply_high_to_low,
                    co_presence,
                    humor,
                    rough,
                    support,
                    topic_markers,
                    summary,
                    int(stats["last_interaction_at"]),
                    confidence,
                )
            )
        with self.db_lock:
            self.db.execute("DELETE FROM relation_memory WHERE chat_id = ?", (chat_id,))
            self.db.executemany(
                """INSERT INTO relation_memory(
                    chat_id, user_low_id, user_high_id, reply_count_low_to_high, reply_count_high_to_low,
                    co_presence_count, humor_markers, rough_markers, support_markers, topic_markers,
                    summary, last_interaction_at, confidence, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))""",
                payload_rows,
            )
            self.db.commit()
        return True

    def get_relation_memory_context(
        self,
        chat_id: int,
        user_id: Optional[int] = None,
        reply_to_user_id: Optional[int] = None,
        query: str = "",
        limit: int = 4,
    ) -> str:
        normalized_targets: List[int] = []
        for candidate in [user_id, reply_to_user_id]:
            if candidate is None:
                continue
            candidate_int = int(candidate)
            if candidate_int not in normalized_targets:
                normalized_targets.append(candidate_int)
        should_focus_chat = detect_local_chat_query(query)
        with self.db_lock:
            existing_count = self.db.execute(
                "SELECT COUNT(*) FROM relation_memory WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if int(existing_count[0] or 0) == 0:
            self.refresh_relation_memory(chat_id)
        with self.db_lock:
            if normalized_targets:
                placeholders = ",".join("?" for _ in normalized_targets)
                rows = self.db.execute(
                    f"""SELECT user_low_id, user_high_id, reply_count_low_to_high, reply_count_high_to_low,
                    co_presence_count, humor_markers, rough_markers, support_markers, topic_markers,
                    summary, last_interaction_at, confidence
                    FROM relation_memory
                    WHERE chat_id = ? AND (user_low_id IN ({placeholders}) OR user_high_id IN ({placeholders}))
                    ORDER BY (reply_count_low_to_high + reply_count_high_to_low) DESC, co_presence_count DESC, last_interaction_at DESC
                    LIMIT ?""",
                    [chat_id, *normalized_targets, *normalized_targets, max(2, limit)],
                ).fetchall()
            elif should_focus_chat:
                rows = self.db.execute(
                    """SELECT user_low_id, user_high_id, reply_count_low_to_high, reply_count_high_to_low,
                    co_presence_count, humor_markers, rough_markers, support_markers, topic_markers,
                    summary, last_interaction_at, confidence
                    FROM relation_memory
                    WHERE chat_id = ?
                    ORDER BY last_interaction_at DESC, (reply_count_low_to_high + reply_count_high_to_low) DESC, co_presence_count DESC
                    LIMIT ?""",
                    (chat_id, max(2, limit)),
                ).fetchall()
            else:
                rows = []
        if not rows:
            return ""
        user_ids: List[int] = []
        for row in rows:
            user_ids.extend([int(row[0]), int(row[1])])
        labels = self.get_actor_labels(chat_id, user_ids)
        return _render_relation_memory_context(rows, labels, limit=limit, truncate_text_func=truncate_text)

    def get_self_model_state(self) -> sqlite3.Row:
        with self.db_lock:
            row = self.db.execute(
                """SELECT identity, active_mode, capabilities, hard_limitations, trusted_tools, confidence_policy,
                current_goals, active_constraints, honesty_rules, jarvis_style_invariants,
                enterprise_style_invariants, last_route_kind, last_outcome, updated_at
                FROM self_model_state
                WHERE state_id = 'primary'"""
            ).fetchone()
        if row is None:
            raise RuntimeError("self_model_state is not initialized")
        return row

    def update_self_model_state(self, **updates: str) -> None:
        allowed = {
            "identity",
            "active_mode",
            "capabilities",
            "hard_limitations",
            "trusted_tools",
            "confidence_policy",
            "current_goals",
            "active_constraints",
            "honesty_rules",
            "jarvis_style_invariants",
            "enterprise_style_invariants",
            "last_route_kind",
            "last_outcome",
        }
        assignments: List[str] = []
        params: List[object] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            assignments.append(f"{key} = ?")
            params.append(truncate_text(normalize_whitespace(str(value)), 1200))
        if not assignments:
            return
        assignments.append("updated_at = strftime('%s','now')")
        with self.db_lock:
            self.db.execute(
                f"UPDATE self_model_state SET {', '.join(assignments)} WHERE state_id = 'primary'",
                params,
            )
            self.db.commit()

    def get_self_model_context(self, persona: str) -> str:
        row = self.get_self_model_state()
        return _render_self_model_context(row, persona, truncate_text)

    def record_autobiographical_event(
        self,
        *,
        category: str,
        event_type: str,
        title: str,
        details: str,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        route_kind: str = "",
        status: str = "",
        importance: int = 0,
        open_state: str = "closed",
        tags: str = "",
        observed_payload: Optional[dict] = None,
    ) -> int:
        with self.db_lock:
            cursor = self.db.execute(
                """INSERT INTO autobiographical_memory(
                    category, event_type, chat_id, user_id, route_kind, title, details, status,
                    importance, open_state, tags, observed_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))""",
                (
                    truncate_text(category, 80),
                    truncate_text(event_type, 80),
                    chat_id,
                    user_id,
                    truncate_text(route_kind, 80),
                    truncate_text(normalize_whitespace(title), 240),
                    truncate_text(normalize_whitespace(details), 1500),
                    truncate_text(status, 80),
                    max(0, min(100, int(importance))),
                    truncate_text(open_state, 32),
                    truncate_text(tags, 240),
                    json.dumps(observed_payload or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
            self.db.commit()
            return int(cursor.lastrowid or 0)

    def update_autobiographical_event(self, event_id: int, *, status: str = "", details: str = "", open_state: str = "") -> None:
        assignments: List[str] = ["updated_at = strftime('%s','now')"]
        params: List[object] = []
        if status:
            assignments.append("status = ?")
            params.append(truncate_text(status, 80))
        if details:
            assignments.append("details = ?")
            params.append(truncate_text(normalize_whitespace(details), 1500))
        if open_state:
            assignments.append("open_state = ?")
            params.append(truncate_text(open_state, 32))
        if len(assignments) == 1:
            return
        params.append(event_id)
        with self.db_lock:
            self.db.execute(
                f"UPDATE autobiographical_memory SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
            self.db.commit()

    def get_autobiographical_context(self, chat_id: int, query: str = "", limit: int = 6) -> str:
        lowered = normalize_whitespace(query).lower()
        keywords = extract_keywords(lowered)
        with self.db_lock:
            rows = self.db.execute(
                """SELECT id, category, event_type, route_kind, title, details, status, importance, open_state, tags, created_at
                FROM autobiographical_memory
                WHERE chat_id IS NULL OR chat_id = ?
                ORDER BY importance DESC, id DESC
                LIMIT 40""",
                (chat_id,),
            ).fetchall()
        if not rows:
            return ""
        selected: List[sqlite3.Row] = []
        for row in rows:
            haystack = " ".join(str(row[key] or "").lower() for key in ("category", "event_type", "title", "details", "tags", "status"))
            if keywords and not any(keyword in haystack for keyword in keywords):
                continue
            if not keywords and lowered and lowered not in haystack:
                continue
            selected.append(row)
            if len(selected) >= limit:
                break
        if not selected:
            selected = rows[:limit]
        return _render_autobiographical_context(selected[:limit], truncate_text)

    def get_recent_autobiographical_rows(self, limit: int = 8) -> List[sqlite3.Row]:
        with self.db_lock:
            return self.db.execute(
                """SELECT id, category, event_type, title, status, importance, open_state, created_at
                FROM autobiographical_memory
                ORDER BY id DESC
                LIMIT ?""",
                (max(1, min(20, limit)),),
            ).fetchall()

    def record_reflection(
        self,
        *,
        chat_id: Optional[int],
        user_id: Optional[int],
        route_kind: str,
        task_summary: str,
        observed_outcome: str,
        uncertainty: str,
        lesson: str,
        recommended_updates: str,
        applied_updates: str,
        tags: str,
    ) -> int:
        with self.db_lock:
            cursor = self.db.execute(
                """INSERT INTO reflections(
                    chat_id, user_id, route_kind, task_summary, observed_outcome, uncertainty,
                    lesson, recommended_updates, applied_updates, tags
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chat_id,
                    user_id,
                    truncate_text(route_kind, 80),
                    truncate_text(normalize_whitespace(task_summary), 260),
                    truncate_text(normalize_whitespace(observed_outcome), 700),
                    truncate_text(normalize_whitespace(uncertainty), 400),
                    truncate_text(normalize_whitespace(lesson), 500),
                    truncate_text(normalize_whitespace(recommended_updates), 500),
                    truncate_text(normalize_whitespace(applied_updates), 500),
                    truncate_text(tags, 240),
                ),
            )
            self.db.commit()
            return int(cursor.lastrowid or 0)

    def get_recent_reflections(self, limit: int = 6) -> List[sqlite3.Row]:
        with self.db_lock:
            return self.db.execute(
                """SELECT route_kind, task_summary, observed_outcome, uncertainty, lesson, recommended_updates, created_at
                FROM reflections
                ORDER BY id DESC
                LIMIT ?""",
                (max(1, min(20, limit)),),
            ).fetchall()

    def get_reflection_context(self, limit: int = 4) -> str:
        rows = self.get_recent_reflections(limit=limit)
        return _render_reflection_context(rows, truncate_text)

    def mark_skill_used(self, skill_key: str, success: bool) -> None:
        with self.db_lock:
            row = self.db.execute(
                "SELECT reliability, use_count FROM skill_memory WHERE skill_key = ?",
                (skill_key,),
            ).fetchone()
            if row is None:
                return
            reliability = float(row[0] or 0.5)
            use_count = int(row[1] or 0) + 1
            reliability = min(0.99, reliability + 0.03) if success else max(0.1, reliability - 0.04)
            self.db.execute(
                """UPDATE skill_memory
                SET reliability = ?, use_count = ?, last_used_at = strftime('%s','now'), updated_at = strftime('%s','now')
                WHERE skill_key = ?""",
                (reliability, use_count, skill_key),
            )
            self.db.commit()

    def get_skill_memory_context(self, query: str, route_kind: str = "", limit: int = 4) -> str:
        lowered = normalize_whitespace(query).lower()
        keywords = extract_keywords(lowered)
        with self.db_lock:
            rows = self.db.execute(
                """SELECT skill_key, title, trigger_tags, procedure, reliability, use_count, last_used_at
                FROM skill_memory
                ORDER BY reliability DESC, use_count DESC, updated_at DESC
                LIMIT 20"""
            ).fetchall()
        matched: List[sqlite3.Row] = []
        for row in rows:
            haystack = " ".join(str(row[key] or "").lower() for key in ("skill_key", "title", "trigger_tags", "procedure"))
            if route_kind and route_kind.replace("live_", "") in haystack:
                matched.append(row)
                continue
            if keywords and any(keyword in haystack for keyword in keywords):
                matched.append(row)
                continue
        if not matched and route_kind == "codex_workspace":
            matched = [row for row in rows if "runtime" in (row["trigger_tags"] or "").lower()][:limit]
        if not matched and detect_local_chat_query(query):
            matched = [row for row in rows if "chat" in (row["trigger_tags"] or "").lower()][:limit]
        if not matched and (route_kind.startswith("live_") if route_kind else False):
            matched = [row for row in rows if "live" in (row["trigger_tags"] or "").lower()][:limit]
        if not matched:
            matched = rows[: min(limit, 2)]
        return _render_skill_memory_context(matched, truncate_text, limit)

    def upsert_world_state_entry(
        self,
        state_key: str,
        *,
        category: str,
        status: str,
        value_text: str = "",
        value_number: Optional[float] = None,
        source: str = "",
        confidence: float = 0.0,
        ttl_seconds: int = 0,
        verification_method: str = "",
        stale_flag: bool = False,
    ) -> None:
        with self.db_lock:
            self.db.execute(
                """INSERT INTO world_state_registry(
                    state_key, category, status, value_text, value_number, source,
                    confidence, ttl_seconds, verification_method, stale_flag, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(state_key) DO UPDATE SET
                    category = excluded.category,
                    status = excluded.status,
                    value_text = excluded.value_text,
                    value_number = excluded.value_number,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    ttl_seconds = excluded.ttl_seconds,
                    verification_method = excluded.verification_method,
                    stale_flag = excluded.stale_flag,
                    updated_at = excluded.updated_at""",
                (
                    truncate_text(state_key, 120),
                    truncate_text(category, 80),
                    truncate_text(status, 80),
                    truncate_text(normalize_whitespace(value_text), 800),
                    value_number,
                    truncate_text(source, 120),
                    max(0.0, min(1.0, float(confidence))),
                    max(0, int(ttl_seconds)),
                    truncate_text(verification_method, 160),
                    1 if stale_flag else 0,
                ),
            )
            self.db.commit()

    def add_world_state_snapshot(self, source: str, summary: str, payload: dict) -> None:
        with self.db_lock:
            self.db.execute(
                "INSERT INTO world_state_snapshots(source, summary, payload_json) VALUES(?, ?, ?)",
                (
                    truncate_text(source, 120),
                    truncate_text(normalize_whitespace(summary), 1200),
                    truncate_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), 4000),
                ),
            )
            self.db.commit()

    def get_world_state_context(self, category: str = "", limit: int = 10) -> str:
        with self.db_lock:
            if category:
                rows = self.db.execute(
                    """SELECT state_key, category, status, value_text, value_number, source, updated_at
                    FROM world_state_registry
                    WHERE category = ?
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                    (category, max(1, min(20, limit))),
                ).fetchall()
            else:
                rows = self.db.execute(
                    """SELECT state_key, category, status, value_text, value_number, source, updated_at
                    FROM world_state_registry
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                    (max(1, min(20, limit)),),
                ).fetchall()
        if not rows:
            return ""
        return _render_world_state_context(rows, truncate_text)

    def get_recent_world_state_snapshots(self, limit: int = 5) -> List[sqlite3.Row]:
        with self.db_lock:
            return self.db.execute(
                "SELECT source, summary, created_at FROM world_state_snapshots ORDER BY id DESC LIMIT ?",
                (max(1, min(20, limit)),),
            ).fetchall()

    def set_drive_score(self, drive_name: str, score: float, reason: str) -> None:
        with self.db_lock:
            self.db.execute(
                """INSERT INTO drive_scores(drive_name, score, reason, updated_at)
                VALUES(?, ?, ?, strftime('%s','now'))
                ON CONFLICT(drive_name) DO UPDATE SET
                    score = excluded.score,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at""",
                (drive_name, max(0.0, min(100.0, float(score))), truncate_text(normalize_whitespace(reason), 400)),
            )
            self.db.commit()

    def get_drive_scores(self) -> List[sqlite3.Row]:
        with self.db_lock:
            return self.db.execute(
                "SELECT drive_name, score, reason, updated_at FROM drive_scores ORDER BY score DESC, drive_name ASC"
            ).fetchall()

    def get_drive_context(self) -> str:
        rows = self.get_drive_scores()
        return _render_drive_context(rows, truncate_text)

    def get_summary_memory_context(self, chat_id: int, limit: int = 3) -> str:
        with self.db_lock:
            rows = self.db.execute(
                """SELECT scope, summary, created_at
                FROM summary_snapshots
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (chat_id, max(1, min(6, limit))),
            ).fetchall()
        return _render_summary_memory_context(rows, truncate_text)

    def add_summary_snapshot(self, chat_id: int, scope: str, summary: str) -> None:
        cleaned = truncate_text(normalize_whitespace(summary), 1800)
        if not cleaned:
            return
        with self.db_lock:
            self.db.execute(
                "INSERT INTO summary_snapshots(chat_id, scope, summary) VALUES(?, ?, ?)",
                (chat_id, scope, cleaned),
            )
            self.db.commit()

    def set_user_memory_ai_summary(self, chat_id: int, user_id: int, ai_summary: str) -> None:
        cleaned = truncate_text(normalize_whitespace(ai_summary), 900)
        if not cleaned:
            return
        with self.db_lock:
            self.db.execute(
                "UPDATE user_memory_profiles SET ai_summary = ?, updated_at = strftime('%s','now') WHERE chat_id = ? AND user_id = ?",
                (cleaned, chat_id, user_id),
            )
            self.db.commit()

    def get_recent_chat_rows(self, chat_id: int, limit: int = 40) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_recent_user_rows(self, chat_id: int, user_id: int, limit: int = 20) -> List[Tuple[int, Optional[int], str, str, str, str, str]]:
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'user' AND user_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, user_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_recent_global_user_rows(self, user_id: int, limit: int = 40) -> List[Tuple[int, Optional[int], str, str, str, str, str]]:
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE role = 'user' AND user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_chats_due_for_memory_refresh(self, limit: int = 3, min_new_events: int = 12, min_gap_seconds: int = DEFAULT_MEMORY_REFRESH_INTERVAL_SECONDS) -> List[Tuple[int, int, int]]:
        with self.db_lock:
            chat_rows = self.db.execute(
                """SELECT chat_id, MAX(id) AS max_id
                FROM chat_events
                GROUP BY chat_id
                ORDER BY max_id DESC
                LIMIT 40"""
            ).fetchall()
            now_ts = int(time.time())
            due: List[Tuple[int, int, int]] = []
            for chat_id, max_id in chat_rows:
                if int(chat_id) > 0 and int(chat_id) != OWNER_USER_ID:
                    continue
                marker_row = self.db.execute(
                    "SELECT last_event_id, last_run_at FROM memory_refresh_state WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
                last_event_id = int(marker_row[0]) if marker_row else 0
                last_run_at = int(marker_row[1]) if marker_row else 0
                if last_run_at and now_ts - last_run_at < min_gap_seconds:
                    continue
                count_row = self.db.execute(
                    "SELECT COUNT(*) FROM chat_events WHERE chat_id = ? AND id > ? AND role = 'user'",
                    (chat_id, last_event_id),
                ).fetchone()
                new_events = int(count_row[0] or 0)
                if new_events < min_new_events:
                    continue
                due.append((int(chat_id), int(max_id or 0), new_events))
                if len(due) >= limit:
                    break
        return due

    def mark_memory_refresh(
        self,
        chat_id: int,
        last_event_id: int,
        *,
        summary_refreshed: bool = False,
        users_refreshed: bool = False,
    ) -> None:
        with self.db_lock:
            existing = self.db.execute(
                "SELECT last_summary_refresh_at, last_user_refresh_at FROM memory_refresh_state WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            last_summary_refresh_at = int(existing[0] or 0) if existing else 0
            last_user_refresh_at = int(existing[1] or 0) if existing else 0
            now_expr = "strftime('%s','now')"
            self.db.execute(
                f"""INSERT INTO memory_refresh_state(chat_id, last_event_id, last_run_at, last_user_refresh_at, last_summary_refresh_at)
                VALUES(?, ?, {now_expr}, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    last_event_id = excluded.last_event_id,
                    last_run_at = {now_expr},
                    last_user_refresh_at = excluded.last_user_refresh_at,
                    last_summary_refresh_at = excluded.last_summary_refresh_at""",
                (
                    chat_id,
                    int(last_event_id),
                    int(time.time()) if users_refreshed else last_user_refresh_at,
                    int(time.time()) if summary_refreshed else last_summary_refresh_at,
                ),
            )
            self.db.commit()

    def get_chat_memory_context(self, chat_id: int, query: str = "") -> str:
        summary = self.get_summary(chat_id)
        facts = self.get_facts(chat_id, query=query, limit=6)
        with self.db_lock:
            rows = self.db.execute(
                """SELECT user_id, username, first_name, last_name, COUNT(*) as cnt
                FROM chat_events
                WHERE chat_id = ? AND role = 'user'
                GROUP BY user_id, username, first_name, last_name
                ORDER BY cnt DESC
                LIMIT 5""",
                (chat_id,),
            ).fetchall()
        dynamics = self.get_chat_dynamics_context(chat_id, query=query)
        profile = self.get_chat_profile_context(chat_id)
        return _render_chat_memory_context(
            summary=summary,
            profile=profile,
            rows=rows,
            facts=facts,
            dynamics=dynamics,
            build_actor_name_func=build_actor_name,
            truncate_text_func=truncate_text,
        )

    def get_chat_dynamics_context(self, chat_id: int, query: str = "", limit: int = 60) -> str:
        if not detect_local_chat_query(query):
            return ""
        with self.db_lock:
            rows = self.db.execute(
                """SELECT user_id, username, first_name, last_name, reply_to_user_id, message_type, text, created_at
                FROM chat_events
                WHERE chat_id = ? AND role = 'user'
                ORDER BY id DESC
                LIMIT ?""",
                (chat_id, limit),
            ).fetchall()
        if not rows:
            return ""
        recent_rows = list(reversed(rows))
        actor_counts: Dict[str, int] = {}
        reply_pairs: Dict[Tuple[str, str], int] = {}
        short_markers = 0
        laugh_markers = 0
        rough_markers = 0
        duplicate_markers = 0
        current_streak = 0
        previous_label = ""
        topic_markers: Dict[str, int] = {}
        label_by_user: Dict[int, str] = {}
        last_text_by_user: Dict[str, str] = {}
        for user_id, username, first_name, last_name, reply_to_user_id, message_type, text, created_at in recent_rows:
            label = build_actor_name(user_id, username or "", first_name or "", last_name or "", "user")
            actor_counts[label] = actor_counts.get(label, 0) + 1
            if user_id is not None:
                label_by_user[int(user_id)] = label
            if previous_label == label:
                current_streak += 1
            else:
                previous_label = label
                current_streak = 1
            cleaned = (text or "").lower()
            if len((text or "").strip()) <= 40:
                short_markers += 1
            if any(token in cleaned for token in ("ахах", "хаха", "))))", "😂", "😁", "😄")):
                laugh_markers += 1
            if any(token in cleaned for token in ("нах", "охуе", "говно", "заеб", "пизд")):
                rough_markers += 1
            if len(cleaned) >= 8 and last_text_by_user.get(label, "") == cleaned:
                duplicate_markers += 1
            last_text_by_user[label] = cleaned
            for marker in ("бот", "jarvis", "осознан", "контекст", "стиль", "тест", "чат", "памят", "серьез", "цикл"):
                if marker in cleaned:
                    topic_markers[marker] = topic_markers.get(marker, 0) + 1
            if reply_to_user_id is not None and user_id is not None:
                source = label
                target = label_by_user.get(int(reply_to_user_id), f"user_id={int(reply_to_user_id)}")
                pair = (source, target)
                reply_pairs[pair] = reply_pairs.get(pair, 0) + 1
        lines = ["Chat dynamics:"]
        if actor_counts:
            ranked_actors = sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))
            top_actors = ", ".join(
                f"{name}={count}" for name, count in ranked_actors[:5]
            )
            lines.append(f"- active_now: {truncate_text(top_actors, 320)}")
            if ranked_actors:
                lines.append(f"- tone_setters: {truncate_text(', '.join(name for name, _count in ranked_actors[:3]), 220)}")
        if reply_pairs:
            top_pairs = ", ".join(
                f"{src} -> {dst} x{count}" for (src, dst), count in sorted(reply_pairs.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:4]
            )
            lines.append(f"- reply_links: {truncate_text(top_pairs, 320)}")
        tone_bits: List[str] = []
        if short_markers >= max(6, len(recent_rows) // 3):
            tone_bits.append("короткие быстрые реплики")
        if laugh_markers >= 2:
            tone_bits.append("ирония/смех")
        if rough_markers >= 1:
            tone_bits.append("грубоватый дружеский тон")
        if duplicate_markers >= 2:
            tone_bits.append("повторы и зацикливание")
        if current_streak >= 3:
            tone_bits.append("серии сообщений подряд")
        if tone_bits:
            lines.append(f"- tone: {', '.join(tone_bits)}")
        if topic_markers:
            topics = ", ".join(
                f"{name}={count}" for name, count in sorted(topic_markers.items(), key=lambda item: (-item[1], item[0]))[:6]
            )
            lines.append(f"- recurring_topics: {truncate_text(topics, 320)}")
        if actor_counts:
            message_total = sum(actor_counts.values())
            if message_total > 0:
                dominant_name, dominant_count = max(actor_counts.items(), key=lambda item: (item[1], item[0]))
                dominance_share = dominant_count / message_total
                if dominance_share >= 0.34:
                    lines.append(
                        f"- dominance_signal: {truncate_text(dominant_name, 120)} держит заметную долю окна ({int(dominance_share * 100)}%)"
                    )
        recent_snippets = [
            truncate_text((row[6] or "").strip(), 120)
            for row in recent_rows[-6:]
            if (row[6] or "").strip()
        ]
        if recent_snippets:
            lines.append("- latest_turns:")
            lines.extend(f"  • {snippet}" for snippet in recent_snippets[:4])
        return "\n".join(lines)

    def get_event_context(self, chat_id: int, user_text: str, limit: int = 24) -> str:
        return _get_event_context_service(self, chat_id, user_text, limit=limit)

    def get_database_context(self, chat_id: int, query: str, limit: int = 8) -> str:
        return _get_database_context_service(
            self,
            chat_id,
            query,
            limit=limit,
            build_actor_name_func=build_actor_name,
            truncate_text_func=truncate_text,
        )

    def search_events(self, chat_id: int, query: str, limit: int = 10, prefer_fts: bool = True) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
        query_text = normalize_whitespace(query)
        keywords = extract_keywords(query_text)
        needle = query_text.lower()
        broad_local_query = detect_local_chat_query(query_text)
        mention_match = re.search(r"@([a-zA-Z0-9_]{3,})", query_text)
        mentioned_username = mention_match.group(1).lower() if mention_match else ""
        if prefer_fts and query_text:
            fts_query = build_fts_query(query_text)
            if fts_query:
                with self.db_lock:
                    rows = self.db.execute(
                        "SELECT e.created_at, e.user_id, e.username, e.first_name, e.last_name, e.role, e.message_type, e.text FROM chat_events_fts f JOIN chat_events e ON e.id = f.rowid WHERE e.chat_id = ? AND f.text MATCH ? ORDER BY e.id DESC LIMIT ?",
                        (chat_id, fts_query, limit),
                    ).fetchall()
                if rows:
                    return list(reversed(rows))
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, max(limit * 12, 180)),
            ).fetchall()
        if broad_local_query and not keywords and not mentioned_username:
            return list(reversed(rows[:limit]))
        matched = []
        for row in rows:
            content = normalize_whitespace(
                " ".join(
                    (
                        row[7] or "",
                        row[2] or "",
                        row[3] or "",
                        row[4] or "",
                        row[6] or "",
                    )
                )
            ).lower()
            if mentioned_username and mentioned_username not in (row[2] or "").lower():
                continue
            if keywords:
                if not any(keyword in content for keyword in keywords):
                    continue
            elif needle and needle not in content:
                continue
            matched.append(row)
            if len(matched) >= limit:
                break
        return list(reversed(matched))

    def get_summary_recall_context(self, chat_id: int, query: str, limit: int = 4) -> str:
        query_text = normalize_whitespace(query)
        keywords = extract_keywords(query_text)
        with self.db_lock:
            rows = self.db.execute(
                """SELECT scope, summary, created_at
                FROM summary_snapshots
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT 40""",
                (chat_id,),
            ).fetchall()
        if not rows:
            return ""
        selected: List[sqlite3.Row] = []
        for row in rows:
            summary_text = normalize_whitespace(row["summary"] or "")
            lowered = summary_text.lower()
            if keywords:
                if not any(keyword in lowered for keyword in keywords):
                    continue
            elif query_text and not detect_local_chat_query(query_text):
                continue
            selected.append(row)
            if len(selected) >= max(1, limit):
                break
        if not selected and detect_local_chat_query(query_text):
            selected = rows[: max(1, min(2, limit))]
        if not selected:
            return ""
        lines = ["Archive memory:"]
        for row in reversed(selected[:limit]):
            stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
            lines.append(f"- [{stamp}] {row['scope']}: {truncate_text(row['summary'] or '', 260)}")
        return "\n".join(lines)


    def get_user_timeline(self, chat_id: int, target_user_id: Optional[int] = None, target_username: str = "", limit: int = 12) -> Tuple[str, List[Tuple[int, Optional[int], str, str, str, str, str]]]:
        username_filter = target_username.lstrip("@").lower()
        with self.db_lock:
            if target_user_id is not None:
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'user' AND user_id = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, target_user_id, limit),
                ).fetchall()
            elif username_filter:
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'user' AND lower(username) = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, username_filter, limit),
                ).fetchall()
            else:
                rows = []
        if not rows:
            return "", []
        latest = rows[0]
        label = build_actor_name(latest[1], latest[2] or "", latest[3] or "", latest[4] or "", "user")
        return label, list(reversed(rows))

    def get_daily_summary_context(self, chat_id: int, day: str = "") -> Tuple[str, List[Tuple[int, Optional[int], str, str, str, str, str, str]]]:
        target_day = day.strip() or datetime.now().strftime("%Y-%m-%d")
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT 400",
                (chat_id,),
            ).fetchall()
        selected = []
        for row in rows:
            stamp = datetime.fromtimestamp(row[0]).strftime("%Y-%m-%d") if row[0] else ""
            if stamp != target_day:
                continue
            selected.append(row)
        return target_day, list(reversed(selected[-80:]))

    def get_thread_context(self, chat_id: int, root_message_id: int, limit: int = 12) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
        with self.db_lock:
            rows = self.db.execute(
                """
                SELECT created_at, user_id, username, first_name, last_name, role, message_type, text
                FROM chat_events
                WHERE chat_id = ?
                  AND (message_id = ? OR reply_to_message_id = ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, root_message_id, root_message_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def export_events(self, chat_id: int, scope: str = "chat", limit: int = 80) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
        scope_clean = (scope or "chat").strip()
        with self.db_lock:
            if scope_clean == "today":
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT 400",
                    (chat_id,),
                ).fetchall()
                today = datetime.now().strftime("%Y-%m-%d")
                rows = [row for row in rows if (datetime.fromtimestamp(row[0]).strftime("%Y-%m-%d") if row[0] else "") == today]
                return list(reversed(rows[-limit:]))
            if scope_clean.startswith("@"):
                username_filter = scope_clean.lstrip("@").lower()
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? AND lower(username) = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, username_filter, limit),
                ).fetchall()
                return list(reversed(rows))
            try:
                user_id = int(scope_clean)
            except ValueError:
                user_id = None
            if user_id is not None:
                rows = self.db.execute(
                    "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, user_id, limit),
                ).fetchall()
                return list(reversed(rows))
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_status_snapshot(self, chat_id: int) -> Dict[str, int]:
        with self.db_lock:
            events_count = self.db.execute("SELECT COUNT(*) FROM chat_events WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            facts_count = self.db.execute("SELECT COUNT(*) FROM memory_facts WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            history_count = self.db.execute("SELECT COUNT(*) FROM chat_history WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            total_events = self.db.execute("SELECT COUNT(*) FROM chat_events").fetchone()[0]
            total_route_decisions = self.db.execute("SELECT COUNT(*) FROM request_diagnostics").fetchone()[0]
            user_memory_profiles = self.db.execute("SELECT COUNT(*) FROM user_memory_profiles WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            summary_snapshots = self.db.execute("SELECT COUNT(*) FROM summary_snapshots WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            relation_memory_rows = self.db.execute("SELECT COUNT(*) FROM relation_memory WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            autobiographical_rows = self.db.execute("SELECT COUNT(*) FROM autobiographical_memory").fetchone()[0]
            reflections_rows = self.db.execute("SELECT COUNT(*) FROM reflections").fetchone()[0]
            world_state_rows = self.db.execute("SELECT COUNT(*) FROM world_state_registry").fetchone()[0]
        return {
            "events_count": events_count,
            "facts_count": facts_count,
            "history_count": history_count,
            "total_events": total_events,
            "total_route_decisions": total_route_decisions,
            "user_memory_profiles": user_memory_profiles,
            "summary_snapshots": summary_snapshots,
            "relation_memory_rows": relation_memory_rows,
            "autobiographical_rows": autobiographical_rows,
            "reflections_rows": reflections_rows,
            "world_state_rows": world_state_rows,
        }

    def record_request_diagnostic(
        self,
        chat_id: int,
        user_id: Optional[int],
        chat_type: str,
        persona: str,
        intent: str,
        route_kind: str,
        source_label: str,
        request_kind: str,
        used_live: bool,
        used_web: bool,
        used_events: bool,
        used_database: bool,
        used_reply: bool,
        used_workspace: bool,
        guardrails: str,
        outcome: str,
        response_mode: str,
        sources: str,
        tools_used: str,
        memory_used: str,
        confidence: float,
        freshness: str,
        notes: str,
        latency_ms: int,
        query_text: str,
        request_trace_id: str = "",
        task_id: str = "",
        tools_attempted: str = "",
        contract_satisfied: int = 0,
    ) -> None:
        _record_request_diagnostic_service(
            self,
            chat_id,
            user_id,
            chat_type,
            persona,
            intent,
            route_kind,
            source_label,
            request_kind,
            used_live,
            used_web,
            used_events,
            used_database,
            used_reply,
            used_workspace,
            guardrails,
            outcome,
            response_mode,
            sources,
            tools_used,
            memory_used,
            confidence,
            freshness,
            notes,
            latency_ms,
            query_text,
            request_trace_id=request_trace_id,
            task_id=task_id,
            tools_attempted=tools_attempted,
            contract_satisfied=contract_satisfied,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_recent_request_diagnostics(self, limit: int = 8, chat_id: Optional[int] = None) -> List[sqlite3.Row]:
        return _get_recent_request_diagnostics_service(self, limit, chat_id)

    def record_repair_journal(
        self,
        *,
        signal_code: str,
        playbook_id: str,
        status: str,
        summary: str,
        evidence: str = "",
        verification_result: str = "",
        notes: str = "",
    ) -> None:
        _record_repair_journal_service(
            self,
            signal_code=signal_code,
            playbook_id=playbook_id,
            status=status,
            summary=summary,
            evidence=evidence,
            verification_result=verification_result,
            notes=notes,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_recent_repair_journal(self, limit: int = 8) -> List[sqlite3.Row]:
        return _get_recent_repair_journal_service(self, limit)

    def has_recent_self_heal_incident(self, problem_type: str, signal_code: str, window_seconds: int = 900) -> bool:
        return _has_recent_self_heal_incident_service(self, problem_type, signal_code, window_seconds)

    def record_self_heal_incident(
        self,
        *,
        problem_type: str,
        signal_code: str,
        state: str,
        severity: str,
        summary: str,
        evidence: str,
        risk_level: str,
        autonomy_level: str,
        source: str,
        confidence: float,
        suggested_playbook: str = "",
    ) -> int:
        return _record_self_heal_incident_service(
            self,
            problem_type=problem_type,
            signal_code=signal_code,
            state_value=state,
            severity=severity,
            summary=summary,
            evidence=evidence,
            risk_level=risk_level,
            autonomy_level=autonomy_level,
            source=source,
            confidence=confidence,
            suggested_playbook=suggested_playbook,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def update_self_heal_incident_state(
        self,
        incident_id: int,
        *,
        new_state: str,
        note: str = "",
        verification_status: str = "",
        lesson_text: str = "",
    ) -> None:
        _update_self_heal_incident_state_service(
            self,
            incident_id,
            new_state=new_state,
            note=note,
            verification_status=verification_status,
            lesson_text=lesson_text,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def record_self_heal_attempt(
        self,
        *,
        incident_id: int,
        playbook_id: str,
        state: str,
        status: str,
        execution_summary: str,
        executed_steps: Sequence[str] = (),
        failed_step: str = "",
        artifacts_changed: Sequence[str] = (),
        verification_required: bool = True,
        notes: str = "",
        stdout_log: Sequence[str] = (),
        stderr_log: Sequence[str] = (),
    ) -> int:
        return _record_self_heal_attempt_service(
            self,
            incident_id=incident_id,
            playbook_id=playbook_id,
            state_value=state,
            status=status,
            execution_summary=normalize_whitespace(execution_summary),
            executed_steps=executed_steps,
            failed_step=failed_step,
            artifacts_changed=artifacts_changed,
            verification_required=verification_required,
            notes=normalize_whitespace(notes),
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            truncate_text_func=truncate_text,
        )

    def update_self_heal_attempt(
        self,
        attempt_id: int,
        *,
        state: str = "",
        status: str = "",
        execution_summary: str = "",
        notes: str = "",
    ) -> None:
        _update_self_heal_attempt_service(
            self,
            attempt_id,
            state_value=state,
            status=status,
            execution_summary=execution_summary,
            notes=notes,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def record_self_heal_verification(
        self,
        *,
        incident_id: int,
        attempt_id: Optional[int],
        verified: bool,
        before_state: dict,
        after_state: dict,
        confidence: float,
        remaining_issues: Sequence[str] = (),
        regressions_detected: Sequence[str] = (),
        notes: str = "",
    ) -> int:
        return _record_self_heal_verification_service(
            self,
            incident_id=incident_id,
            attempt_id=attempt_id,
            verified=verified,
            before_state=before_state,
            after_state=after_state,
            confidence=confidence,
            remaining_issues=remaining_issues,
            regressions_detected=regressions_detected,
            notes=notes,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def record_self_heal_lesson(self, *, incident_id: int, lesson_key: str, lesson_text: str, confidence: float = 0.5) -> int:
        return _record_self_heal_lesson_service(
            self,
            incident_id=incident_id,
            lesson_key=lesson_key,
            lesson_text=lesson_text,
            confidence=confidence,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_recent_self_heal_incidents(self, limit: int = 8) -> List[sqlite3.Row]:
        return _get_recent_self_heal_incidents_service(self, limit)

    def get_self_heal_incident(self, incident_id: int) -> Optional[sqlite3.Row]:
        return _get_self_heal_incident_service(self, incident_id)

    def find_recent_self_heal_incident(self, problem_type: str, signal_code: str, window_seconds: int = 3600) -> Optional[sqlite3.Row]:
        return _find_recent_self_heal_incident_service(self, problem_type, signal_code, window_seconds)

    def count_self_heal_attempts(self, incident_id: int) -> int:
        return _count_self_heal_attempts_service(self, incident_id)

    def get_world_state_rows(self, category: str = "", limit: int = 10) -> List[sqlite3.Row]:
        return _get_world_state_rows_service(self, category, limit)

    def upsert_task_run(
        self,
        *,
        task_id: str,
        chat_id: int,
        user_id: Optional[int] = None,
        message_id: Optional[int] = None,
        delivery_chat_id: Optional[int] = None,
        progress_message_id: Optional[int] = None,
        request_trace_id: str = "",
        task_kind: str = "",
        route_kind: str = "",
        persona: str = "",
        request_kind: str = "",
        source: str = "",
        summary: str = "",
        status: str = "",
        approval_state: str = "",
        verification_state: str = "",
        outcome: str = "",
        evidence_text: str = "",
        error_text: str = "",
        tools_used: str = "",
        memory_used: str = "",
    ) -> None:
        _upsert_task_run_service(
            self,
            task_id=task_id,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            delivery_chat_id=delivery_chat_id,
            progress_message_id=progress_message_id,
            request_trace_id=request_trace_id,
            task_kind=task_kind,
            route_kind=route_kind,
            persona=persona,
            request_kind=request_kind,
            source=source,
            summary=summary,
            status=status,
            approval_state=approval_state,
            verification_state=verification_state,
            outcome=outcome,
            evidence_text=evidence_text,
            error_text=error_text,
            tools_used=tools_used,
            memory_used=memory_used,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def update_task_run(
        self,
        task_id: str,
        *,
        status: str = "",
        approval_state: str = "",
        verification_state: str = "",
        outcome: str = "",
        evidence_text: str = "",
        error_text: str = "",
        progress_message_id: Optional[int] = None,
        tools_used: str = "",
        memory_used: str = "",
    ) -> None:
        _update_task_run_service(
            self,
            task_id,
            status=status,
            approval_state=approval_state,
            verification_state=verification_state,
            outcome=outcome,
            evidence_text=evidence_text,
            error_text=error_text,
            progress_message_id=progress_message_id,
            tools_used=tools_used,
            memory_used=memory_used,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_task_run(self, task_id: str) -> Optional[sqlite3.Row]:
        return _get_task_run_service(self, task_id)

    def find_latest_task_id_by_request_trace(self, request_trace_id: str) -> str:
        return _find_latest_task_id_by_request_trace_service(self, request_trace_id)

    def get_task_context(self, chat_id: int, limit: int = 4) -> str:
        return _get_task_context_service(self, chat_id, limit, truncate_text_func=truncate_text)

    def record_task_event(
        self,
        *,
        task_id: str,
        chat_id: int,
        request_trace_id: str = "",
        phase: str,
        status: str,
        detail: str = "",
        evidence_text: str = "",
    ) -> None:
        _record_task_event_service(
            self,
            task_id=task_id,
            chat_id=chat_id,
            request_trace_id=request_trace_id,
            phase=phase,
            status=status,
            detail=detail,
            evidence_text=evidence_text,
            truncate_text_func=truncate_text,
            normalize_whitespace_func=normalize_whitespace,
        )

    def get_meta(self, key: str, default: str = "") -> str:
        with self.db_lock:
            row = self.db.execute("SELECT value FROM bot_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row and row[0] is not None else default

    def set_meta(self, key: str, value: str) -> None:
        with self.db_lock:
            self.db.execute(
                "INSERT INTO bot_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.db.commit()

    def set_ui_session(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        active_panel: str,
        pending_action: str = "",
        pending_payload: str = "",
    ) -> None:
        with self.db_lock:
            self.db.execute(
                """INSERT INTO ui_sessions
                (user_id, chat_id, message_id, active_panel, pending_action, pending_payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    message_id = excluded.message_id,
                    active_panel = excluded.active_panel,
                    pending_action = excluded.pending_action,
                    pending_payload = excluded.pending_payload,
                    updated_at = excluded.updated_at""",
                (user_id, chat_id, message_id, active_panel, pending_action, pending_payload),
            )
            self.db.commit()

    def get_ui_session(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.db_lock:
            return self.db.execute(
                "SELECT user_id, chat_id, message_id, active_panel, pending_action, pending_payload FROM ui_sessions WHERE user_id = ?",
                (user_id,),
            ).fetchone()

    def clear_ui_pending(self, user_id: int) -> None:
        with self.db_lock:
            self.db.execute(
                "UPDATE ui_sessions SET pending_action = '', pending_payload = '', updated_at = strftime('%s','now') WHERE user_id = ?",
                (user_id,),
            )
            self.db.commit()

    def resolve_chat_user(self, chat_id: int, token: str) -> Tuple[Optional[int], str]:
        cleaned = (token or "").strip()
        if not cleaned:
            return None, ""
        with self.db_lock:
            if cleaned.lstrip("-").isdigit():
                row = self.db.execute(
                    "SELECT user_id, username, first_name, last_name FROM chat_events WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                    (chat_id, int(cleaned)),
                ).fetchone()
                if row:
                    return int(row[0]), build_actor_name(row[0], row[1] or "", row[2] or "", row[3] or "", "user")
                return int(cleaned), f"user_id={cleaned}"
            username = cleaned.lstrip("@").lower()
            row = self.db.execute(
                "SELECT user_id, username, first_name, last_name FROM chat_events WHERE chat_id = ? AND lower(username) = ? ORDER BY id DESC LIMIT 1",
                (chat_id, username),
            ).fetchone()
        if row:
            return int(row[0]) if row[0] is not None else None, build_actor_name(row[0], row[1] or "", row[2] or "", row[3] or "", "user")
        return None, ""

    def add_moderation_action(self, chat_id: int, user_id: int, action: str, reason: str, created_by_user_id: Optional[int], expires_at: Optional[int] = None) -> None:
        _add_moderation_action_service(self, chat_id, user_id, action, reason, created_by_user_id, expires_at)

    def complete_moderation_action(self, action_id: int) -> None:
        _complete_moderation_action_service(self, action_id)

    def deactivate_active_moderation(self, chat_id: int, user_id: int, action: str) -> None:
        _deactivate_active_moderation_service(self, chat_id, user_id, action)

    def get_due_moderation_actions(self, now_ts: int, limit: int = 20) -> List[Tuple[int, int, int, str]]:
        return _get_due_moderation_actions_service(self, now_ts, limit)

    def get_latest_active_moderation(self, chat_id: int) -> Optional[Tuple[int, int, str]]:
        return _get_latest_active_moderation_service(self, chat_id)

    def get_active_moderations(self, chat_id: int, limit: int = 10) -> List[Tuple[int, int, str, str]]:
        return _get_active_moderations_service(self, chat_id, limit)

    def get_managed_group_chat_ids(self) -> List[int]:
        return _get_managed_group_chat_ids_service(self)

    def get_voice_prompt_terms(self, chat_id: int, limit: int = 24) -> List[str]:
        with self.db_lock:
            rows = self.db.execute(
                """SELECT first_name, last_name, username
                FROM chat_events
                WHERE chat_id = ? AND role = 'user'
                ORDER BY id DESC
                LIMIT 200""",
                (chat_id,),
            ).fetchall()
        terms: List[str] = []
        seen: Set[str] = set()
        base_terms = [
            "Джарвис",
            "Jarvis",
            "Enterprise",
            "Enterprise Core",
            "рейтинг",
            "ачивки",
            "достижения",
            "апелляция",
            "апелляции",
            "санкции",
            "модерация",
            "уровень",
            "престиж",
            "чат",
            "бот",
        ]
        for term in base_terms:
            normalized = term.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                terms.append(term.strip())
        for first_name, last_name, username in rows:
            candidates = [
                (first_name or "").strip(),
                (last_name or "").strip(),
                (username or "").strip().lstrip("@"),
                " ".join(part for part in [(first_name or "").strip(), (last_name or "").strip()] if part).strip(),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                cleaned = re.sub(r"\s+", " ", candidate).strip()
                if len(cleaned) < 2:
                    continue
                normalized = cleaned.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                terms.append(cleaned)
                if len(terms) >= limit:
                    return terms
        return terms

    def add_warning(self, chat_id: int, user_id: int, reason: str, created_by_user_id: Optional[int], expires_at: Optional[int] = None) -> int:
        return _add_warning_service(self, chat_id, user_id, reason, created_by_user_id, expires_at)

    def get_warning_count(self, chat_id: int, user_id: int) -> int:
        return _get_warning_count_service(self, chat_id, user_id)

    def remove_last_warning(self, chat_id: int, user_id: int) -> int:
        return _remove_last_warning_service(self, chat_id, user_id)

    def reset_warnings(self, chat_id: int, user_id: int) -> None:
        _reset_warnings_service(self, chat_id, user_id)

    def get_warn_settings(self, chat_id: int) -> Tuple[int, str, int]:
        return _get_warn_settings_service(self, chat_id)

    def set_warn_limit(self, chat_id: int, warn_limit: int) -> None:
        _set_warn_limit_service(self, chat_id, warn_limit)

    def set_warn_mode(self, chat_id: int, warn_mode: str) -> None:
        _set_warn_mode_service(self, chat_id, warn_mode)

    def set_warn_time(self, chat_id: int, warn_expire_seconds: int) -> None:
        _set_warn_time_service(self, chat_id, warn_expire_seconds)

    def get_warning_rows(self, chat_id: int, user_id: int, limit: int = 5) -> List[Tuple[int, str]]:
        return _get_warning_rows_service(self, chat_id, user_id, limit)

    def get_moderation_log_rows(self, chat_id: int, limit: int = 12) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
        with self.db_lock:
            rows = self.db.execute(
                "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? AND role = 'assistant' AND (message_type LIKE 'moderation_%' OR message_type LIKE 'warn%' OR message_type LIKE 'auto_%') ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_welcome_settings(self, chat_id: int) -> Tuple[bool, str]:
        return _get_welcome_settings_service(self, chat_id, default_template=WELCOME_DEFAULT_TEMPLATE)

    def set_welcome_enabled(self, chat_id: int, enabled: bool) -> None:
        _set_welcome_enabled_service(self, chat_id, enabled, default_template=WELCOME_DEFAULT_TEMPLATE)

    def set_welcome_template(self, chat_id: int, template: str) -> None:
        _set_welcome_template_service(self, chat_id, template)

    def reset_welcome_template(self, chat_id: int) -> None:
        _reset_welcome_template_service(self, chat_id, default_template=WELCOME_DEFAULT_TEMPLATE)

    def try_start_upgrade(self, chat_id: int) -> bool:
        return _try_start_upgrade_service(self, chat_id)

    def finish_upgrade(self, chat_id: int) -> None:
        _finish_upgrade_service(self, chat_id)

    def try_start_chat_task(self, chat_id: int) -> bool:
        return _try_start_chat_task_service(self, chat_id)

    def finish_chat_task(self, chat_id: int) -> None:
        _finish_chat_task_service(self, chat_id)


    def is_duplicate_message(self, chat_id: int, message_id: Optional[int]) -> bool:
        return _is_duplicate_message_service(self, chat_id, message_id, max_seen_messages=MAX_SEEN_MESSAGES)


class TelegramBridge:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.owner_user_id = OWNER_USER_ID
        self.owner_alias_user_ids = OWNER_ALIAS_USER_IDS
        self.state = BridgeState(config.history_limit, config.default_mode, config.db_path)
        self.legacy = LegacyJarvisAdapter(config.legacy_jarvis_db_path, config.db_path)
        self.appeals = AppealsService(config.db_path, config.legacy_jarvis_db_path)
        self.session = Session()
        self.live_gateway = LiveGateway(
            LiveGatewayDeps(
                request_json_with_retry=self.request_json_with_retry,
                request_text_with_retry=self.request_text_with_retry,
                log_func=log,
                normalize_whitespace_func=normalize_whitespace,
                truncate_text_func=truncate_text,
                shorten_for_log_func=shorten_for_log,
                normalize_location_query_func=normalize_location_query,
                build_location_query_variants_func=build_location_query_variants,
                format_signed_value_func=format_signed_value,
                weather_code_labels=WEATHER_CODE_LABELS,
            )
        )
        self.script_path = Path(__file__).resolve()
        self.log_path = self.script_path.with_name("tg_codex_bridge.log")
        self.runtime_service = RuntimeService(
            RuntimeServiceDeps(
                log_func=log,
                log_exception_func=log_exception,
                doc_runtime_drift_markers=DOC_RUNTIME_DRIFT_MARKERS,
            )
        )
        self.memory_service = MemoryService(
            MemoryServiceDeps(
                build_actor_name_func=build_actor_name,
            )
        )
        self.owner_handlers = OwnerCommandService(
            owner_user_id=OWNER_USER_ID,
            is_owner_private_chat_func=is_owner_private_chat,
            memory_user_usage_text=MEMORY_USER_USAGE_TEXT,
            reflections_usage_text=REFLECTIONS_USAGE_TEXT,
            chat_digest_usage_text=CHAT_DIGEST_USAGE_TEXT,
        )
        self.context_pipeline = ContextPipeline()
        self.telegram_handlers = TelegramMessageHandlers(
            owner_user_id=OWNER_USER_ID,
            safe_mode_reply=SAFE_MODE_REPLY,
        )
        self.command_dispatcher = CommandDispatcher(
            owner_username=OWNER_USERNAME,
            public_help_text=PUBLIC_HELP_TEXT,
            mode_prompts=MODE_PROMPTS,
        )
        self.control_panel_renderer = ControlPanelRenderer(
            owner_user_id=OWNER_USER_ID,
            owner_username=OWNER_USERNAME,
            public_home_text=PUBLIC_HOME_TEXT,
            commands_list_text=COMMANDS_LIST_TEXT,
            control_panel_sections=set(CONTROL_PANEL_SECTIONS),
            has_chat_access_func=has_chat_access,
            format_duration_seconds_func=format_duration_seconds,
            truncate_text_func=truncate_text,
            render_git_status_summary_func=render_git_status_summary,
            render_git_last_commits_func=render_git_last_commits,
            render_admin_command_catalog_func=render_admin_command_catalog,
        )
        self.ui_handlers = UIHandlers(
            owner_user_id=OWNER_USER_ID,
            access_denied_text=ACCESS_DENIED_TEXT,
            ui_pending_appeal=UI_PENDING_APPEAL,
            ui_pending_approve_comment=UI_PENDING_APPROVE_COMMENT,
            ui_pending_reject_comment=UI_PENDING_REJECT_COMMENT,
            ui_pending_close_comment=UI_PENDING_CLOSE_COMMENT,
            admin_help_sections=set(ADMIN_HELP_PANEL_SECTIONS),
            public_help_sections=set(PUBLIC_HELP_PANEL_SECTIONS),
            control_panel_sections=set(CONTROL_PANEL_SECTIONS),
        )
        self.bot_username = config.bot_username
        self.bot_user_id: Optional[int] = None
        self.backup_lock = Lock()
        self.backup_in_progress = False
        self.next_backup_check_ts = 0.0
        self.next_report_check_ts = 0.0
        self.next_owner_alert_check_ts = 0.0
        self.next_moderation_check_ts = 0.0
        self.next_memory_refresh_check_ts = 0.0
        self.next_auto_self_heal_check_ts = 0.0
        self.memory_refresh_lock = Lock()
        self.memory_refresh_in_progress = False
        self.heartbeat_path = Path(config.heartbeat_path)
        self.outgoing_dedupe_lock = Lock()
        self.recent_outgoing_messages: Dict[int, Tuple[str, float]] = {}
        self.status_answer_delivery_lock = Lock()
        self.status_answer_delivered: Dict[int, float] = {}
        self.console_jobs_lock = Lock()
        self.console_jobs: Dict[str, Dict[str, object]] = {}
        self.enterprise_server_bootstrap_lock = Lock()
        self.codex_app_server_started = False
        self.codex_app_server_lock = Lock()
        self.codex_app_server_process: Optional[subprocess.Popen[str]] = None
        self.group_reply_policy = GroupReplyPolicy(
            state=self.state,
            config=self.config,
            normalize_whitespace_func=normalize_whitespace,
            is_dangerous_request_func=is_dangerous_request,
            compute_score_func=compute_group_spontaneous_reply_score,
            get_chat_event_count_func=self.get_chat_event_count,
            log_func=log,
        )
        self.group_conversation_state = GroupConversationState(
            state=self.state,
            normalize_whitespace_func=normalize_whitespace,
            is_dangerous_request_func=is_dangerous_request,
            is_explicit_help_request_func=is_explicit_help_request,
            bot_user_id_getter=lambda: self.bot_user_id,
            owner_user_id=OWNER_USER_ID,
        )
        self.moderation_orchestrator = ModerationOrchestrator(
            anti_abuse=AntiAbuseAdapter(self.legacy.anti_abuse),
            sanctions=SanctionsAdapter(self.legacy.sanctions),
            warnings=WarningAdapter(self.state.add_warning, self.state.get_warning_count),
            appeals=AppealsAdapter(self.appeals),
            modlog=ModlogAdapter(config.db_path),
            text_policy=ModerationTextPolicy(),
            policy=ModerationPolicy(),
            contains_profanity_func=contains_profanity,
        )
        self.moderation_execution_service = ModerationExecutionService(
            ModerationExecutionServiceDeps(
                owner_user_id=OWNER_USER_ID,
                normalize_whitespace_func=normalize_whitespace,
                format_duration_seconds_func=format_duration_seconds,
                build_actor_name_func=build_actor_name,
                log_func=log,
            )
        )
        self.text_route_service = TextRouteService(
            TextRouteServiceDeps(
                build_prompt_func=build_prompt,
                log_func=log,
                default_chat_route_timeout=DEFAULT_CHAT_ROUTE_TIMEOUT,
            )
        )
        self.js_enterprise = JSEnterpriseService(
            JSEnterpriseServiceDeps(
                build_codex_command_func=self.build_codex_command,
                build_subprocess_env_func=build_subprocess_env,
                heartbeat_guard_factory=lambda: HeartbeatGuard(self),
                normalize_whitespace_func=normalize_whitespace,
                postprocess_answer_func=postprocess_answer,
                build_codex_failure_answer_func=build_codex_failure_answer,
                extract_usable_codex_stdout_func=extract_usable_codex_stdout,
                shorten_for_log_func=shorten_for_log,
                log_func=log,
                send_chat_action_func=self.send_chat_action,
                send_status_message_func=self.send_status_message,
                edit_status_message_func=self.edit_status_message,
                update_progress_status_func=self._update_progress_status,
                finish_progress_status_func=self._finish_progress_status,
                codex_timeout=self.config.codex_timeout,
                progress_update_seconds=CODEX_PROGRESS_UPDATE_SECONDS,
                jarvis_offline_text=JARVIS_OFFLINE_TEXT,
                upgrade_timeout_text=UPGRADE_TIMEOUT_TEXT,
                enterprise_worker_path=self.script_path.with_name("enterprise_worker.py"),
                enterprise_server_base_url=self.config.enterprise_server_base_url,
                register_pending_job_func=self.register_pending_enterprise_job,
                update_pending_job_func=self.update_pending_enterprise_job_state,
                clear_pending_job_func=self.clear_pending_enterprise_job,
                send_stream_chunks_func=lambda chat_id, title, text, include_header, reply_to_message_id: self.send_enterprise_stream_chunks(
                    chat_id,
                    title,
                    text,
                    include_header=include_header,
                    reply_to_message_id=reply_to_message_id,
                ),
                format_stream_entry_func=self.format_console_stream_entry,
            )
        )
        self.ensure_enterprise_server_started()
        self.resume_pending_enterprise_jobs()

    def get_chat_event_count(self, chat_id: int) -> int:
        with self.state.db_lock:
            row = self.state.db.execute("SELECT COUNT(*) FROM chat_events WHERE chat_id = ?", (chat_id,)).fetchone()
        return int(row[0] or 0) if row else 0

    def build_actor_name(self, user_id: Optional[int], username: str, first_name: str, last_name: str, role: str) -> str:
        return build_actor_name(user_id, username, first_name, last_name, role)

    def ensure_enterprise_server_started(self) -> None:
        with self.enterprise_server_bootstrap_lock:
            for _ in range(2):
                try:
                    response = self.session.get(f"{self.config.enterprise_server_base_url}/health", timeout=2)
                    if response.ok:
                        return
                except Exception:
                    pass
            starter = self.script_path.with_name("start_enterprise_on_userland.sh")
            if starter.exists():
                try:
                    subprocess.Popen(["sh", str(starter)], cwd=str(self.script_path.parent))
                    for _ in range(10):
                        time.sleep(0.3)
                        try:
                            response = self.session.get(f"{self.config.enterprise_server_base_url}/health", timeout=2)
                            if response.ok:
                                return
                        except Exception:
                            continue
                except OSError as error:
                    log(f"failed to start enterprise server supervisor: {error}")

    def register_pending_enterprise_job(self, payload: dict) -> None:
        raw = self.state.get_meta("pending_enterprise_jobs", "[]")
        try:
            jobs = json.loads(raw)
        except ValueError:
            jobs = []
        jobs = [job for job in jobs if str(job.get("job_id") or "") != str(payload.get("job_id") or "")]
        jobs.append(payload)
        self.state.set_meta("pending_enterprise_jobs", json.dumps(jobs, ensure_ascii=False))
        job_id = str(payload.get("job_id") or "")
        if job_id:
            self.state.upsert_task_run(
                task_id=job_id,
                chat_id=int(payload.get("chat_id") or 0),
                user_id=int(payload.get("user_id") or 0) or None,
                message_id=int(payload.get("message_id") or 0) or None,
                delivery_chat_id=int(payload.get("delivery_chat_id") or 0) or None,
                progress_message_id=int(payload.get("status_message_id") or 0) or None,
                request_trace_id=str(payload.get("request_trace_id") or ""),
                task_kind=str(payload.get("task_kind") or "enterprise_job"),
                route_kind=str(payload.get("route_kind") or ""),
                persona=str(payload.get("persona") or ""),
                request_kind=str(payload.get("request_kind") or ""),
                source="enterprise_server",
                summary=str(payload.get("summary") or payload.get("initial_status") or ""),
                status="running",
                approval_state="not_required",
                verification_state="pending",
            )
            self.state.record_task_event(
                task_id=job_id,
                chat_id=int(payload.get("chat_id") or 0),
                request_trace_id=str(payload.get("request_trace_id") or ""),
                phase="job_registered",
                status="running",
                detail=str(payload.get("initial_status") or "enterprise job registered"),
                evidence_text=str(payload.get("summary") or ""),
            )

    def clear_pending_enterprise_job(self, job_id: str) -> None:
        raw = self.state.get_meta("pending_enterprise_jobs", "[]")
        try:
            jobs = json.loads(raw)
        except ValueError:
            jobs = []
        jobs = [job for job in jobs if str(job.get("job_id") or "") != str(job_id or "")]
        self.state.set_meta("pending_enterprise_jobs", json.dumps(jobs, ensure_ascii=False))

    def update_pending_enterprise_job_state(self, job_id: str, **updates: object) -> None:
        if not (job_id or "").strip():
            return
        task_row = self.state.get_task_run(job_id)
        task_chat_id = 0
        task_request_trace_id = ""
        if task_row is not None:
            try:
                task_chat_id = int(task_row["chat_id"] or 0)
            except Exception:
                task_chat_id = 0
            try:
                task_request_trace_id = str(task_row["request_trace_id"] or "")
            except Exception:
                task_request_trace_id = ""
        self.state.update_task_run(
            job_id,
            status=str(updates.get("status") or ""),
            approval_state=str(updates.get("approval_state") or ""),
            verification_state=str(updates.get("verification_state") or ""),
            outcome=str(updates.get("outcome") or ""),
            evidence_text=str(updates.get("evidence_text") or ""),
            error_text=str(updates.get("error_text") or ""),
            progress_message_id=int(updates.get("progress_message_id") or 0) or None,
            tools_used=str(updates.get("tools_used") or ""),
            memory_used=str(updates.get("memory_used") or ""),
        )
        self.state.record_task_event(
            task_id=job_id,
            chat_id=task_chat_id,
            request_trace_id=task_request_trace_id,
            phase=str(updates.get("phase") or "job_state"),
            status=str(updates.get("status") or updates.get("verification_state") or "updated"),
            detail=str(updates.get("detail") or updates.get("outcome") or ""),
            evidence_text=str(updates.get("evidence_text") or updates.get("error_text") or ""),
        )

    def clear_pending_enterprise_jobs_for_chat(self, chat_id: int) -> None:
        raw = self.state.get_meta("pending_enterprise_jobs", "[]")
        try:
            jobs = json.loads(raw)
        except ValueError:
            jobs = []
        removed_jobs = [job for job in jobs if int(job.get("chat_id") or 0) == int(chat_id or 0)]
        jobs = [job for job in jobs if int(job.get("chat_id") or 0) != int(chat_id or 0)]
        self.state.set_meta("pending_enterprise_jobs", json.dumps(jobs, ensure_ascii=False))
        for job in removed_jobs:
            job_id = str(job.get("job_id") or "")
            if job_id:
                self.state.update_task_run(
                    job_id,
                    status="cleared",
                    verification_state="unknown",
                    outcome="cleared",
                    evidence_text="pending job removed from in-memory queue for chat",
                )
                self.state.record_task_event(
                    task_id=job_id,
                    chat_id=int(chat_id or 0),
                    request_trace_id=str(job.get("request_trace_id") or ""),
                    phase="queue_cleanup",
                    status="cleared",
                    detail="pending enterprise job removed after delivery/cleanup",
                )

    def _filter_new_achievement_announcements(
        self,
        chat_id: int,
        user_id: int,
        unlocked: Sequence[Dict[str, object]],
        cooldown_seconds: int = 86400,
    ) -> List[Dict[str, object]]:
        fresh: List[Dict[str, object]] = []
        now_ts = int(time.time())
        for item in unlocked:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            meta_key = f"achievement_announce:{chat_id}:{user_id}:{code}"
            try:
                last_sent_ts = int(str(self.state.get_meta(meta_key, "0") or "0").strip() or "0")
            except ValueError:
                last_sent_ts = 0
            if last_sent_ts > 0 and now_ts - last_sent_ts < cooldown_seconds:
                continue
            self.state.set_meta(meta_key, str(now_ts))
            fresh.append(item)
        return fresh

    def resume_pending_enterprise_jobs(self) -> None:
        raw = self.state.get_meta("pending_enterprise_jobs", "[]")
        try:
            jobs = json.loads(raw)
        except ValueError:
            jobs = []
        if not jobs:
            return
        self.state.set_meta("pending_enterprise_jobs", "[]")
        for job in jobs:
            job_id = str(job.get("job_id") or "")
            chat_id = int(job.get("chat_id") or 0)
            if not job_id:
                continue
            if hasattr(self.state, "update_task_run"):
                self.state.update_task_run(
                    job_id,
                    status="cleared",
                    verification_state="unknown",
                    outcome="cleared_after_restart",
                    evidence_text="pending enterprise job cleared on bridge restart without redelivery",
                )
            if hasattr(self.state, "record_task_event"):
                self.state.record_task_event(
                    task_id=job_id,
                    chat_id=chat_id,
                    request_trace_id=str(job.get("request_trace_id") or ""),
                    phase="job_resume_skipped",
                    status="cleared",
                    detail="pending enterprise job cleared after restart",
                )
            log(f"cleared pending enterprise job after restart job={job_id} chat={chat_id}")

    def _resume_pending_enterprise_job(self, job: dict) -> None:
        job_id = str(job.get("job_id") or "")
        chat_id = int(job.get("chat_id") or 0)
        delivery_chat_id = int(job.get("delivery_chat_id") or 0) or chat_id
        progress_chat_id = int(job.get("progress_chat_id") or 0) or delivery_chat_id or chat_id
        if not job_id or not chat_id:
            return
        try:
            log(f"resume pending enterprise job={job_id} chat={chat_id}")
            if hasattr(self.state, "update_task_run"):
                self.state.update_task_run(
                    job_id,
                    status="resumed",
                    verification_state="pending",
                    evidence_text="bridge resumed waiting for pending enterprise job after restart",
                )
            if hasattr(self.state, "record_task_event"):
                self.state.record_task_event(
                    task_id=job_id,
                    chat_id=chat_id,
                    request_trace_id=str(job.get("request_trace_id") or ""),
                    phase="job_resume",
                    status="resumed",
                    detail="bridge resumed pending enterprise job after restart",
                )
            status_message_id = job.get("status_message_id")
            if status_message_id in {"", None}:
                status_message_id = None
            else:
                status_message_id = int(status_message_id)
            answer = self.js_enterprise.wait_for_job(
                job_id=job_id,
                chat_id=chat_id,
                progress_chat_id=progress_chat_id,
                initial_status=str(job.get("initial_status") or OWNER_AGENT_RUNNING_TEXT),
                status_message_id=status_message_id,
                effective_timeout=int(job.get("timeout_seconds") or 0) or None,
                progress_style=str(job.get("progress_style") or "enterprise"),
                replace_status_with_answer=bool(job.get("replace_status_with_answer")),
                target_label=str(job.get("target_label") or ""),
                delivery_chat_id=delivery_chat_id,
                postprocess=bool(job.get("postprocess", True)),
                approval_policy=str(job.get("approval_policy") or "") or None,
                sandbox_mode=str(job.get("sandbox_mode") or "") or None,
                clear_pending_on_finish=False,
            )
            self.state.append_history(chat_id, "assistant", answer)
            self.state.record_event(chat_id, None, "assistant", "answer", answer)
            delivered_via_status = self.consume_answer_delivered_via_status(chat_id)
            if not delivered_via_status:
                self.safe_send_text(delivery_chat_id, answer)
            self.clear_pending_enterprise_job(job_id)
            log(
                "resume pending enterprise delivered "
                f"job={job_id} chat={chat_id} delivery_chat={delivery_chat_id} via_status={'yes' if delivered_via_status else 'no'}"
            )
        except Exception as error:
            if hasattr(self.state, "update_task_run"):
                self.state.update_task_run(
                    job_id,
                    status="failed",
                    verification_state="failed",
                    outcome="error",
                    error_text=str(error),
                )
            self.clear_pending_enterprise_job(job_id)
            log_exception(f"resume pending enterprise failed job={job_id}", error, limit=10)

    def start_console_job(self, command: str) -> str:
        self.ensure_enterprise_server_started()
        return self.js_enterprise.start_remote_job(
            chat_id=0,
            prompt=(command or "").strip(),
            timeout_seconds=self.config.enterprise_task_timeout if self.config.enterprise_task_timeout is not None else self.config.codex_timeout,
        )

    def get_console_job_snapshot(self, job_id: str) -> Optional[Dict[str, object]]:
        self.ensure_enterprise_server_started()
        return self.js_enterprise.get_remote_job_snapshot(job_id)

    def stop_console_job(self, job_id: str) -> bool:
        if not (job_id or "").strip():
            return False
        self.ensure_enterprise_server_started()
        return self.js_enterprise.stop_remote_job(job_id)

    def build_console_status_markup(self, chat_id: int, running: bool = True) -> dict:
        if not running:
            return {"inline_keyboard": []}
        return {
            "inline_keyboard": [
                [{"text": "Остановить", "callback_data": f"console_stop:{int(chat_id)}"}],
            ]
        }

    def register_local_console_process(
        self,
        chat_id: int,
        process: object,
        *,
        command: str,
        status_message_id: Optional[int],
    ) -> None:
        with self.console_jobs_lock:
            self.console_jobs[str(chat_id)] = {
                "chat_id": int(chat_id),
                "command": command,
                "process": process,
                "status_message_id": int(status_message_id) if status_message_id is not None else None,
                "started_at": time.time(),
                "stop_requested": False,
            }

    def clear_local_console_process(self, chat_id: int) -> None:
        with self.console_jobs_lock:
            self.console_jobs.pop(str(chat_id), None)

    def request_stop_local_console_process(self, chat_id: int) -> Tuple[bool, str]:
        with self.console_jobs_lock:
            job = self.console_jobs.get(str(chat_id))
            if not job:
                return False, "Активная консольная задача не найдена."
            process = job.get("process")
            job_id = str(job.get("job_id") or "")
            if job_id:
                job["stop_requested"] = True
            elif not isinstance(process, subprocess.Popen):
                return False, "Процесс консоли недоступен."
            elif process.poll() is not None:
                return False, "Процесс уже завершился."
            job["stop_requested"] = True
        if job_id:
            stopped = self.stop_console_job(job_id)
            return (True, "Останавливаю задачу Enterprise...") if stopped else (False, "Не удалось остановить задачу Enterprise.")
        try:
            process.terminate()
            return True, "Останавливаю процесс..."
        except Exception as error:
            log(f"failed to stop console process chat={chat_id}: {error}")
            return False, "Не удалось остановить процесс."

    def get_enterprise_runtime_status(self) -> Optional[Dict[str, object]]:
        self.ensure_enterprise_server_started()
        return self.js_enterprise.get_runtime_status()

    def restart_bridge_via_enterprise_server(self) -> Optional[Dict[str, object]]:
        self.ensure_enterprise_server_started()
        return self.js_enterprise.restart_bridge_runtime()

    def truncate_text(self, text: str, limit: int = 280) -> str:
        return truncate_text(text, limit)

    def normalize_whitespace(self, text: str) -> str:
        return normalize_whitespace(text)

    def render_chat_troublemaker_summary(
        self,
        rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
        *,
        top_limit: int = 3,
    ) -> str:
        return render_chat_troublemaker_summary(rows, top_limit=top_limit)

    def build_service_actor_name(self, payload: dict) -> str:
        return _build_service_actor_name(payload, self.build_actor_name)

    def log(self, message: str) -> None:
        log(message)

    def build_enterprise_console_webapp_url(self) -> str:
        if not self.config.webapp_base_url:
            return ""
        return f"{self.config.webapp_base_url}/enterprise-console?token={self.config.webapp_secret}"

    def open_enterprise_console_webapp(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        webapp_url = self.build_enterprise_console_webapp_url()
        if not webapp_url:
            self.safe_send_text(
                chat_id,
                "Enterprise WebApp уже встроен, но для открытия из Telegram нужен публичный HTTPS URL.\n\n"
                "Задай `WEBAPP_BASE_URL`, например `https://<домен-или-tunnel>`.",
            )
            return True
        self.send_inline_message(
            chat_id,
            "Enterprise Console WebApp",
            {"inline_keyboard": [[{"text": "Открыть Enterprise Console", "web_app": {"url": webapp_url}}]]},
        )
        return True


    def build_webapp_html_old(self, screen_text: str = "Готов. Пиши запрос.", prompt_value: str = "", auto_refresh_seconds: int = 0) -> str:
        refresh_meta = f'<meta http-equiv="refresh" content="{auto_refresh_seconds}">' if auto_refresh_seconds > 0 else ""
        escaped_screen = html.escape(screen_text)
        escaped_prompt = html.escape(prompt_value)
        return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  __REFRESH_META__
  <title>Enterprise</title>
  <style>
    :root { --bg:#0d1117; --panel:#161b22; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --acc:#2f81f7; }
    * { box-sizing:border-box; }
    html, body { height:100%; }
    body {
      margin:0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      background:linear-gradient(180deg,#0d1117,#11161d);
      color:var(--text);
      min-height:100dvh;
      overflow:hidden;
    }
    .wrap {
      max-width:1280px;
      margin:0 auto;
      padding:12px;
      height:100dvh;
      display:flex;
      flex-direction:column;
      gap:10px;
    }
    .title { margin:0; font-size:26px; flex:0 0 auto; }
    .screen {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:16px;
      padding:18px;
      flex:1 1 auto;
      min-height:0;
      white-space:pre-wrap;
      overflow:auto;
      font-size:16px;
      line-height:1.55;
    }
    .composer {
      flex:0 0 auto;
      display:flex;
      flex-direction:column;
      gap:10px;
      padding-bottom:max(8px, env(safe-area-inset-bottom));
      background:linear-gradient(180deg, rgba(13,17,23,0.2), rgba(13,17,23,0.98));
    }
    .row { display:flex; gap:10px; }
    textarea {
      width:100%;
      min-height:36px;
      max-height:34dvh;
      resize:none;
      background:#0b0f14;
      border:1px solid var(--line);
      color:var(--text);
      border-radius:12px;
      padding:16px;
      font:inherit;
      font-size:16px;
      line-height:1.45;
    }
    @media (max-width: 720px) {
      .wrap { padding:10px; gap:8px; }
      .title { font-size:22px; }
      .screen { padding:14px; font-size:15px; }
      .composer { gap:8px; }
      textarea { min-height:64px; max-height:40dvh; padding:14px; }
      .row { gap:8px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h2 class="title">Enterprise</h2>
    <div id="screen" class="screen">Готов. Пиши запрос.</div>
    <div class="composer">
      <div class="row"><textarea id="cmd" placeholder="Напиши запрос для Enterprise"></textarea></div>
    </div>
  </div>
  <script>
    const token = new URLSearchParams(location.search).get("token") || "";
    const screen = document.getElementById("screen");
    const input = document.getElementById("cmd");
    let currentJob = null;
    let timer = null;
    function setScreen(text) { screen.textContent = text; screen.scrollTop = screen.scrollHeight; }
    function autoResizeInput() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, window.innerHeight * 0.34) + "px";
    }
    async function pollJob() {
      if (!currentJob) return;
      const response = await fetch(`/enterprise-console/api/jobs/${currentJob}?token=${encodeURIComponent(token)}`);
      const data = await response.json();
      const header = `Enterprise\\n\\nЗапрос:\\n${data.command}\\n\\nСтатус: ${data.done ? "готово" : "выполняется"}\\n\\n`;
      setScreen(header + (data.output || "[пустой ответ]"));
      if (data.done && timer) { clearInterval(timer); timer = null; }
    }
    async function runCommand() {
      const command = input.value.trim();
      if (!command) return;
      input.value = "";
      autoResizeInput();
      const response = await fetch(`/enterprise-console/api/exec?token=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({command})
      });
      const data = await response.json();
      currentJob = data.job_id;
      setScreen(`Enterprise\\n\\nЗапрос:\\n${command}\\n\\nСтатус: выполняется`);
      if (timer) clearInterval(timer);
      timer = setInterval(pollJob, 900);
      pollJob();
    }
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        runCommand();
      }
    });
    input.addEventListener("input", autoResizeInput);
    input.addEventListener("focus", () => {
      setTimeout(() => screen.scrollTop = screen.scrollHeight, 150);
    });
    autoResizeInput();
  </script>
</body>
</html>""".replace("__REFRESH_META__", refresh_meta)


    def build_webapp_html(self, screen_text: str = "Готов. Пиши запрос.", prompt_value: str = "", auto_refresh_seconds: int = 0) -> str:
        return build_enterprise_console_html(
            screen_text=screen_text,
            prompt_value=prompt_value,
            auto_refresh_seconds=auto_refresh_seconds,
        )

    def run_webapp_server(self) -> None:
        run_enterprise_console_server(
            bridge=self,
            secret=self.config.webapp_secret,
            bind_host=self.config.webapp_bind_host,
            port=self.config.webapp_port,
        )

    def ensure_webapp_server_started(self) -> None:
        with self.webapp_lock:
            if self.webapp_started:
                return
            Thread(target=self.run_webapp_server, daemon=True).start()
            self.webapp_started = True

    def ensure_codex_app_server_started(self) -> None:
        with self.codex_app_server_lock:
            process = self.codex_app_server_process
            if process is not None and process.poll() is None:
                return
            listen_url = self.config.codex_app_server_url
            command = [
                "codex",
                "app-server",
                "--listen",
                listen_url,
                "--session-source",
                "cli",
            ]
            self.codex_app_server_process = subprocess.Popen(
                command,
                cwd=str(self.script_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                env=build_subprocess_env(),
            )
            self.codex_app_server_started = True

    def log_exception(self, prefix: str, error: Exception, limit: int = 8) -> None:
        log_exception(prefix, error, limit=limit)

    def shorten_for_log(self, value: str, limit: int = 220) -> str:
        return shorten_for_log(value, limit)

    def normalize_incoming_text(self, raw_text: str, bot_username: str) -> str:
        return normalize_incoming_text(raw_text, bot_username)

    def format_reaction_payload(self, reactions: List[dict]) -> str:
        return format_reaction_payload(reactions)

    def format_reaction_count_payload(self, reactions: List[dict]) -> str:
        return format_reaction_count_payload(reactions)

    def extract_assistant_persona(self, text: str) -> Tuple[str, str]:
        return extract_assistant_persona(text)

    def detect_weather_location(self, text: str) -> str:
        return detect_weather_location(text)

    def detect_currency_pair(self, text: str) -> Optional[Tuple[str, str]]:
        return detect_currency_pair(text)

    def detect_crypto_asset(self, text: str) -> str:
        return detect_crypto_asset(text)

    def detect_stock_symbol(self, text: str) -> str:
        return detect_stock_symbol(text)

    def detect_news_query(self, text: str) -> str:
        return detect_news_query(text)

    def detect_current_fact_query(self, text: str) -> str:
        return detect_current_fact_query(text)

    def detect_local_chat_query(self, user_text: str) -> bool:
        return detect_local_chat_query(user_text)

    def should_include_database_context(self, user_text: str) -> bool:
        return should_include_database_context(user_text)

    def should_include_event_context(self, user_text: str) -> bool:
        return should_include_event_context(user_text)

    def is_owner_private_chat(self, user_id: Optional[int], chat_id: int) -> bool:
        return is_owner_private_chat(user_id, chat_id)

    def is_owner_identity(self, user_id: Optional[int]) -> bool:
        return is_owner_identity(user_id)

    def build_route_summary_text(self, route_info: RouteDecision) -> str:
        return build_route_summary_text(route_info)

    def build_guardrail_note(self, route_info: RouteDecision) -> str:
        return build_guardrail_note(route_info)

    def has_chat_access(self, authorized_user_ids: set[int], user_id: Optional[int]) -> bool:
        return has_chat_access(authorized_user_ids, user_id)

    def should_process_group_message(self, message: dict, text: str) -> bool:
        return should_process_group_message(
            message,
            text,
            self.bot_username,
            self.config.trigger_name,
            bot_user_id=self.bot_user_id,
            allow_owner_reply=False,
        )

    def contains_profanity(self, text: str) -> bool:
        return contains_profanity(text)

    def is_dangerous_request(self, text: str) -> bool:
        return is_dangerous_request(text)

    def can_owner_use_workspace_mode(self, user_id: Optional[int], chat_type: str, assistant_persona: str) -> bool:
        return can_owner_use_workspace_mode(user_id, chat_type, assistant_persona)

    def compute_group_spontaneous_reply_score(self, text: str) -> int:
        return compute_group_spontaneous_reply_score(text)

    def should_attempt_owner_autofix(self, raw_text: str, message: dict) -> bool:
        return should_attempt_owner_autofix(raw_text, message)

    def build_user_autofix_label(self, payload: dict) -> str:
        return build_user_autofix_label(payload)

    def parse_sd_save_command(self, text: str) -> Optional[str]:
        return parse_sd_save_command(text)

    def parse_owner_report_command(self, text: str) -> bool:
        return parse_owner_report_command(text)

    def parse_chat_watch_command(self, text: str) -> bool:
        return parse_chat_watch_command(text)

    def parse_export_command(self, text: str) -> Optional[str]:
        return parse_export_command(text)

    def parse_portrait_command(self, text: str) -> Optional[str]:
        return parse_portrait_command(text)

    def parse_welcome_command(self, text: str) -> Optional[Tuple[str, str]]:
        return parse_welcome_command(text)

    def parse_mode_command(self, text: str) -> Optional[str]:
        return parse_mode_command(text)

    def has_public_command_access(self, text: str) -> bool:
        return has_public_command_access(text)

    def has_public_callback_access(self, data: str) -> bool:
        return has_public_callback_access(data)

    def is_message_not_modified_error(self, error: Exception) -> bool:
        return is_message_not_modified_error(error)

    def is_message_edit_recoverable_error(self, error: Exception) -> bool:
        return is_message_edit_recoverable_error(error)

    def is_request_exception(self, error: Exception) -> bool:
        return isinstance(error, RequestException)

    def try_claim_group_spontaneous_reply_slot(self, chat_id: int, message_id: Optional[int]) -> bool:
        return self.group_reply_policy.try_claim_group_spontaneous_reply_slot(chat_id, message_id)

    def is_group_spontaneous_reply_candidate(self, chat_id: int, message: dict, raw_text: str) -> bool:
        return self.group_reply_policy.is_group_spontaneous_reply_candidate(chat_id, message, raw_text)

    def grant_group_followup_window(self, chat_id: int, user_id: Optional[int]) -> None:
        self.group_reply_policy.grant_group_followup_window(chat_id, user_id)

    def has_active_group_followup_window(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.group_reply_policy.has_active_group_followup_window(chat_id, user_id)

    def is_group_followup_message(self, chat_id: int, message: dict, raw_text: str) -> bool:
        return self.group_reply_policy.is_group_followup_message(chat_id, message, raw_text)

    def is_ambient_group_chatter(self, message: dict, raw_text: str) -> bool:
        return self.group_reply_policy.is_ambient_group_chatter(message, raw_text)

    def is_meaningful_group_request(self, message: dict, raw_text: str) -> bool:
        return self.group_reply_policy.is_meaningful_group_request(message, raw_text)

    def is_group_discussion_rate_limited(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.group_reply_policy.is_group_discussion_rate_limited(chat_id, user_id)

    def record_group_discussion_turn(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.group_reply_policy.record_group_discussion_turn(chat_id, user_id)

    def mark_active_group_discussion(self, chat_id: int, user_id: Optional[int], message: Optional[dict], ttl_seconds: int = 900) -> None:
        self.group_conversation_state.mark_active_discussion(chat_id, user_id, message, ttl_seconds=ttl_seconds)

    def is_group_discussion_continuation(self, chat_id: int, message: dict, raw_text: str) -> bool:
        return self.group_conversation_state.is_group_discussion_continuation(chat_id, message, raw_text)

    def get_group_participant_priority(self, chat_id: int, message: dict) -> str:
        return self.group_conversation_state.get_group_participant_priority(chat_id, message)

    def get_group_discussion_state_hint(self, chat_id: int) -> str:
        return self.group_conversation_state.render_discussion_state_hint(chat_id)

    def get_active_group_discussion(self, chat_id: int, message: Optional[dict] = None, raw_text: str = "") -> Dict[str, object]:
        return self.group_conversation_state.get_active_discussion(chat_id, message, raw_text)

    def mark_answer_delivered_via_status(self, chat_id: int) -> None:
        with self.status_answer_delivery_lock:
            self.status_answer_delivered[chat_id] = time.time()

    def consume_answer_delivered_via_status(self, chat_id: int) -> bool:
        with self.status_answer_delivery_lock:
            timestamp = self.status_answer_delivered.pop(chat_id, 0.0)
        return bool(timestamp)

    def should_consider_group_spontaneous_reply(self, chat_id: int, message: dict, raw_text: str) -> bool:
        return self.group_reply_policy.should_consider_group_spontaneous_reply(chat_id, message, raw_text)

    def beat_heartbeat(self) -> None:
        try:
            self.heartbeat_path.write_text(str(time.time()), encoding="utf-8")
        except OSError as error:
            log(f"failed to write heartbeat: {error}")

    def run(self) -> None:
        self.beat_heartbeat()
        self.load_bot_identity()
        self.refresh_world_state_registry("startup")
        self.recompute_drive_scores()
        self.finalize_pending_auto_restart()
        if self.owner_autofix_enabled():
            self.run_auto_repair_loop("startup")
        else:
            self.run_self_heal_cycle("startup", auto_execute=False)
        self.state.record_autobiographical_event(
            category="runtime",
            event_type="startup",
            title="bridge started",
            details=f"mode={self.config.default_mode}; db={self.config.db_path}",
            status="ok",
            importance=55,
            open_state="closed",
            tags="startup,runtime",
            observed_payload={"db_path": self.config.db_path, "safe_chat_only": self.config.safe_chat_only},
        )
        log("bot started")
        self.maybe_send_restart_confirmation()
        while True:
            try:
                self.beat_heartbeat()
                self.maybe_start_weekly_backup()
                self.maybe_start_scheduled_reports()
                self.maybe_start_owner_chat_alerts()
                self.maybe_start_memory_refresh()
                self.maybe_run_auto_repair_loop()
                self.process_due_moderation_actions()
                updates = self.get_updates(self.state.last_update_id)
                if not updates.get("ok"):
                    log(f"telegram getUpdates returned ok=false: {updates}")
                    time.sleep(ERROR_BACKOFF_SECONDS)
                    continue

                for item in updates.get("result", []):
                    self.beat_heartbeat()
                    self.state.set_last_update_id(item["update_id"] + 1)
                    self.handle_update(item)
            except KeyboardInterrupt:
                log("bot stopped")
                raise
            except RequestException as error:
                log(f"network error in main loop: {error}")
                self.refresh_world_state_registry("runtime_error")
                self.recompute_drive_scores()
                if self.owner_autofix_enabled():
                    self.run_auto_repair_loop("runtime_error")
                else:
                    self.run_self_heal_cycle("runtime_error", auto_execute=False)
                self.state.record_autobiographical_event(
                    category="runtime",
                    event_type="network_error",
                    title="main loop network error",
                    details=str(error),
                    status="error",
                    importance=70,
                    open_state="closed",
                    tags="runtime,network",
                )
                time.sleep(ERROR_BACKOFF_SECONDS)
            except Exception as error:
                log_exception("unexpected main loop error", error, limit=12)
                self.refresh_world_state_registry("runtime_error")
                self.recompute_drive_scores()
                if self.owner_autofix_enabled():
                    self.run_auto_repair_loop("runtime_error")
                else:
                    self.run_self_heal_cycle("runtime_error", auto_execute=False)
                self.state.record_autobiographical_event(
                    category="runtime",
                    event_type="unexpected_error",
                    title="main loop unexpected error",
                    details=str(error),
                    status="error",
                    importance=80,
                    open_state="closed",
                    tags="runtime,error",
                )
                time.sleep(ERROR_BACKOFF_SECONDS)

    def maybe_send_restart_confirmation(self) -> None:
        raw_chat_id = self.state.get_meta("pending_restart_chat_id", "")
        if not raw_chat_id:
            return
        raw_message_id = self.state.get_meta("pending_restart_message_id", "")
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            self.state.set_meta("pending_restart_chat_id", "")
            self.state.set_meta("pending_restart_message_id", "")
            return
        pending_text = self.state.get_meta("pending_restart_text", RESTARTED_TEXT) or RESTARTED_TEXT
        started_at_text = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S MSK")
        outgoing_text = f"{pending_text}\nВремя запуска: {started_at_text}"
        restart_digest = self.build_restart_runtime_digest()
        if restart_digest:
            outgoing_text = f"{outgoing_text}\n\n{restart_digest}"
        try:
            edited = False
            if raw_message_id:
                try:
                    edited = self.edit_status_message(chat_id, int(raw_message_id), outgoing_text)
                except ValueError:
                    edited = False
            if not edited:
                self.safe_send_text(chat_id, outgoing_text)
            log(f"restart confirmation sent chat={chat_id}")
        finally:
            self.state.set_meta("pending_restart_chat_id", "")
            self.state.set_meta("pending_restart_message_id", "")
            self.state.set_meta("pending_restart_text", "")

    def build_restart_runtime_digest(self) -> str:
        lines: List[str] = []
        enterprise_ok = False
        try:
            response = self.session.get(f"{self.config.enterprise_server_base_url}/health", timeout=2)
            enterprise_ok = bool(response.ok)
        except Exception:
            enterprise_ok = False
        lines.append(f"Enterprise server: {'ok' if enterprise_ok else 'unreachable'}")

        raw_jobs = self.state.get_meta("pending_enterprise_jobs", "[]")
        try:
            jobs = json.loads(raw_jobs)
        except ValueError:
            jobs = []
        if not isinstance(jobs, list):
            jobs = []
        active_jobs = [job for job in jobs if str(job.get("job_id") or "").strip()]
        lines.append(f"Pending enterprise jobs: {len(active_jobs)}")
        if active_jobs:
            preview = []
            for job in active_jobs[:3]:
                job_id = str(job.get("job_id") or "").strip() or "?"
                source_chat_id = int(job.get("chat_id") or 0)
                delivery_chat_id = int(job.get("delivery_chat_id") or 0) or source_chat_id
                preview.append(f"- {job_id}: source={source_chat_id} delivery={delivery_chat_id}")
            lines.extend(preview)
            if len(active_jobs) > 3:
                lines.append(f"- ... ещё {len(active_jobs) - 3}")
        return "\n".join(lines)

    def get_updates(self, offset: Optional[int]) -> dict:
        params = {
            "timeout": GET_UPDATES_TIMEOUT,
            "allowed_updates": json.dumps(["message", "edited_message", "callback_query", "message_reaction", "message_reaction_count"]),
        }
        if offset is not None:
            params["offset"] = offset
        response = self.session.get(
            f"{self.config.base_url}/getUpdates",
            params=params,
            timeout=GET_UPDATES_TIMEOUT + 10,
        )
        ensure_telegram_ok(response)
        return response.json()

    def telegram_api(self, method: str, *, params: Optional[dict] = None, data: Optional[dict] = None) -> dict:
        response = self.session.post(
            f"{self.config.base_url}/{method}",
            params=params,
            data=data,
            timeout=TELEGRAM_TIMEOUT,
        )
        ensure_telegram_ok(response)
        return response.json()

    def load_bot_identity(self) -> None:
        try:
            payload = self.telegram_api("getMe")
            result = payload.get("result") or {}
            self.bot_user_id = result.get("id")
            username = (result.get("username") or "").strip().lstrip("@").lower()
            if username:
                self.bot_username = username
        except RequestException as error:
            log(f"failed to load bot identity: {error}")

    def get_file_info(self, file_id: str) -> dict:
        payload = self.telegram_api("getFile", data={"file_id": file_id})
        return payload.get("result") or {}

    def get_chat_member_status(self, chat_id: int, user_id: int) -> str:
        payload = self.telegram_api("getChatMember", data={"chat_id": chat_id, "user_id": user_id})
        result = payload.get("result") or {}
        return (result.get("status") or "").lower()

    def get_chat_member_info(self, chat_id: int, user_id: int) -> dict:
        payload = self.telegram_api("getChatMember", data={"chat_id": chat_id, "user_id": user_id})
        result = payload.get("result") or {}
        return result if isinstance(result, dict) else {}

    def get_chat_administrators(self, chat_id: int) -> List[dict]:
        payload = self.telegram_api("getChatAdministrators", data={"chat_id": chat_id})
        result = payload.get("result") or []
        return result if isinstance(result, list) else []

    def get_chat_member_count(self, chat_id: int) -> int:
        payload = self.telegram_api("getChatMemberCount", data={"chat_id": chat_id})
        result = payload.get("result")
        try:
            return int(result)
        except (TypeError, ValueError):
            return 0

    def maybe_refresh_chat_participants_snapshot(self, chat_id: int, chat_type: str) -> None:
        if chat_type not in {"group", "supergroup"}:
            return
        snapshot = self.state.get_chat_runtime_snapshot(chat_id)
        now = int(time.time())
        admins_synced_at = int(snapshot["admins_synced_at"] or 0) if snapshot else 0
        member_count_synced_at = int(snapshot["member_count_synced_at"] or 0) if snapshot else 0
        if admins_synced_at and member_count_synced_at:
            if now - min(admins_synced_at, member_count_synced_at) < CHAT_PARTICIPANTS_REFRESH_SECONDS:
                return
        try:
            admin_payload = self.get_chat_administrators(chat_id)
            admin_rows: List[Tuple[int, str, str, str, int, str]] = []
            for item in admin_payload:
                user = item.get("user") or {}
                user_id = user.get("id")
                if user_id is None:
                    continue
                admin_rows.append(
                    (
                        int(user_id),
                        user.get("username") or "",
                        user.get("first_name") or "",
                        user.get("last_name") or "",
                        1 if user.get("is_bot") else 0,
                        (item.get("status") or "").lower(),
                    )
                )
            self.state.mark_admins_synced(chat_id, admin_rows)
            member_count = self.get_chat_member_count(chat_id)
            if member_count > 0:
                self.state.save_chat_member_count(chat_id, member_count)
        except RequestException as error:
            log(f"failed to refresh participants snapshot chat={chat_id}: {error}")

    def is_chat_admin(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        if is_owner_identity(user_id):
            return True
        try:
            return self.get_chat_member_status(chat_id, user_id) in {"creator", "administrator"}
        except RequestException as error:
            log(f"failed to fetch admin status chat={chat_id} user={user_id}: {error}")
            return False

    def can_moderate_target(self, chat_id: int, target_user_id: int) -> bool:
        if is_owner_identity(target_user_id):
            return False
        if self.bot_user_id is not None and target_user_id == self.bot_user_id:
            return False
        try:
            return self.get_chat_member_status(chat_id, target_user_id) not in {"creator", "administrator"}
        except RequestException:
            return True

    def ban_chat_member(self, chat_id: int, user_id: int, until_ts: Optional[int] = None) -> None:
        data = {"chat_id": chat_id, "user_id": user_id}
        if until_ts is not None:
            data["until_date"] = until_ts
        self.telegram_api("banChatMember", data=data)

    def unban_chat_member(self, chat_id: int, user_id: int) -> None:
        self.telegram_api("unbanChatMember", data={"chat_id": chat_id, "user_id": user_id, "only_if_banned": False})

    def restrict_chat_member(self, chat_id: int, user_id: int, can_send_messages: bool, until_ts: Optional[int] = None) -> None:
        permissions = {
            "can_send_messages": can_send_messages,
            "can_send_audios": can_send_messages,
            "can_send_documents": can_send_messages,
            "can_send_photos": can_send_messages,
            "can_send_videos": can_send_messages,
            "can_send_video_notes": can_send_messages,
            "can_send_voice_notes": can_send_messages,
            "can_send_polls": can_send_messages,
            "can_send_other_messages": can_send_messages,
            "can_add_web_page_previews": can_send_messages,
            "can_change_info": False,
            "can_invite_users": can_send_messages,
            "can_pin_messages": False,
            "can_manage_topics": False,
        }
        data = {"chat_id": chat_id, "user_id": user_id, "permissions": json.dumps(permissions)}
        if until_ts is not None:
            data["until_date"] = until_ts
        self.telegram_api("restrictChatMember", data=data)

    def kick_chat_member(self, chat_id: int, user_id: int) -> None:
        self.ban_chat_member(chat_id, user_id, until_ts=int(time.time()) + 35)
        self.unban_chat_member(chat_id, user_id)

    def download_telegram_file(self, file_path: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.session.get(
            f"{self.config.file_base_url}/{file_path}",
            timeout=TELEGRAM_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
        return destination

    def open_control_panel(self, chat_id: int, user_id: int, section: str = "home", payload: str = "") -> None:
        self.ui_handlers.open_control_panel(self, chat_id, user_id, section, payload)

    def edit_control_panel(self, chat_id: int, user_id: int, message_id: int, section: str = "home", payload: str = "") -> None:
        self.ui_handlers.edit_control_panel(self, chat_id, user_id, message_id, section, payload)

    def build_help_panel_text(self, section: str) -> str:
        return build_help_panel_text(section)

    def build_help_panel_markup(self, section: str) -> dict:
        return build_help_panel_markup(section)

    def build_control_panel(self, user_id: int, section: str, payload: str = "") -> Tuple[str, dict]:
        return self.control_panel_renderer.build_control_panel(self, user_id, section, payload)

    def handle_ui_pending_input(self, chat_id: int, user_id: int, text: str) -> bool:
        return self.ui_handlers.handle_ui_pending_input(self, chat_id, user_id, text)

    def owner_console_session_active(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != OWNER_USER_ID or chat_id != OWNER_USER_ID:
            return False
        return self.state.get_meta("owner_console_session", "").strip() == "1"

    def set_owner_console_session(self, enabled: bool) -> None:
        self.state.set_meta("owner_console_session", "1" if enabled else "0")

    def handle_owner_console_session_input(self, chat_id: int, user_id: Optional[int], raw_text: str) -> bool:
        if user_id != OWNER_USER_ID or chat_id != OWNER_USER_ID:
            return False
        command = (raw_text or "").strip()
        lowered = command.lower()
        if lowered in {"enterprise", "enterprise,", "энтерпрайз", "console", "консоль"}:
            self.set_owner_console_session(True)
            self.safe_send_text(
                chat_id,
                "Enterprise console включён.\n\n"
                "Дальше каждое сообщение будет выполнено как команда.\n"
                "Выход: `exit`\n"
                "Разовый запуск тоже работает: `/console <команда>` или `/sh <команда>`",
            )
            return True
        if not self.owner_console_session_active(chat_id, user_id):
            return False
        if lowered in {"exit", "quit", "выход", "стоп"}:
            self.set_owner_console_session(False)
            self.safe_send_text(chat_id, "Enterprise console выключен.")
            return True
        return self.handle_console_command(chat_id, user_id, command)

    def handle_update(self, item: dict) -> None:
        handle_telegram_update(self, item)

    def should_record_incoming_event(self, chat_id: int, user_id: Optional[int], message: dict, chat_type: str) -> bool:
        del chat_id
        if has_chat_access(self.state.authorized_user_ids, user_id):
            return True
        if chat_type in {"group", "supergroup"}:
            return True
        text = (message.get("text") or "").strip()
        if text and has_public_command_access(text):
            return False
        if message.get("caption") and has_public_command_access(message.get("caption") or ""):
            return False
        return False

    def record_incoming_event(self, chat_id: int, user_id: Optional[int], message: dict) -> None:
        from_user = message.get("from") or {}
        chat = message.get("chat") or {}
        message_id = message.get("message_id")
        username = from_user.get("username") or ""
        first_name = from_user.get("first_name") or ""
        last_name = from_user.get("last_name") or ""
        self.state.save_chat_title(chat_id, chat.get("title") or "")
        if message.get("new_chat_title"):
            self.state.save_chat_title(chat_id, message.get("new_chat_title") or "")
        self.state.upsert_chat_participant(
            chat_id,
            user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_bot=bool(from_user.get("is_bot")),
        )
        reply_user = (message.get("reply_to_message") or {}).get("from") or {}
        if reply_user.get("id") is not None:
            self.state.upsert_chat_participant(
                chat_id,
                reply_user.get("id"),
                username=reply_user.get("username") or "",
                first_name=reply_user.get("first_name") or "",
                last_name=reply_user.get("last_name") or "",
                is_bot=bool(reply_user.get("is_bot")),
            )
        for member in message.get("new_chat_members") or []:
            self.state.upsert_chat_participant(
                chat_id,
                member.get("id"),
                username=member.get("username") or "",
                first_name=member.get("first_name") or "",
                last_name=member.get("last_name") or "",
                is_bot=bool(member.get("is_bot")),
                last_status="member",
                mark_join=True,
            )
        left_member = message.get("left_chat_member") or {}
        if left_member.get("id") is not None:
            self.state.upsert_chat_participant(
                chat_id,
                left_member.get("id"),
                username=left_member.get("username") or "",
                first_name=left_member.get("first_name") or "",
                last_name=left_member.get("last_name") or "",
                is_bot=bool(left_member.get("is_bot")),
                last_status="left",
                mark_leave=True,
            )
        chat_type = (chat.get("type") or "")
        reply_to = message.get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        reply_to_message_id = reply_to.get("message_id")
        reply_to_user_id = reply_from.get("id")
        reply_to_username = reply_from.get("username") or ""
        forward_origin = extract_forward_origin(message)
        is_edited = 1 if message.get("edit_date") else 0

        def write_event(message_type: str, content: str, has_media: int = 0, file_kind: str = "") -> None:
            self.state.record_event(
                chat_id,
                user_id,
                "user",
                message_type,
                content,
                message_id,
                username,
                first_name,
                last_name,
                chat_type,
                reply_to_message_id=reply_to_message_id,
                reply_to_user_id=reply_to_user_id,
                reply_to_username=reply_to_username,
                forward_origin=forward_origin,
                has_media=has_media,
                file_kind=file_kind,
                is_edited=is_edited,
            )
            self.state.refresh_user_memory_profile(
                chat_id,
                user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

        self.sync_legacy_jarvis(message)

        if message.get("text"):
            message_type = "edited_text" if is_edited else "text"
            write_event(message_type, message.get("text") or "")
            return
        if message.get("caption"):
            message_type = "edited_caption" if is_edited else "caption"
            write_event(message_type, message.get("caption") or "")
        if message.get("photo"):
            caption = (message.get("caption") or "").strip() or "без подписи"
            write_event("photo", f"[Фото: {caption}]", has_media=1, file_kind="photo")
            return
        if message.get("voice"):
            duration = (message.get("voice") or {}).get("duration")
            write_event("voice", f"[Голосовое сообщение, duration={duration}]", has_media=1, file_kind="voice")
            return
        if message.get("animation"):
            caption = (message.get("caption") or "").strip() or "без подписи"
            write_event("animation", f"[GIF: {caption}]", has_media=1, file_kind="animation")
            return
        if message.get("sticker"):
            sticker = message.get("sticker") or {}
            emoji = sticker.get("emoji") or ""
            set_name = sticker.get("set_name") or ""
            details = ", ".join(part for part in [f"emoji={emoji}" if emoji else "", f"set={set_name}" if set_name else ""] if part)
            write_event("sticker", f"[Стикер{': ' + details if details else ''}]", has_media=1, file_kind="sticker")
            return
        if message.get("document"):
            document = message.get("document") or {}
            file_name = document.get("file_name") or "document"
            mime_type = document.get("mime_type") or ""
            write_event("document", f"[Документ: {file_name}{', ' + mime_type if mime_type else ''}]", has_media=1, file_kind="document")
            return
        if message.get("video"):
            video = message.get("video") or {}
            duration = video.get("duration")
            write_event("video", f"[Видео, duration={duration}]", has_media=1, file_kind="video")
            return
        if message.get("video_note"):
            video_note = message.get("video_note") or {}
            duration = video_note.get("duration")
            write_event("video_note", f"[Кружок, duration={duration}]", has_media=1, file_kind="video_note")
            return
        if message.get("audio"):
            audio = message.get("audio") or {}
            title = audio.get("title") or audio.get("file_name") or "audio"
            performer = audio.get("performer") or ""
            write_event("audio", f"[Аудио: {title}{', ' + performer if performer else ''}]", has_media=1, file_kind="audio")
            return
        if message.get("contact"):
            contact = message.get("contact") or {}
            label = " ".join(part for part in [contact.get("first_name") or "", contact.get("last_name") or ""] if part).strip() or (contact.get("phone_number") or "contact")
            write_event("contact", f"[Контакт: {label}]")
            return
        if message.get("location"):
            location = message.get("location") or {}
            details = [f"lat={location.get('latitude')}", f"lon={location.get('longitude')}"]
            if location.get("horizontal_accuracy") is not None:
                details.append(f"accuracy={location.get('horizontal_accuracy')}")
            if location.get("live_period") is not None:
                details.append(f"live_period={location.get('live_period')}")
            if location.get("heading") is not None:
                details.append(f"heading={location.get('heading')}")
            if location.get("proximity_alert_radius") is not None:
                details.append(f"proximity_alert_radius={location.get('proximity_alert_radius')}")
            write_event("location", f"[Локация: {', '.join(details)}]")
            return
        if message.get("new_chat_members"):
            for member in message.get("new_chat_members") or []:
                actor = build_service_actor_name(member)
                write_event("join", f"[В чат вошёл: {actor}]")
            return
        if message.get("left_chat_member"):
            actor = build_service_actor_name(message.get("left_chat_member") or {})
            write_event("leave", f"[Из чата вышел: {actor}]")
            return
        if message.get("pinned_message"):
            pinned = message.get("pinned_message") or {}
            summary = summarize_message_for_pin(pinned)
            write_event("pin", f"[Закреплено сообщение: {summary}]")
            return
        if message.get("new_chat_title"):
            write_event("chat_title", f"[Новое название чата: {message.get('new_chat_title')}]")
            return
        if message.get("new_chat_photo"):
            write_event("chat_photo", "[Обновлено фото чата]", has_media=1, file_kind="chat_photo")
            return

    def sync_legacy_jarvis(self, message: dict) -> None:
        if not self.legacy.enabled:
            return
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        if from_user.get("is_bot"):
            return
        chat_type = (chat.get("type") or "").lower()
        if chat_type not in {"group", "supergroup"}:
            return

        message_id = message.get("message_id")
        user_id = from_user.get("id")
        chat_id = chat.get("id")
        if message_id is None or user_id is None or chat_id is None:
            return

        text = (message.get("text") or "").strip()
        if not text:
            text = (message.get("caption") or "").strip()
        if not text:
            return

        try:
            unlocked = self.legacy.sync_message(
                chat_id=int(chat_id),
                message_id=int(message_id),
                user_id=int(user_id),
                username=from_user.get("username") or "",
                first_name=from_user.get("first_name") or "",
                text=text,
            )
            if unlocked:
                unlocked = self._filter_new_achievement_announcements(int(chat_id), int(user_id), unlocked)
                display_name = (from_user.get("first_name") or from_user.get("username") or str(user_id)).strip()
                announce_text = self.legacy.achievements.format_unlock_announcement(display_name, unlocked)
                if announce_text:
                    self.safe_send_text(int(chat_id), announce_text)
        except Exception as error:
            log_exception(f"legacy jarvis sync failed chat={chat_id} user={user_id}", error, limit=6)

    def handle_reaction_update(self, reaction_update: dict) -> None:
        dispatch_reaction_update(self, reaction_update)

    def handle_text_message(self, chat_id: int, user_id: Optional[int], message: dict, chat_type: str = "private") -> None:
        self.telegram_handlers.handle_text_message(self, chat_id, user_id, message, chat_type)

    def enforce_private_profanity_global_ban(self, chat_id: int, user_id: int, raw_text: str, message: dict) -> None:
        reason = f"pm profanity auto global ban: {truncate_text(' '.join((raw_text or '').split()), 160)}"
        managed_chat_ids = self.state.get_managed_group_chat_ids()
        from_user = message.get("from") or {}
        username = from_user.get("username") or ""
        first_name = from_user.get("first_name") or ""
        last_name = from_user.get("last_name") or ""
        banned_chat_ids: List[int] = []
        failed_chat_ids: List[int] = []

        for target_chat_id in managed_chat_ids:
            try:
                self.ban_chat_member(target_chat_id, user_id)
                banned_chat_ids.append(target_chat_id)
            except RequestException as error:
                failed_chat_ids.append(target_chat_id)
                log(f"private profanity global ban failed chat={target_chat_id} user={user_id}: {error}")
            self.state.add_moderation_action(target_chat_id, user_id, "ban", reason, OWNER_USER_ID)
            self.legacy.sync_moderation_event(
                chat_id=target_chat_id,
                user_id=user_id,
                action="ban",
                reason=reason,
                created_by_user_id=OWNER_USER_ID,
                source_ref="private_profanity_global_ban",
            )
            self.state.record_event(
                target_chat_id,
                user_id,
                "assistant",
                "moderation_private_profanity_global_ban",
                reason,
                username=username,
                first_name=first_name,
                last_name=last_name,
                chat_type="supergroup" if str(target_chat_id).startswith("-100") else "group",
            )

        self.state.record_event(
            chat_id,
            user_id,
            "assistant",
            "private_profanity_global_ban",
            reason,
            username=username,
            first_name=first_name,
            last_name=last_name,
            chat_type="private",
        )
        self.safe_send_text(chat_id, "Доступ заблокирован. За оскорбления в личных сообщениях включён глобальный бан.")
        applied_line = ", ".join(str(item) for item in banned_chat_ids) if banned_chat_ids else "нет"
        failed_line = ", ".join(str(item) for item in failed_chat_ids) if failed_chat_ids else "нет"
        self.notify_owner(
            "AUTO GLOBAL BAN • PM ABUSE\n"
            f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            f"user_id={user_id}\n"
            f"user={build_actor_name(user_id, username, first_name, last_name, 'user')}\n"
            f"Забанено чатов: {len(banned_chat_ids)}/{len(managed_chat_ids)}\n"
            f"Чаты, где применено: {applied_line}\n"
            f"Чаты с ошибкой: {failed_line}\n"
            f"Текст: {truncate_text(raw_text, 400)}"
        )

    def get_group_rules_text(self, message: Optional[dict]) -> str:
        chat = (message or {}).get("chat") or {}
        chat_id = int(chat.get("id") or 0)
        chat_title = self.state.get_chat_title(chat_id, chat.get("title") or "") if chat_id else (chat.get("title") or "")
        return _get_group_rules_text(chat_title)

    def render_auto_moderation_owner_report(
        self,
        *,
        chat_id: int,
        message: dict,
        target_user_id: int,
        target_label: str,
        decision: AutoModerationDecision,
        applied_action: str,
    ) -> str:
        chat = message.get("chat") or {}
        chat_title = self.state.get_chat_title(chat_id, chat.get("title") or "")
        raw_text = normalize_whitespace((message.get("text") or "").strip())
        severity_map = {
            "low": "низкая",
            "medium": "средняя",
            "high": "высокая",
        }
        applied_map = {
            "warn": "предупреждение",
            "mute": f"мут на {format_duration_seconds(decision.mute_seconds)}" if decision.mute_seconds > 0 else "мут",
            "ban": "бан",
        }
        lines = [
            "OWNER REPORT • AUTO MODERATION",
            "",
            "Что произошло:",
            f"• Чат: {chat_title}",
            f"• chat_id={chat_id}",
            f"• Участник: {target_label}",
            f"• user_id={target_user_id}",
            f"• Серьёзность: {severity_map.get(decision.severity, decision.severity)}",
            f"• Нарушение: {decision.public_reason}",
            f"• Код: {decision.code}",
            f"• Автодействие: {applied_map.get(applied_action, applied_action)}",
            "",
            "Основание:",
            truncate_text(raw_text, 700),
            "",
            "Решение владельца:",
            f"• {decision.suggested_owner_action or 'Посмотреть контекст и принять ручное решение.'}",
            "",
            "Быстрые действия:",
            "• reply в группе: «сними», «сними мут», «сними бан»",
            "• вручную: /warn /mute /ban /unmute /unban",
        ]
        return "\n".join(lines)

    def maybe_handle_owner_moderation_override(self, chat_id: int, user_id: Optional[int], raw_text: str, message: dict, chat_type: str) -> bool:
        if user_id != OWNER_USER_ID or chat_type not in {"group", "supergroup"}:
            return False
        normalized = normalize_whitespace(raw_text).lower()
        if not normalized or normalized.startswith("/"):
            return False
        compact = normalized.rstrip(")!., ")
        if not any(
            compact == token or compact.startswith(token + " ")
            for token in {"сними", "снять", "размуть", "разбань", "анмут", "анбан", "unmute", "unban"}
        ):
            return False

        requested_action = ""
        if compact in {"размуть", "анмут", "unmute"} or compact.endswith(" мут") or compact.endswith(" mute"):
            requested_action = "mute"
        elif compact in {"разбань", "анбан", "unban"} or compact.endswith(" бан") or compact.endswith(" ban"):
            requested_action = "ban"

        reply_to = (message.get("reply_to_message") or {})
        reply_from = reply_to.get("from") or {}
        target_user_id = reply_from.get("id") if reply_from and not reply_from.get("is_bot") else None
        target_label = ""
        action_to_lift = requested_action

        if target_user_id is not None:
            target_label = build_actor_name(
                target_user_id,
                reply_from.get("username") or "",
                reply_from.get("first_name") or "",
                reply_from.get("last_name") or "",
                "user",
            )
            if not action_to_lift:
                latest = self.state.get_latest_active_moderation(chat_id)
                if latest and latest[1] == int(target_user_id):
                    action_to_lift = latest[2]
        else:
            active_rows = self.state.get_active_moderations(chat_id, limit=6)
            if not active_rows:
                self.safe_send_text(chat_id, "Сейчас нет активных санкций, которые можно снять.")
                return True
            if len(active_rows) > 1:
                self.safe_send_text(chat_id, "Активно несколько санкций. Ответь этой командой на сообщение нужного участника.")
                return True
            _action_id, target_user_id, latest_action, _latest_reason = active_rows[0]
            action_to_lift = requested_action or latest_action
            row_user_id, target_label = self.state.resolve_chat_user(chat_id, str(target_user_id))
            if row_user_id is not None:
                target_user_id = row_user_id

        if target_user_id is None or not action_to_lift:
            self.safe_send_text(chat_id, "Не понял, какую санкцию снимать.")
            return True

        try:
            if action_to_lift == "mute":
                self.restrict_chat_member(chat_id, int(target_user_id), True)
                member_info = self.get_chat_member_info(chat_id, int(target_user_id))
                if (member_info.get("status") or "").lower() == "restricted" and not bool(member_info.get("can_send_messages", True)):
                    self.safe_send_text(chat_id, "Попробовал снять мут, но ограничение всё ещё висит. Возможно, санкцию держит другой бот или внешняя модерация Telegram.")
                    return True
                self.state.deactivate_active_moderation(chat_id, int(target_user_id), "mute")
                self.legacy.sync_moderation_event(
                    chat_id=chat_id,
                    user_id=int(target_user_id),
                    action="unmute",
                    reason="owner natural-language override",
                    created_by_user_id=user_id,
                    source_ref="owner_override",
                )
                self.safe_send_text(chat_id, f"Снял мут: {target_label or f'user_id={target_user_id}'}")
                return True
            if action_to_lift == "ban":
                self.unban_chat_member(chat_id, int(target_user_id))
                self.state.deactivate_active_moderation(chat_id, int(target_user_id), "ban")
                self.legacy.sync_moderation_event(
                    chat_id=chat_id,
                    user_id=int(target_user_id),
                    action="unban",
                    reason="owner natural-language override",
                    created_by_user_id=user_id,
                    source_ref="owner_override",
                )
                self.safe_send_text(chat_id, f"Снял бан: {target_label or f'user_id={target_user_id}'}")
                return True
        except RequestException as error:
            log(f"owner moderation override failed chat={chat_id} target={target_user_id} action={action_to_lift}: {error}")
            self.safe_send_text(chat_id, "Не смог снять санкцию. Проверь права бота.")
            return True

        self.safe_send_text(chat_id, "Не понял, какую санкцию снимать.")
        return True

    def maybe_apply_auto_moderation(self, chat_id: int, user_id: Optional[int], message: dict, chat_type: str) -> bool:
        return self.moderation_execution_service.maybe_apply_auto_moderation(
            self,
            chat_id=chat_id,
            user_id=user_id,
            message=message,
            chat_type=chat_type,
        )

    def apply_auto_moderation_decision(
        self,
        chat_id: int,
        target_user_id: int,
        message: dict,
        decision: AutoModerationDecision,
    ) -> None:
        self.moderation_execution_service.apply_auto_moderation_decision(
            self,
            chat_id=chat_id,
            target_user_id=target_user_id,
            message=message,
            decision=decision,
        )

    def handle_photo_message(self, chat_id: int, user_id: Optional[int], message: dict) -> None:
        self.telegram_handlers.handle_photo_message(self, chat_id, user_id, message)

    def handle_document_message(self, chat_id: int, user_id: Optional[int], message: dict, chat_type: str) -> None:
        self.telegram_handlers.handle_document_message(self, chat_id, user_id, message, chat_type)

    def handle_voice_message(self, chat_id: int, user_id: Optional[int], message: dict) -> None:
        self.telegram_handlers.handle_voice_message(self, chat_id, user_id, message)

    def build_voice_initial_prompt(self, chat_id: int, strict_trigger: bool = False) -> str:
        return self.telegram_handlers.build_voice_initial_prompt(self, chat_id, strict_trigger)

    def handle_command(self, chat_id: int, user_id: Optional[int], text: str, message: Optional[dict] = None, allow_followup_text: bool = False) -> bool:
        return self.command_dispatcher.handle_command(
            self,
            chat_id,
            user_id,
            text,
            message=message,
            allow_followup_text=allow_followup_text,
        )

    def run_text_task(
        self,
        chat_id: int,
        text: str,
        user_id: Optional[int] = None,
        chat_type: str = "private",
        assistant_persona: str = "",
        message: Optional[dict] = None,
        spontaneous_group_reply: bool = False,
    ) -> None:
        _run_text_task_service(
            self,
            chat_id=chat_id,
            text=text,
            user_id=user_id,
            chat_type=chat_type,
            assistant_persona=assistant_persona,
            message=message,
            spontaneous_group_reply=spontaneous_group_reply,
        )

    def run_recent_chat_report_task(self, chat_id: int, user_id: Optional[int], text: str, message: Optional[dict] = None) -> None:
        _run_recent_chat_report_task_service(self, chat_id=chat_id, user_id=user_id, text=text, message=message)

    def maybe_start_silent_photo_analysis(self, chat_id: int, user_id: int, message: dict) -> None:
        best_photo = max((message.get("photo") or []), key=lambda item: item.get("file_size", 0), default=None)
        if not best_photo:
            return
        message_id = int(message.get("message_id") or 0)
        if message_id <= 0:
            return
        meta_key = f"silent_photo_analysis:{chat_id}:{message_id}"
        if self.state.get_meta(meta_key, ""):
            return
        self.state.set_meta(meta_key, str(int(time.time())))
        worker = Thread(
            target=self.run_silent_photo_analysis,
            args=(chat_id, user_id, message_id, best_photo, (message.get("caption") or "").strip()),
            daemon=True,
        )
        worker.start()

    def run_silent_photo_analysis(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        photo: dict,
        caption: str,
    ) -> None:
        file_id = str(photo.get("file_id") or "")
        file_unique_id = str(photo.get("file_unique_id") or "")
        if not file_id:
            return
        analysis_text = ""
        risk_flags: List[str] = []
        media_sha256 = ""
        try:
            with self.temp_workspace() as workspace:
                file_info = self.get_file_info(file_id)
                file_path = file_info.get("file_path")
                if not file_path:
                    return
                local_path = workspace / build_download_name(file_path, fallback_name="silent_photo.jpg")
                self.download_telegram_file(file_path, local_path)
                media_sha256 = hashlib.sha256(local_path.read_bytes()).hexdigest()
                prompt = (
                    "Тихий анализ Telegram-фото для внутренней памяти бота.\n"
                    "Нужно кратко и без морализаторства оценить изображение как сигнал риска аккаунта.\n"
                    "Верни 4 строки:\n"
                    "сцена: ...\n"
                    "стиль_профиля: ...\n"
                    "флаги_риска: comma-separated from [none, suspicious_visual, likely_bot, bot_like, engagement_bait, mass_bait, fake_identity, promo_bait, scam_risk, romance_scam, sexual_bait, adult_promo, sexualized_profile]\n"
                    "почему: ...\n"
                    "Не выдумывай, пиши кратко."
                )
                analysis_text = self.run_codex(prompt, image_path=local_path, postprocess=False)
        except Exception as error:
            log(f"silent photo analysis failed chat={chat_id} message_id={message_id}: {error}")
        lowered = normalize_whitespace((analysis_text or "") + "\n" + (caption or "")).lower()
        keyword_map = {
            "suspicious_visual": ("suspicious_visual", "подозр", "неаутентич", "catfish"),
            "likely_bot": ("likely_bot", "bot_like", "ботоподоб", "automation"),
            "engagement_bait": ("engagement_bait", "bait", "приманк"),
            "mass_bait": ("mass_bait", "массов", "однотип"),
            "fake_identity": ("fake_identity", "fake_identity", "фейков", "чужое фото"),
            "promo_bait": ("promo_bait", "promo", "реклам", "продвиж"),
            "scam_risk": ("scam_risk", "scam", "развод", "скам"),
            "romance_scam": ("romance_scam", "romance", "love-scam", "романтическ"),
            "sexual_bait": ("sexual_bait", "sexual_bait", "эрот", "сексуализ"),
            "adult_promo": ("adult_promo", "adult", "18+", "onlyfans"),
            "sexualized_profile": ("sexualized_profile", "sexualized_profile", "провокацион"),
        }
        for canonical, markers in keyword_map.items():
            if any(marker in lowered for marker in markers):
                risk_flags.append(canonical)
        risk_flags = list(dict.fromkeys(risk_flags))
        if not analysis_text:
            analysis_text = (
                f"сцена: неизвестно\n"
                f"стиль_профиля: без анализа\n"
                f"флаги_риска: {', '.join(risk_flags) or 'none'}\n"
                f"почему: подпись={truncate_text(caption or '', 120)}"
            )
        self.state.record_participant_visual_signal(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            file_unique_id=file_unique_id,
            media_sha256=media_sha256,
            caption=caption,
            analysis_text=analysis_text,
            risk_flags=risk_flags,
        )
        self.state.record_message_subject(
            chat_id=chat_id,
            message_id=message_id,
            subject_type="photo",
            source_kind="silent_photo_analysis",
            user_id=user_id,
            summary=analysis_text,
            details={"caption": caption, "risk_flags": risk_flags},
        )
        self.state.set_active_subject(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            subject_type="photo",
            source="silent_photo_analysis",
        )
        self.state.refresh_participant_behavior_profile(user_id, chat_id=chat_id)

    def run_photo_task(self, chat_id: int, file_id: str, caption: str, message: Optional[dict] = None) -> None:
        _run_photo_task_service(
            self,
            chat_id,
            file_id,
            caption,
            message=message,
            default_image_prompt=DEFAULT_IMAGE_PROMPT,
            build_download_name_func=build_download_name,
            build_prompt_func=build_prompt,
            normalize_whitespace_func=normalize_whitespace,
            truncate_text_func=truncate_text,
        )

    def run_document_task(self, chat_id: int, file_id: str, document: dict, caption: str, message: Optional[dict] = None) -> None:
        _run_document_task_service(
            self,
            chat_id,
            file_id,
            document,
            caption,
            message=message,
            build_download_name_func=build_download_name,
            build_prompt_func=build_prompt,
            format_file_size_func=format_file_size,
            normalize_whitespace_func=normalize_whitespace,
            read_document_excerpt_func=read_document_excerpt,
            truncate_text_func=truncate_text,
        )

    def run_voice_task(self, chat_id: int, user_id: Optional[int], file_id: str, message: Optional[dict] = None) -> None:
        _run_voice_task_service(
            self,
            chat_id,
            user_id,
            file_id,
            message=message,
            safe_mode_reply=SAFE_MODE_REPLY,
            build_download_name_func=build_download_name,
            build_voice_transcription_help_func=build_voice_transcription_help,
            contains_voice_trigger_name_func=contains_voice_trigger_name,
            should_process_group_message_func=should_process_group_message,
            is_dangerous_request_func=is_dangerous_request,
        )

    def run_audio_task(self, chat_id: int, user_id: Optional[int], file_id: str, message: Optional[dict] = None) -> None:
        _run_audio_task_service(
            self,
            chat_id,
            user_id,
            file_id,
            message=message,
            safe_mode_reply=SAFE_MODE_REPLY,
            build_download_name_func=build_download_name,
            build_voice_transcription_help_func=build_voice_transcription_help,
            contains_voice_trigger_name_func=contains_voice_trigger_name,
            should_process_group_message_func=should_process_group_message,
            is_dangerous_request_func=is_dangerous_request,
        )

    def process_due_moderation_actions(self) -> None:
        now = time.time()
        if now < self.next_moderation_check_ts:
            return
        self.next_moderation_check_ts = now + 15
        due = self.state.get_due_moderation_actions(int(now), limit=20)
        for action_id, chat_id, user_id, action in due:
            try:
                if action == "ban":
                    self.unban_chat_member(chat_id, user_id)
                elif action == "mute":
                    self.restrict_chat_member(chat_id, user_id, True)
                self.state.complete_moderation_action(action_id)
                self.state.record_event(chat_id, user_id, "assistant", f"auto_{action}_expire", f"[Автоснятие {action} user_id={user_id}]")
                self.legacy.sync_moderation_event(
                    chat_id=chat_id,
                    user_id=user_id,
                    action=f"auto_{action}_expire",
                    reason=f"auto expire {action}",
                    created_by_user_id=None,
                    source_ref=f"moderation_action:{action_id}",
                )
            except RequestException as error:
                log(f"failed to process due moderation action id={action_id}: {error}")

    def resolve_moderation_target(self, chat_id: int, command_payload: str, message: Optional[dict]) -> Tuple[Optional[int], str, str]:
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        payload = (command_payload or "").strip()
        if reply_from.get("id") is not None:
            target_user_id = reply_from.get("id")
            target_label = build_user_autofix_label(reply_from)
            return int(target_user_id), strip_html_tags(target_label), payload
        if not payload:
            return None, "", ""
        parts = payload.split(maxsplit=1)
        target_token = parts[0]
        reason = parts[1].strip() if len(parts) > 1 else ""
        target_user_id, target_label = self.state.resolve_chat_user(chat_id, target_token)
        return target_user_id, target_label, reason

    def handle_moderation_command(self, chat_id: int, user_id: Optional[int], moderation: Tuple[str, str], message: Optional[dict]) -> bool:
        command, payload = moderation
        if chat_id > 0:
            self.safe_send_text(chat_id, "Эти команды работают только в группе или супергруппе.")
            return True
        if not self.is_chat_admin(chat_id, user_id):
            self.safe_send_text(chat_id, "Недостаточно прав.")
            return True

        duration_seconds = None
        target_payload = payload
        if command in {"tban", "tmute"}:
            duration_token, rest = split_duration_and_rest(payload)
            duration_seconds = parse_duration_to_seconds(duration_token)
            if duration_seconds is None:
                self.safe_send_text(chat_id, MODERATION_USAGE_TEXT)
                return True
            target_payload = rest

        target_user_id, target_label, reason = self.resolve_moderation_target(chat_id, target_payload, message)
        if target_user_id is None:
            self.safe_send_text(chat_id, MODERATION_USAGE_TEXT)
            return True
        if not self.can_moderate_target(chat_id, target_user_id):
            self.safe_send_text(chat_id, "Этого пользователя модерировать нельзя.")
            return True

        action_name = command[1:] if command.startswith('t') else command
        until_ts = int(time.time()) + duration_seconds if duration_seconds else None
        audit_reason = reason or "без причины"
        try:
            if command in {"ban", "tban"}:
                self.ban_chat_member(chat_id, target_user_id, until_ts=until_ts)
                if duration_seconds:
                    self.state.add_moderation_action(chat_id, target_user_id, "ban", audit_reason, user_id, expires_at=until_ts)
                    self.safe_send_text(chat_id, f"Бан выдан: {target_label} на {format_duration_seconds(duration_seconds)}")
                else:
                    self.safe_send_text(chat_id, f"Бан выдан: {target_label}")
            elif command == "unban":
                self.unban_chat_member(chat_id, target_user_id)
                self.state.deactivate_active_moderation(chat_id, target_user_id, "ban")
                self.safe_send_text(chat_id, f"Бан снят: {target_label}")
            elif command in {"mute", "tmute"}:
                self.restrict_chat_member(chat_id, target_user_id, False, until_ts=until_ts)
                if duration_seconds:
                    self.state.add_moderation_action(chat_id, target_user_id, "mute", audit_reason, user_id, expires_at=until_ts)
                    self.safe_send_text(chat_id, f"Мут выдан: {target_label} на {format_duration_seconds(duration_seconds)}")
                else:
                    self.safe_send_text(chat_id, f"Мут выдан: {target_label}")
            elif command == "unmute":
                self.restrict_chat_member(chat_id, target_user_id, True)
                self.state.deactivate_active_moderation(chat_id, target_user_id, "mute")
                self.safe_send_text(chat_id, f"Мут снят: {target_label}")
            elif command == "kick":
                self.kick_chat_member(chat_id, target_user_id)
                self.safe_send_text(chat_id, f"Пользователь удалён: {target_label}")
            else:
                self.safe_send_text(chat_id, MODERATION_USAGE_TEXT)
                return True
        except RequestException as error:
            log(f"moderation command failed chat={chat_id} target={target_user_id} command={command}: {error}")
            self.safe_send_text(chat_id, "Команда модерации не выполнилась. Проверь права бота.")
            return True

        self.legacy.sync_moderation_event(
            chat_id=chat_id,
            user_id=target_user_id,
            action=command,
            reason=audit_reason,
            created_by_user_id=user_id,
            expires_at=until_ts,
            source_ref=f"command:{command}",
        )
        self.state.record_event(chat_id, target_user_id, "assistant", f"moderation_{action_name}", f"[{command} {target_user_id}: {audit_reason}]")
        return True

    def apply_warn_limit_action(self, chat_id: int, actor_user_id: Optional[int], target_user_id: int, target_label: str, warn_mode: str) -> None:
        if warn_mode == "ban":
            self.ban_chat_member(chat_id, target_user_id)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="ban",
                reason="warn auto ban",
                created_by_user_id=actor_user_id,
                source_ref="warn_limit",
            )
            self.state.record_event(chat_id, target_user_id, "assistant", "warn_auto_ban", f"[warn auto ban {target_user_id}]")
            self.safe_send_text(chat_id, f"Лимит предупреждений достигнут. Бан: {target_label}")
            return
        if warn_mode.startswith("tban:"):
            duration_seconds = int(warn_mode.split(":", 1)[1])
            until_ts = int(time.time()) + duration_seconds
            self.ban_chat_member(chat_id, target_user_id, until_ts=until_ts)
            self.state.add_moderation_action(chat_id, target_user_id, "ban", "warn auto tban", actor_user_id, expires_at=until_ts)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="tban",
                reason="warn auto tban",
                created_by_user_id=actor_user_id,
                expires_at=until_ts,
                source_ref="warn_limit",
            )
            self.state.record_event(chat_id, target_user_id, "assistant", "warn_auto_tban", f"[warn auto tban {target_user_id} {duration_seconds}]")
            self.safe_send_text(chat_id, f"Лимит предупреждений достигнут. Временный бан: {target_label} на {format_duration_seconds(duration_seconds)}")
            return
        if warn_mode == "kick":
            self.kick_chat_member(chat_id, target_user_id)
            self.state.record_event(chat_id, target_user_id, "assistant", "warn_auto_kick", f"[warn auto kick {target_user_id}]")
            self.safe_send_text(chat_id, f"Лимит предупреждений достигнут. Удаление: {target_label}")
            return
        if warn_mode.startswith("tmute:"):
            duration_seconds = int(warn_mode.split(":", 1)[1])
            until_ts = int(time.time()) + duration_seconds
            self.restrict_chat_member(chat_id, target_user_id, False, until_ts=until_ts)
            self.state.add_moderation_action(chat_id, target_user_id, "mute", "warn auto tmute", actor_user_id, expires_at=until_ts)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="tmute",
                reason="warn auto tmute",
                created_by_user_id=actor_user_id,
                expires_at=until_ts,
                source_ref="warn_limit",
            )
            self.state.record_event(chat_id, target_user_id, "assistant", "warn_auto_tmute", f"[warn auto tmute {target_user_id} {duration_seconds}]")
            self.safe_send_text(chat_id, f"Лимит предупреждений достигнут. Временный мут: {target_label} на {format_duration_seconds(duration_seconds)}")
            return
        self.restrict_chat_member(chat_id, target_user_id, False)
        self.legacy.sync_moderation_event(
            chat_id=chat_id,
            user_id=target_user_id,
            action="mute",
            reason="warn auto mute",
            created_by_user_id=actor_user_id,
            source_ref="warn_limit",
        )
        self.state.record_event(chat_id, target_user_id, "assistant", "warn_auto_mute", f"[warn auto mute {target_user_id}]")
        self.safe_send_text(chat_id, f"Лимит предупреждений достигнут. Мут: {target_label}")

    def handle_warn_command(self, chat_id: int, user_id: Optional[int], warn_command: Tuple[str, str], message: Optional[dict]) -> bool:
        command, payload = warn_command
        if chat_id > 0:
            self.safe_send_text(chat_id, "Эти команды работают только в группе или супергруппе.")
            return True
        if not self.is_chat_admin(chat_id, user_id):
            self.safe_send_text(chat_id, "Недостаточно прав.")
            return True

        if command == "modlog":
            rows = self.state.get_moderation_log_rows(chat_id, limit=14)
            if not rows:
                self.safe_send_text(chat_id, "Лог модерации пока пуст.")
                return True
            self.safe_send_text(chat_id, render_event_rows(rows, title="ModLog"))
            return True

        if command == "setwarnlimit":
            if not payload.isdigit() or int(payload) < 1 or int(payload) > 20:
                self.safe_send_text(chat_id, WARN_USAGE_TEXT)
                return True
            self.state.set_warn_limit(chat_id, int(payload))
            self.safe_send_text(chat_id, f"Лимит предупреждений: {int(payload)}")
            return True

        if command == "setwarnmode":
            mode_token, rest = split_duration_and_rest(payload)
            mode = mode_token.strip().lower()
            if mode not in {"mute", "tmute", "ban", "tban", "kick"}:
                self.safe_send_text(chat_id, WARN_USAGE_TEXT)
                return True
            stored_mode = mode
            if mode in {"tmute", "tban"}:
                duration_seconds = parse_duration_to_seconds(rest)
                if duration_seconds is None:
                    self.safe_send_text(chat_id, WARN_USAGE_TEXT)
                    return True
                stored_mode = f"{mode}:{duration_seconds}"
            self.state.set_warn_mode(chat_id, stored_mode)
            self.safe_send_text(chat_id, f"Режим предупреждений: {mode if mode not in {'tmute','tban'} else mode + ' ' + format_duration_seconds(duration_seconds)}")
            return True

        if command == "warntime":
            if not payload:
                warn_limit, warn_mode, warn_expire_seconds = self.state.get_warn_settings(chat_id)
                self.safe_send_text(chat_id, f"Срок жизни предупреждений: {format_duration_seconds(warn_expire_seconds) if warn_expire_seconds > 0 else 'off'}")
                return True
            if payload.strip().lower() in {"off", "0", "none"}:
                self.state.set_warn_time(chat_id, 0)
                self.safe_send_text(chat_id, "Срок жизни предупреждений: off")
                return True
            warn_expire_seconds = parse_duration_to_seconds(payload)
            if warn_expire_seconds is None:
                self.safe_send_text(chat_id, WARN_USAGE_TEXT)
                return True
            self.state.set_warn_time(chat_id, warn_expire_seconds)
            self.safe_send_text(chat_id, f"Срок жизни предупреждений: {format_duration_seconds(warn_expire_seconds)}")
            return True

        target_user_id, target_label, reason = self.resolve_moderation_target(chat_id, payload, message)
        if target_user_id is None:
            self.safe_send_text(chat_id, WARN_USAGE_TEXT)
            return True
        if not self.can_moderate_target(chat_id, target_user_id):
            self.safe_send_text(chat_id, "Этого пользователя модерировать нельзя.")
            return True

        if command in {"warn", "dwarn", "swarn"}:
            warn_limit, warn_mode, warn_expire_seconds = self.state.get_warn_settings(chat_id)
            warning_expires_at = int(time.time()) + warn_expire_seconds if warn_expire_seconds > 0 else None
            count = self.state.add_warning(chat_id, target_user_id, reason or "без причины", user_id, expires_at=warning_expires_at)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action=command,
                reason=reason or "без причины",
                created_by_user_id=user_id,
                expires_at=warning_expires_at,
                source_ref=f"command:{command}",
            )
            self.state.record_event(chat_id, target_user_id, "assistant", command, f"[{command} {target_user_id}: {reason or 'без причины'}]")
            if command == "dwarn" and (message or {}).get("reply_to_message"):
                reply_message_id = ((message or {}).get("reply_to_message") or {}).get("message_id")
                if reply_message_id:
                    try:
                        self.delete_message(chat_id, int(reply_message_id))
                    except RequestException as error:
                        log(f"dwarn delete failed chat={chat_id} message_id={reply_message_id}: {error}")
            if command != "swarn":
                self.safe_send_text(chat_id, f"Предупреждение: {target_label} ({count}/{warn_limit})")
            if count >= warn_limit:
                try:
                    self.apply_warn_limit_action(chat_id, user_id, target_user_id, target_label, warn_mode)
                except RequestException as error:
                    log(f"warn auto action failed chat={chat_id} target={target_user_id}: {error}")
                    self.safe_send_text(chat_id, "Лимит предупреждений достигнут, но авто-действие не выполнилось. Проверь права бота.")
            return True

        if command == "warns":
            count = self.state.get_warning_count(chat_id, target_user_id)
            warn_limit, warn_mode, warn_expire_seconds = self.state.get_warn_settings(chat_id)
            expire_text = format_duration_seconds(warn_expire_seconds) if warn_expire_seconds > 0 else "off"
            self.safe_send_text(chat_id, f"Предупреждения {target_label}: {count}/{warn_limit}. Режим: {warn_mode}. Срок: {expire_text}")
            return True

        if command == "warnreasons":
            rows = self.state.get_warning_rows(chat_id, target_user_id, limit=5)
            if not rows:
                self.safe_send_text(chat_id, f"У {target_label} пока нет предупреждений.")
                return True
            lines = [f"Причины предупреждений: {target_label}"]
            for created_at, warn_reason in rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
                lines.append(f"[{stamp}] {warn_reason or 'без причины'}")
            self.safe_send_text(chat_id, "\n".join(lines))
            return True

        if command == "rmwarn":
            count = self.state.remove_last_warning(chat_id, target_user_id)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="unwarn",
                reason="rmwarn",
                created_by_user_id=user_id,
                source_ref="command:rmwarn",
            )
            self.safe_send_text(chat_id, f"Предупреждение снято: {target_label}. Осталось: {count}")
            return True

        if command == "resetwarn":
            self.state.reset_warnings(chat_id, target_user_id)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="resetwarn",
                reason="resetwarn",
                created_by_user_id=user_id,
                source_ref="command:resetwarn",
            )
            self.safe_send_text(chat_id, f"Предупреждения сброшены: {target_label}")
            return True

        self.safe_send_text(chat_id, WARN_USAGE_TEXT)
        return True

    def handle_new_chat_members(self, chat_id: int, message: dict) -> None:
        enabled, template = self.state.get_welcome_settings(chat_id)
        for member in message.get("new_chat_members") or []:
            self.state.upsert_chat_participant(
                chat_id,
                member.get("id"),
                username=member.get("username") or "",
                first_name=member.get("first_name") or "",
                last_name=member.get("last_name") or "",
                is_bot=bool(member.get("is_bot")),
                last_status="member",
                mark_join=True,
            )
        if not enabled:
            return
        chat = message.get("chat") or {}
        chat_title = self.state.get_chat_title(chat_id, chat.get("title") or "")
        for member in message.get("new_chat_members") or []:
            if member.get("is_bot") and self.bot_user_id is not None and member.get("id") == self.bot_user_id:
                continue
            welcome_text = build_welcome_text(template, member, chat_title)
            if welcome_text:
                self.safe_send_text(chat_id, welcome_text)

    def send_help_panel(self, chat_id: int, section: str = "main") -> None:
        self.send_inline_message(chat_id, build_help_panel_text(section), build_help_panel_markup(section))

    def send_access_denied(self, chat_id: int) -> None:
        log(f"send_access_denied chat={chat_id}")
        self.safe_send_text(chat_id, ACCESS_DENIED_TEXT)

    def handle_callback_query(self, callback_query: dict) -> None:
        callback_id = str(callback_query.get("id") or "")
        data = str(callback_query.get("data") or "")
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        from_user = callback_query.get("from") or {}
        chat_id = int(chat.get("id") or 0)
        user_id = int(from_user.get("id") or 0)
        if data.startswith("console_stop:"):
            target_chat_id = parse_int(data.split(":", 1)[1] if ":" in data else "")
            if not target_chat_id or target_chat_id != chat_id or not is_owner_private_chat(user_id, chat_id):
                self.answer_callback_query(callback_id)
                return
            stopped, status_text = self.request_stop_local_console_process(chat_id)
            try:
                message_id = int(message.get("message_id") or 0)
                if message_id:
                    self.edit_inline_message(
                        chat_id,
                        message_id,
                        self.fit_single_telegram_message(
                            f"Консоль\n\nСтатус: {'останавливаю' if stopped else 'без изменений'}\n\n{status_text}"
                        ),
                        self.build_console_status_markup(chat_id, running=False),
                    )
            except Exception as error:
                log(f"failed to update console stop message chat={chat_id}: {error}")
            self.answer_callback_query(callback_id)
            return
        self.ui_handlers.handle_callback_query(self, callback_query)

    def handle_commands_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        self.send_help_panel(chat_id, "main" if has_chat_access(self.state.authorized_user_ids, user_id) else "public")
        return True

    def notify_owner(self, text: str) -> None:
        self.safe_send_text(OWNER_USER_ID, text)

    def resolve_enterprise_delivery_chat_id(self, source_chat_id: int, chat_type: str, assistant_persona: str) -> int:
        del chat_type, assistant_persona
        return source_chat_id

    def process_appeal_release_actions(self, user_id: int, actions: List[dict], event_name: str, resolution: str) -> None:
        seen: Set[Tuple[int, str]] = set()
        for item in actions:
            chat_id = int(item.get("chat_id", 0))
            action = (item.get("action") or "").strip().lower()
            if chat_id == 0 or action not in {"ban", "mute"}:
                continue
            dedupe_key = (chat_id, action)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            try:
                if action == "ban":
                    self.unban_chat_member(chat_id, user_id)
                else:
                    self.restrict_chat_member(chat_id, user_id, True)
            except RequestException as error:
                log(f"appeal release failed chat={chat_id} user={user_id} action={action}: {error}")
            self.state.deactivate_active_moderation(chat_id, user_id, action)
            self.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=user_id,
                action=event_name,
                reason=f"{resolution} [{action}]",
                created_by_user_id=OWNER_USER_ID,
                source_ref=f"appeal:{action}",
            )
            self.state.record_event(chat_id, user_id, "assistant", event_name, f"{resolution} [{action}]")

    def handle_appeal_command(self, chat_id: int, user_id: Optional[int], text: str) -> bool:
        if user_id is None:
            self.safe_send_text(chat_id, "Не удалось определить пользователя.")
            return True
        appeal_text = text[len("/appeal"):].strip()
        if not appeal_text:
            self.open_control_panel(chat_id, user_id, "appeals")
            return True

        result = self.appeals.submit_appeal(user_id, chat_id, appeal_text)
        self.state.record_event(chat_id, user_id, "assistant", f"appeal_{result.get('status', 'unknown')}", appeal_text)
        self.safe_send_text(chat_id, str(result.get("message", "Апелляция обработана.")))

        if result.get("status") == "auto_approved":
            resolution = f"[appeal auto approved user_id={user_id}]"
            self.process_appeal_release_actions(
                user_id,
                result.get("release_actions", []),
                "appeal_auto_release",
                resolution,
            )
            self.notify_owner(
                f"Автоапелляция #{result.get('appeal_id')} одобрена автоматически.\n"
                f"user_id={user_id}\n"
                f"Причина: {appeal_text}"
            )
            return True

        if result.get("status") == "new":
            snapshot = result.get("snapshot", {})
            self.notify_owner(
                f"Новая апелляция #{result.get('appeal_id')}\n"
                f"user_id={user_id}\n"
                f"Причина: {appeal_text}\n"
                f"Активных банов: {len(snapshot.get('active_bans', []))}\n"
                f"Подтвержденных нарушений: {snapshot.get('confirmed_violations', 0)}\n"
                f"Активных предупреждений: {snapshot.get('active_warnings', 0)}\n\n"
                f"Команды:\n"
                f"/appeal_review {result.get('appeal_id')}\n"
                f"/appeal_approve {result.get('appeal_id')} <решение>\n"
                f"/appeal_reject {result.get('appeal_id')} <решение>"
            )
        return True

    def handle_appeal_admin_command(self, chat_id: int, user_id: Optional[int], text: str) -> bool:
        if user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, "Недостаточно прав.")
            return True

        if text == "/appeals":
            self.open_control_panel(chat_id, user_id, "admin_appeals")
            return True

        if text.startswith("/appeal_review"):
            parts = text.split(maxsplit=2)
            if len(parts) < 2 or not parts[1].isdigit():
                self.safe_send_text(chat_id, "Используй: /appeal_review <id>")
                return True
            result = self.appeals.mark_in_review(int(parts[1]), user_id)
            self.safe_send_text(chat_id, str(result["message"]))
            return True

        approve = text.startswith("/appeal_approve")
        reject = text.startswith("/appeal_reject")
        if not (approve or reject):
            return False

        parts = text.split(maxsplit=2)
        if len(parts) < 2 or not parts[1].isdigit():
            self.safe_send_text(chat_id, f"Используй: {'/appeal_approve' if approve else '/appeal_reject'} <id> [решение]")
            return True
        appeal_id = int(parts[1])
        resolution = parts[2].strip() if len(parts) > 2 else ("Одобрено модератором." if approve else "Отклонено модератором.")
        result = self.appeals.resolve_appeal(appeal_id, user_id, approved=approve, resolution=resolution)
        self.safe_send_text(chat_id, str(result.get("message", f"Статус: {result.get('status', 'unknown')}")))
        if not result.get("ok"):
            return True

        target_user_id = int(result["user_id"])
        if approve:
            self.process_appeal_release_actions(
                target_user_id,
                result.get("release_actions", []),
                "appeal_manual_release",
                f"[appeal approved #{appeal_id}]",
            )
            self.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} одобрена.\n{resolution}")
        else:
            self.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} отклонена.\n{resolution}")
        self.state.record_event(chat_id, target_user_id, "assistant", f"appeal_{result['status']}", resolution)
        return True

    def owner_autofix_enabled(self) -> bool:
        value = self.state.get_meta("owner_autofix_enabled", "")
        if not value:
            return self.config.owner_autofix
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def set_owner_autofix_enabled(self, enabled: bool) -> None:
        self.state.set_meta("owner_autofix_enabled", "1" if enabled else "0")

    def handle_owner_autofix_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, "Только создатель может управлять автоисправлением.")
            return True
        option = (payload or "status").strip().lower()
        if not option or option == "status":
            enabled = self.owner_autofix_enabled()
            self.safe_send_text(chat_id, f"Автоисправление создателя: {'включено' if enabled else 'выключено'}")
            return True
        if option in {"on", "off"}:
            self.set_owner_autofix_enabled(option == "on")
            self.safe_send_text(chat_id, f"Автоисправление создателя: {'включено' if option == 'on' else 'выключено'}")
            return True
        self.safe_send_text(chat_id, OWNER_AUTOFIX_USAGE)
        return True

    def handle_welcome_command(self, chat_id: int, user_id: Optional[int], welcome_command: Tuple[str, str]) -> bool:
        command, payload = welcome_command
        if chat_id > 0:
            self.safe_send_text(chat_id, "Welcome настраивается только в группе или супергруппе.")
            return True
        if not self.is_chat_admin(chat_id, user_id):
            self.safe_send_text(chat_id, "Недостаточно прав.")
            return True
        enabled, template = self.state.get_welcome_settings(chat_id)
        if command == "welcome":
            mode = payload.strip().lower()
            if not mode or mode == "status":
                self.safe_send_text(chat_id, f"Welcome: {'on' if enabled else 'off'}\nШаблон: {template}")
                return True
            if mode not in {"on", "off"}:
                self.safe_send_text(chat_id, WELCOME_USAGE_TEXT)
                return True
            self.state.set_welcome_enabled(chat_id, mode == "on")
            self.safe_send_text(chat_id, f"Welcome: {mode}")
            return True
        if command == "setwelcome":
            if not payload.strip():
                self.safe_send_text(chat_id, WELCOME_USAGE_TEXT)
                return True
            self.state.set_welcome_template(chat_id, payload.strip())
            self.safe_send_text(chat_id, "Welcome-шаблон обновлён.")
            return True
        if command == "resetwelcome":
            self.state.reset_welcome_template(chat_id)
            self.safe_send_text(chat_id, "Welcome-шаблон сброшен к default.")
            return True
        self.safe_send_text(chat_id, WELCOME_USAGE_TEXT)
        return True

    def handle_remember_command(self, chat_id: int, user_id: Optional[int], fact: str) -> bool:
        if not fact:
            self.safe_send_text(chat_id, REMEMBER_USAGE_TEXT)
            return True
        self.state.add_fact(chat_id, fact, user_id)
        self.safe_send_text(chat_id, "Запомнил.")
        return True

    def handle_recall_command(self, chat_id: int, user_id: Optional[int], query: str) -> bool:
        summary = self.state.get_summary(chat_id)
        facts = self.state.render_facts(chat_id, query=query, limit=10)
        events = self.state.get_event_context(chat_id, query or "история чата", limit=10)
        parts = []
        if summary:
            parts.append(f"Сводка:\n{summary}")
        if facts:
            parts.append(f"Факты:\n{facts}")
        if events:
            parts.append(f"События:\n{events}")
        if not parts:
            self.safe_send_text(chat_id, "Память по этому чату пока пуста.")
            return True
        self.safe_send_text(chat_id, "\n\n".join(parts))
        return True

    def handle_status_command(self, chat_id: int) -> bool:
        snapshot = self.state.get_status_snapshot(chat_id)
        lines = [
            f"Создатель: {OWNER_USER_ID}",
            f"Режим: {self.state.get_mode(chat_id)}",
            f"События чата: {snapshot['events_count']}",
            f"Факты: {snapshot['facts_count']}",
            f"История: {snapshot['history_count']}",
            f"User memory profiles: {snapshot['user_memory_profiles']}",
            f"Relation memory rows: {snapshot['relation_memory_rows']}",
            f"Summary snapshots: {snapshot['summary_snapshots']}",
            f"Autobiographical rows: {snapshot['autobiographical_rows']}",
            f"Reflections: {snapshot['reflections_rows']}",
            f"World-state rows: {snapshot['world_state_rows']}",
            f"Всего событий в БД: {snapshot['total_events']}",
            f"Route decisions в БД: {snapshot['total_route_decisions']}",
            f"Upgrade активен: {'да' if self.state.global_upgrade_active else 'нет'}",
            f"STT backend: {self.config.stt_backend}",
            f"Только безопасный чат: {self.config.safe_chat_only}",
            f"Heartbeat: {self.config.heartbeat_path}",
            f"Heartbeat timeout: {self.config.heartbeat_timeout_seconds}s",
            f"Legacy Jarvis DB: {'подключена' if self.legacy.enabled else 'не подключена'}",
            f"Legacy путь: {self.config.legacy_jarvis_db_path}",
        ]
        self.safe_send_text(chat_id, "\n".join(lines))
        return True

    def handle_search_command(self, chat_id: int, query: str) -> bool:
        if not query:
            self.safe_send_text(chat_id, SEARCH_USAGE_TEXT)
            return True
        rows = self.state.search_events(chat_id, query, limit=10)
        if not rows:
            self.safe_send_text(chat_id, "Совпадений не найдено.")
            return True
        self.safe_send_text(chat_id, render_event_rows(rows, title=f"Поиск: {query}"))
        return True

    def handle_console_command(self, chat_id: int, user_id: Optional[int], command: str) -> bool:
        if user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        command = (command or "").strip()
        if not command:
            self.safe_send_text(chat_id, CONSOLE_USAGE_TEXT)
            return True
        if not self.state.try_start_chat_task(chat_id):
            self.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return True
        status_message_id = self.send_inline_message(
            chat_id,
            f"Консоль\n$ {command}\n\nСтатус: запускаю...",
            self.build_console_status_markup(chat_id, running=True),
        )
        worker = Thread(
            target=self.run_console_task,
            args=(chat_id, command, status_message_id),
            daemon=True,
        )
        worker.start()
        return True

    def run_console_task(self, chat_id: int, command: str, status_message_id: Optional[int]) -> None:
        started_at = time.perf_counter()
        try:
            self.send_chat_action(chat_id, "typing")
            job_id = self.start_console_job(command)
            if not job_id:
                raise RuntimeError("Enterprise не вернул job_id для console-задачи.")
            with self.console_jobs_lock:
                self.console_jobs[str(chat_id)] = {
                    "chat_id": int(chat_id),
                    "command": command,
                    "job_id": job_id,
                    "status_message_id": int(status_message_id) if status_message_id is not None else None,
                    "started_at": time.time(),
                    "stop_requested": False,
                }
            next_update_at = 0.0
            streamed_any = False
            stop_requested = False
            seen_events: List[str] = []
            seen_stream_count = 0
            final_snapshot: Optional[Dict[str, object]] = None
            while True:
                now = time.perf_counter()
                snapshot = self.get_console_job_snapshot(job_id)
                if snapshot is None:
                    raise RuntimeError("Enterprise job не найден. Возможно, сервер перезапустился.")
                events = [normalize_whitespace(str(item)) for item in (snapshot.get("events") or [])]
                events = [item for item in events if item]
                stream_entries = [item for item in (snapshot.get("stream_events") or []) if isinstance(item, dict)]
                if len(events) > len(seen_events):
                    new_events = events[len(seen_events):]
                    self.send_console_stream_chunks(
                        chat_id,
                        command,
                        "\n\n".join(new_events),
                        include_header=not streamed_any,
                        reply_to_message_id=status_message_id,
                    )
                    seen_events = events
                    streamed_any = True
                if len(stream_entries) > seen_stream_count:
                    rendered_lines = [
                        self.format_console_stream_entry(item)
                        for item in stream_entries[seen_stream_count:]
                    ]
                    rendered_lines = [line for line in rendered_lines if line]
                    if rendered_lines:
                        self.send_console_stream_chunks(
                            chat_id,
                            command,
                            "\n".join(rendered_lines),
                            include_header=not streamed_any,
                            reply_to_message_id=status_message_id,
                        )
                        streamed_any = True
                    seen_stream_count = len(stream_entries)
                if now >= next_update_at:
                    self.send_chat_action(chat_id, "typing")
                    elapsed = max(1, int(now - started_at))
                    preview_lines = [
                        self.format_console_stream_entry(item)
                        for item in stream_entries[-24:]
                    ]
                    preview_lines = [line for line in preview_lines if line]
                    if preview_lines:
                        preview = truncate_text("\n".join(preview_lines[-16:]), 1600)
                    else:
                        preview = truncate_text("\n\n".join(events[-12:]), 1600) if events else "[пока без событий]"
                    with self.console_jobs_lock:
                        job = self.console_jobs.get(str(chat_id)) or {}
                        stop_requested = bool(job.get("stop_requested"))
                    status_text = (
                        f"Enterprise Core | console\n"
                        f"$ {command}\n\n"
                        f"Статус: {'останавливаю...' if stop_requested else f'выполняется ({elapsed}s)'}\n"
                        f"job_id: {job_id}\n"
                        f"Событий: {len(events)}\n"
                        f"Stream: {len(stream_entries)}\n"
                        f"Лента: {'идёт ниже' if streamed_any else 'ожидание'}\n\n"
                        f"{preview}"
                    )
                    if status_message_id is not None:
                        self.edit_inline_message(
                            chat_id,
                            status_message_id,
                            status_text,
                            self.build_console_status_markup(chat_id, running=not bool(snapshot.get("done")) and not stop_requested),
                        )
                    next_update_at = now + CONSOLE_STREAM_UPDATE_SECONDS
                if bool(snapshot.get("done")):
                    final_snapshot = snapshot
                    break
                time.sleep(0.4)
            answer_text = normalize_whitespace(str((final_snapshot or {}).get("answer") or ""))
            error_text = normalize_whitespace(str((final_snapshot or {}).get("error") or ""))
            final_stream_entries = [item for item in ((final_snapshot or {}).get("stream_events") or []) if isinstance(item, dict)]
            completed_stream_messages = [
                normalize_whitespace(str(item.get("text") or ""))
                for item in final_stream_entries
                if str(item.get("kind") or "").strip().lower() == "assistant_text"
                and str(item.get("state") or "").strip().lower() == "completed"
                and normalize_whitespace(str(item.get("text") or ""))
            ]
            combined_output = "\n\n".join(part for part in [*seen_events[-160:], answer_text, error_text] if part)
            elapsed_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            exit_code = int((final_snapshot or {}).get("exit_code") or 0)
            final_status = "остановлено" if stop_requested and exit_code != 0 else "завершено"
            final_text = (
                f"Enterprise Core | console\n"
                f"$ {command}\n\n"
                f"Статус: {final_status}\n"
                f"Код выхода: {exit_code}\n"
                f"job_id: {job_id}\n"
                f"Время: {elapsed_ms} ms\n"
                f"Событий: {len(seen_events)}\n"
                f"Stream: {len(final_stream_entries)}\n"
                f"Лента: {'отправлена ниже' if streamed_any else 'событий не было'}"
            )
            if answer_text and answer_text not in completed_stream_messages:
                self.safe_send_text(chat_id, f"Итог Enterprise:\n\n{answer_text}", reply_to_message_id=status_message_id)
            if error_text:
                self.safe_send_text(chat_id, f"Ошибка Enterprise:\n\n{error_text}", reply_to_message_id=status_message_id)
            self.send_console_output_document(
                chat_id,
                command,
                combined_output,
                exit_code=exit_code,
                reply_to_message_id=status_message_id,
            )
            self.send_console_stream_copy_document(
                chat_id,
                command,
                final_stream_entries,
                reply_to_message_id=status_message_id,
            )
            if status_message_id is not None:
                self.edit_inline_message(
                    chat_id,
                    status_message_id,
                    final_text,
                    self.build_console_status_markup(chat_id, running=False),
                )
                self.mark_answer_delivered_via_status(chat_id)
            else:
                self.safe_send_text(chat_id, final_text)
        except Exception as error:
            log_exception(f"console task failed chat={chat_id}", error, limit=8)
            error_text = f"Консоль\n$ {command}\n\nОшибка запуска:\n{error}"
            if status_message_id is not None:
                try:
                    self.edit_inline_message(
                        chat_id,
                        status_message_id,
                        error_text,
                        self.build_console_status_markup(chat_id, running=False),
                    )
                    self.mark_answer_delivered_via_status(chat_id)
                except Exception:
                    self.safe_send_text(chat_id, error_text)
            else:
                self.safe_send_text(chat_id, error_text)
        finally:
            self.clear_local_console_process(chat_id)
            self.state.finish_chat_task(chat_id)

    def handle_resources_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self.safe_send_text(chat_id, render_resource_summary())
        return True

    def handle_git_status_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self.safe_send_text(chat_id, render_git_status_summary(self.script_path.parent))
        return True

    def handle_git_last_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        limit = 5
        if payload:
            try:
                limit = max(1, min(15, int(payload)))
            except ValueError:
                self.safe_send_text(chat_id, GIT_LAST_USAGE_TEXT)
                return True
        self.safe_send_text(chat_id, render_git_last_commits(self.script_path.parent, limit=limit))
        return True

    def handle_errors_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        limit = 12
        if payload:
            try:
                limit = max(1, min(30, int(payload)))
            except ValueError:
                self.safe_send_text(chat_id, ERRORS_USAGE_TEXT)
                return True
        lines = read_recent_log_highlights(self.log_path, limit=limit)
        if not lines:
            self.safe_send_text(chat_id, "В последних логах явных ошибок не найдено.")
            return True
        self.safe_send_text(chat_id, "Ошибки и сбои из хвоста лога:\n" + "\n".join(f"- {line}" for line in lines))
        return True

    def handle_events_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        category = "all"
        limit = 12
        if payload:
            parts = payload.split()
            for part in parts:
                lowered = part.lower()
                if lowered in {"restart", "access", "system", "all"}:
                    category = lowered
                    continue
                try:
                    limit = max(1, min(30, int(part)))
                except ValueError:
                    self.safe_send_text(chat_id, EVENTS_USAGE_TEXT)
                    return True
        lines = read_recent_operational_highlights(self.log_path, limit=limit, category=category)
        if not lines:
            self.safe_send_text(chat_id, "В последних логах заметных служебных событий не найдено.")
            return True
        self.safe_send_text(chat_id, f"Служебные события из хвоста лога ({category}):\n" + "\n".join(f"- {line}" for line in lines))
        return True

    def handle_topproc_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self.safe_send_text(chat_id, render_top_processes())
        return True

    def handle_disk_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self.safe_send_text(chat_id, render_disk_summary())
        return True

    def handle_net_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        self.safe_send_text(chat_id, render_network_summary())
        return True

    def handle_sd_list_command(self, chat_id: int, user_id: Optional[int], raw_path: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        try:
            target = resolve_sdcard_path(raw_path, allow_missing=False, default_to_root=True)
        except ValueError as error:
            self.safe_send_text(chat_id, str(error))
            return True
        if not target.exists():
            self.safe_send_text(chat_id, f"Путь не найден: {target}")
            return True
        if not target.is_dir():
            self.safe_send_text(chat_id, f"Это не папка: {target}")
            return True
        items = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        if not items:
            self.safe_send_text(chat_id, f"Папка пуста: {target}")
            return True
        lines = [f"/sdcard список: {target}"]
        for item in items[:60]:
            marker = "DIR" if item.is_dir() else "FILE"
            size_part = ""
            if item.is_file():
                try:
                    size_part = f" ({format_file_size(item.stat().st_size)})"
                except OSError:
                    size_part = ""
            lines.append(f"- [{marker}] {item.name}{size_part}")
        if len(items) > 60:
            lines.append(f"... ещё: {len(items) - 60}")
        self.safe_send_text(chat_id, "\n".join(lines))
        return True

    def handle_sd_send_command(self, chat_id: int, user_id: Optional[int], raw_path: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        if not raw_path:
            self.safe_send_text(chat_id, SD_SEND_USAGE_TEXT)
            return True
        try:
            target = resolve_sdcard_path(raw_path, allow_missing=False, default_to_root=False)
        except ValueError as error:
            self.safe_send_text(chat_id, str(error))
            return True
        if not target.exists():
            self.safe_send_text(chat_id, f"Файл не найден: {target}")
            return True
        if not target.is_file():
            self.safe_send_text(chat_id, f"Нужен именно файл, а не папка: {target}")
            return True
        self.send_document(chat_id, target, caption=f"Файл из /sdcard\n{target}")
        return True

    def handle_sd_save_command(self, chat_id: int, user_id: Optional[int], raw_target: str, message: Optional[dict] = None) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        source_message = message or {}
        if source_message.get("text"):
            source_message = (source_message.get("reply_to_message") or {})
        media = extract_message_media_file(source_message)
        if media is None:
            self.safe_send_text(chat_id, "Нужен reply на сообщение с файлом/медиа или подпись /sdsave у документа.")
            return True
        file_id, suggested_name = media
        try:
            destination = resolve_sdcard_save_target(raw_target, suggested_name)
        except ValueError as error:
            self.safe_send_text(chat_id, str(error))
            return True
        try:
            ensure_sdcard_save_target_writable(destination)
        except ValueError as error:
            log(f"sd save unavailable target={destination} error={error}")
            self.safe_send_text(chat_id, str(error))
            return True
        file_info = self.get_file_info(file_id)
        file_path = file_info.get("file_path")
        if not file_path:
            self.safe_send_text(chat_id, "Telegram не вернул путь к файлу.")
            return True
        try:
            self.download_telegram_file(file_path, destination)
        except Exception as error:
            log_exception(f"sd save failed target={destination}", error, limit=8)
            self.safe_send_text(chat_id, f"Не удалось сохранить файл:\n{error}")
            return True
        self.safe_send_text(chat_id, f"Сохранено:\n{destination}")
        return True

    def handle_who_said_command(self, chat_id: int, query: str) -> bool:
        if not query:
            self.safe_send_text(chat_id, WHO_SAID_USAGE_TEXT)
            return True
        rows = self.state.search_events(chat_id, query, limit=12)
        if not rows:
            self.safe_send_text(chat_id, "Совпадений не найдено.")
            return True
        user_rows = [row for row in rows if row[5] == "user"]
        counts: Dict[str, int] = {}
        for created_at, user_id, username, first_name, last_name, role, message_type, content in user_rows:
            actor = build_actor_name(user_id, username, first_name, last_name, role)
            counts[actor] = counts.get(actor, 0) + 1
        if not counts:
            self.safe_send_text(chat_id, "Совпадения есть, но только в сообщениях Jarvis.")
            return True
        summary = "\n".join(f"- {name}: {count}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10])
        details = render_event_rows(user_rows[:8], title=f"Кто писал: {query}")
        footer = (
            "\n\nГраницы ответа:\n"
            "- это результат локального поиска по chat_events для текущего запроса, а не полный вывод по всей истории чата\n"
            "- прямые наблюдения: найденные совпадения и их авторы в этой поисковой выборке\n"
            "- если старые или нерелевантные сообщения не попали в поиск, ответ может быть неполным\n"
        )
        self.safe_send_text(chat_id, f"Совпадения по авторам:\n{summary}\n\n{details}{footer}")
        return True

    def handle_history_command(self, chat_id: int, raw_target: str, message: Optional[dict]) -> bool:
        target_user_id: Optional[int] = None
        target_username = ""
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        cleaned = (raw_target or "").strip()
        if cleaned:
            if cleaned.startswith("@"):
                target_username = cleaned.lstrip("@")
            else:
                try:
                    target_user_id = int(cleaned)
                except ValueError:
                    target_username = cleaned.lstrip("@")
        elif reply_to and not reply_from.get("is_bot"):
            target_user_id = reply_from.get("id")
            target_username = reply_from.get("username") or ""
        else:
            self.safe_send_text(chat_id, HISTORY_USAGE_TEXT)
            return True
        label, rows = self.state.get_user_timeline(chat_id, target_user_id=target_user_id, target_username=target_username, limit=12)
        if not rows:
            self.safe_send_text(chat_id, "По этому участнику пока мало данных.")
            return True
        self.safe_send_text(chat_id, render_timeline_rows(label, rows))
        return True

    def handle_daily_command(self, chat_id: int, day: str) -> bool:
        target_day, rows = self.state.get_daily_summary_context(chat_id, day)
        if not rows:
            self.safe_send_text(chat_id, f"За {target_day} событий не найдено.")
            return True
        counts: Dict[str, int] = {}
        for created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
            actor = build_actor_name(user_id, username, first_name, last_name, role)
            counts[actor] = counts.get(actor, 0) + 1
        top = "\n".join(f"- {name}: {count}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8])
        body = render_event_rows(rows[-12:], title=f"День: {target_day}")
        self.safe_send_text(chat_id, f"Активность за {target_day}:\n{top}\n\n{body}")
        return True

    def handle_digest_command(self, chat_id: int, day: str) -> bool:
        self.safe_send_text(chat_id, self.render_chat_digest_text(chat_id, day))
        return True

    def handle_recent_chat_report_command(self, chat_id: int, user_id: Optional[int], text: str, message: Optional[dict]) -> bool:
        if user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        if not self.state.try_start_chat_task(chat_id):
            self.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return True
        self.send_chat_action(chat_id, "typing")
        worker = Thread(
            target=self.run_recent_chat_report_task,
            args=(chat_id, user_id, text, message),
            daemon=True,
        )
        worker.start()
        return True

    def handle_routes_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not is_owner_private_chat(user_id, chat_id):
            self.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        limit = 8
        if payload:
            try:
                limit = max(1, min(20, int(payload)))
            except ValueError:
                self.safe_send_text(chat_id, ROUTES_USAGE_TEXT)
                return True
        self.safe_send_text(chat_id, render_route_diagnostics_rows(self.state.get_recent_request_diagnostics(limit=limit)))
        return True

    def handle_memory_chat_command(self, chat_id: int, user_id: Optional[int], query: str) -> bool:
        return self.owner_handlers.handle_memory_chat_command(self, chat_id, user_id, query)

    def handle_memory_user_command(self, chat_id: int, user_id: Optional[int], raw_target: str, message: Optional[dict]) -> bool:
        return self.owner_handlers.handle_memory_user_command(self, chat_id, user_id, raw_target, message)

    def handle_memory_summary_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_memory_summary_command(self, chat_id, user_id)

    def handle_self_state_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_self_state_command(self, chat_id, user_id)

    def handle_world_state_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_world_state_command(self, chat_id, user_id)

    def handle_drives_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_drives_command(self, chat_id, user_id)

    def handle_autobio_command(self, chat_id: int, user_id: Optional[int], query: str) -> bool:
        return self.owner_handlers.handle_autobio_command(self, chat_id, user_id, query)

    def handle_skills_command(self, chat_id: int, user_id: Optional[int], query: str) -> bool:
        return self.owner_handlers.handle_skills_command(self, chat_id, user_id, query)

    def handle_reflections_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_reflections_command(self, chat_id, user_id, payload)

    def handle_chat_digest_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_chat_digest_command(self, chat_id, user_id, payload)

    def handle_chat_deep_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_chat_deep_command(self, chat_id, user_id, payload)

    def handle_whois_command(self, chat_id: int, user_id: Optional[int], payload: str, message: Optional[dict]) -> bool:
        return self.owner_handlers.handle_whois_command(self, chat_id, user_id, payload, message)

    def handle_profilecheck_command(self, chat_id: int, user_id: Optional[int], payload: str, message: Optional[dict]) -> bool:
        return self.owner_handlers.handle_profilecheck_command(self, chat_id, user_id, payload, message)

    def handle_whats_happening_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_whats_happening_command(self, chat_id, user_id, payload)

    def handle_summary24h_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_summary24h_command(self, chat_id, user_id, payload)

    def handle_conflicts_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_conflicts_command(self, chat_id, user_id, payload)

    def handle_ownergraph_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_ownergraph_command(self, chat_id, user_id, payload)

    def handle_watchlist_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_watchlist_command(self, chat_id, user_id, payload)

    def handle_reliable_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_reliable_command(self, chat_id, user_id, payload)

    def handle_suspects_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_suspects_command(self, chat_id, user_id, payload)

    def handle_achievement_audit_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_achievement_audit_command(self, chat_id, user_id, payload)

    def render_chat_digest_text(self, target_chat_id: int, day: str) -> str:
        return self.owner_handlers.render_chat_digest_text(self, target_chat_id, day)

    def handle_owner_report_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_owner_report_command(self, chat_id, user_id)

    def handle_repair_status_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_repair_status_command(self, chat_id, user_id)

    def handle_quality_report_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_quality_report_command(self, chat_id, user_id)

    def handle_self_heal_status_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        return self.owner_handlers.handle_self_heal_status_command(self, chat_id, user_id)

    def handle_self_heal_run_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_self_heal_run_command(self, chat_id, user_id, payload)

    def handle_self_heal_approve_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_self_heal_approve_command(self, chat_id, user_id, payload)

    def handle_self_heal_deny_command(self, chat_id: int, user_id: Optional[int], payload: str) -> bool:
        return self.owner_handlers.handle_self_heal_deny_command(self, chat_id, user_id, payload)

    def render_owner_report_text(self, chat_id: int) -> str:
        return self.owner_handlers.render_owner_report_text(self, chat_id)

    def inspect_runtime_log(self, window_seconds: int = 86400) -> Dict[str, object]:
        return inspect_runtime_log(self.log_path, window_seconds=window_seconds)

    def read_recent_log_highlights(self, limit: int = 8) -> List[str]:
        return read_recent_log_highlights(self.log_path, limit=limit)

    def read_recent_operational_highlights(self, limit: int = 8, category: str = "all") -> List[str]:
        return read_recent_operational_highlights(self.log_path, limit=limit, category=category)

    def render_resource_summary(self) -> str:
        return render_resource_summary()

    def render_bridge_runtime_watch(self) -> str:
        script_dir = Path(__file__).resolve().parent
        supervisor_log_path = Path(getattr(self, "supervisor_log_path", script_dir / "supervisor_boot.log"))
        return _render_bridge_runtime_watch(
            psutil_module=psutil,
            format_bytes_func=format_bytes,
            truncate_text_func=truncate_text,
            heartbeat_path=self.heartbeat_path,
            bridge_log_path=self.log_path,
            supervisor_log_path=supervisor_log_path,
            runtime_log_snapshot=self.inspect_runtime_log(),
            telegram_ping_text=self.get_telegram_ping_text(),
        )

    def get_telegram_ping_text(self, ttl_seconds: int = 30) -> str:
        now = time.time()
        cached_at = float(getattr(self, "_telegram_ping_checked_at", 0.0) or 0.0)
        cached_value = str(getattr(self, "_telegram_ping_text", "") or "").strip()
        if cached_value and now - cached_at <= max(5, ttl_seconds):
            return cached_value
        started_at = time.perf_counter()
        try:
            self.telegram_api("getMe")
            latency_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            ping_text = f"{latency_ms} ms"
        except RequestException:
            ping_text = "недоступен"
        self._telegram_ping_checked_at = now
        self._telegram_ping_text = ping_text
        return ping_text

    def render_route_diagnostics_rows(self, rows: List[sqlite3.Row]) -> str:
        return render_route_diagnostics_rows(rows)

    def handle_export_command(self, chat_id: int, scope: str) -> bool:
        scope_clean = (scope or "chat").strip() or "chat"
        valid_scope = scope_clean == "chat" or scope_clean == "today" or scope_clean.startswith("@")
        if not valid_scope:
            try:
                int(scope_clean)
                valid_scope = True
            except ValueError:
                valid_scope = False
        if not valid_scope:
            self.safe_send_text(chat_id, EXPORT_USAGE_TEXT)
            return True
        rows = self.state.export_events(chat_id, scope_clean, limit=40)
        if not rows:
            self.safe_send_text(chat_id, "Для этого экспорта пока нет данных.")
            return True
        self.safe_send_text(chat_id, render_event_rows(rows, title=f"Экспорт: {scope_clean}"))
        return True

    def handle_portrait_command(self, chat_id: int, user_id: Optional[int], raw_target: str, message: Optional[dict]) -> bool:
        target_user_id: Optional[int] = None
        target_username = ""
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        cleaned = (raw_target or "").strip()
        if cleaned:
            if cleaned.startswith("@"):
                target_username = cleaned.lstrip("@")
            else:
                try:
                    target_user_id = int(cleaned)
                except ValueError:
                    target_username = cleaned.lstrip("@")
        elif reply_to and not reply_from.get("is_bot"):
            target_user_id = reply_from.get("id")
            target_username = (reply_from.get("username") or "")
        else:
            self.safe_send_text(chat_id, PORTRAIT_USAGE_TEXT)
            return True

        if not self.state.try_start_chat_task(chat_id):
            self.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return True

        self.send_chat_action(chat_id, "typing")
        self.safe_send_text(chat_id, "Собираю портрет...")
        worker = Thread(
            target=self.run_portrait_task,
            args=(chat_id, target_user_id, target_username),
            daemon=True,
        )
        worker.start()
        return True

    def run_portrait_task(self, chat_id: int, target_user_id: Optional[int], target_username: str) -> None:
        try:
            label, context = self.state.get_participant_profile_context(chat_id, target_user_id=target_user_id, target_username=target_username)
            if not context:
                self.safe_send_text(chat_id, "Недостаточно данных по этому участнику в текущем чате.")
                return
            prompt = _build_portrait_prompt(label, context)
            answer = self.run_codex(prompt)
            self.state.record_event(chat_id, None, "assistant", "portrait", answer)
            self.safe_send_text(chat_id, answer)
        finally:
            self.state.finish_chat_task(chat_id)

    def handle_restart_command(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, "Запрос отклонён по соображениям безопасности")
            return True
        self.state.record_autobiographical_event(
            category="owner",
            event_type="restart_requested",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested restart",
            details="restart requested via /restart",
            status="accepted",
            importance=65,
            open_state="closed",
            tags="owner,restart",
        )
        self.safe_send_text(
            chat_id,
            "Self-restart отключён. Процесс остаётся в сети и больше не перезапускает сам себя; для обновления кода нужен внешний restart supervisor.",
        )
        return True

    def handle_upgrade_command(self, chat_id: int, user_id: Optional[int], task: str, is_private_chat: bool = False) -> bool:
        if not task:
            self.safe_send_text(chat_id, UPGRADE_USAGE_TEXT)
            return True
        if not is_private_chat or user_id != OWNER_USER_ID:
            self.safe_send_text(chat_id, UPGRADE_PRIVATE_ONLY_TEXT)
            return True
        if is_dangerous_request(task):
            self.safe_send_text(chat_id, "Запрос отклонён по соображениям безопасности")
            return True

        if not self.state.try_start_upgrade(chat_id):
            self.safe_send_text(chat_id, UPGRADE_ALREADY_RUNNING_TEXT)
            return True

        autobiographical_id = self.state.record_autobiographical_event(
            category="owner",
            event_type="upgrade",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="codex_workspace",
            title=truncate_text(task, 160),
            details=f"upgrade started: {truncate_text(task, 600)}",
            status="running",
            importance=85,
            open_state="open",
            tags="owner,upgrade,workspace",
        )
        self.send_chat_action(chat_id, "typing")
        self.safe_send_status(chat_id, UPGRADE_RUNNING_TEXT)
        worker = Thread(
            target=self.run_upgrade_task,
            args=(chat_id, task, autobiographical_id, user_id),
            daemon=True,
        )
        worker.start()
        return True

    def run_upgrade_task(self, chat_id: int, task: str, autobiographical_id: int, user_id: Optional[int]) -> None:
        try:
            prompt = _build_upgrade_request_prompt(task)
            answer = self.run_codex_with_progress(
                chat_id,
                prompt,
                initial_status=UPGRADE_RUNNING_TEXT,
                sandbox_mode="danger-full-access",
                approval_policy="never",
                timeout_seconds=self.config.enterprise_task_timeout if self.config.enterprise_task_timeout is not None else 0,
            )
            self.state.append_history(chat_id, "user", f"[Upgrade request: {task}]")
            self.state.append_history(chat_id, "assistant", answer)
            self.safe_send_text(chat_id, answer)
            success = not answer.startswith(UPGRADE_FAILED_TEXT) and answer != UPGRADE_TIMEOUT_TEXT
            if success:
                self.safe_send_text(chat_id, UPGRADE_APPLIED_TEXT)
            self.state.update_autobiographical_event(
                autobiographical_id,
                status="completed" if success else "failed",
                details=truncate_text(answer, 1400),
                open_state="closed",
            )
            report = SelfCheckReport(
                outcome="ok" if success else "error",
                answer=answer,
                flags=(),
                observed_basis=("workspace-runtime",),
                uncertain_points=() if success else ("upgrade-failed-or-timeout",),
            )
            self.run_post_task_reflection(
                chat_id=chat_id,
                user_id=user_id,
                route_decision=RouteDecision(
                    persona="enterprise",
                    intent="upgrade",
                    chat_type="private",
                    route_kind="codex_workspace",
                    source_label="workspace",
                    use_live=False,
                    use_web=False,
                    use_events=False,
                    use_database=False,
                    use_reply=False,
                    use_workspace=True,
                    guardrails=("runtime-verification", "no-system-actions", "respect-enterprise-mode"),
                ),
                user_text=task,
                report=report,
                source="upgrade",
            )
            self.refresh_world_state_registry("upgrade", chat_id=chat_id)
            self.recompute_drive_scores()
        finally:
            self.state.finish_upgrade(chat_id)


    def restart_process(self) -> None:
        log("restart requested but suppressed: self-restart is disabled")
        return

    def build_codex_command(self, *, image_path: Optional[Path] = None, sandbox_mode: Optional[str] = None, approval_policy: Optional[str] = None, json_output: bool = False) -> List[str]:
        command = ["codex"]
        effective_approval_policy = approval_policy
        if effective_approval_policy is None and self.config.safe_chat_only:
            effective_approval_policy = "never"
        command.append("exec")
        if effective_approval_policy == "never" and sandbox_mode == "danger-full-access":
            command.append("--dangerously-bypass-approvals-and-sandbox")
        elif effective_approval_policy in {"never", "on-request"} and sandbox_mode == "workspace-write":
            command.append("--full-auto")
        if json_output:
            command.append("--json")
        command.append("--skip-git-repo-check")
        effective_sandbox = sandbox_mode
        if effective_sandbox is None and self.config.safe_chat_only:
            effective_sandbox = "read-only"
        if effective_sandbox:
            command.extend(["--sandbox", effective_sandbox])
        if image_path is not None:
            command.extend(["-i", str(image_path)])
        return command

    def ask_codex(
        self,
        chat_id: int,
        user_text: str,
        user_id: Optional[int] = None,
        chat_type: str = "private",
        assistant_persona: str = "",
        message: Optional[dict] = None,
        spontaneous_group_reply: bool = False,
        suppress_status_messages: bool = False,
    ) -> str:
        return _ask_codex_service(
            self,
            chat_id=chat_id,
            user_text=user_text,
            user_id=user_id,
            chat_type=chat_type,
            assistant_persona=assistant_persona,
            message=message,
            spontaneous_group_reply=spontaneous_group_reply,
            suppress_status_messages=suppress_status_messages,
            build_meta_identity_answer_func=build_meta_identity_answer,
            build_owner_contact_reply_func=build_owner_contact_reply,
            analyze_request_route_func=analyze_request_route,
            enrich_self_check_report_func=enrich_self_check_report,
            apply_self_check_contract_func=apply_self_check_contract,
            render_enterprise_runtime_report_func=render_enterprise_runtime_report,
            build_context_budget_status_func=build_context_budget_status,
            build_progress_target_label_func=build_progress_target_label,
            detect_local_chat_query_func=detect_local_chat_query,
            is_explicit_runtime_probe_request_func=is_explicit_runtime_probe_request,
            is_explicit_runtime_restart_request_func=is_explicit_runtime_restart_request,
            postprocess_answer_func=postprocess_answer,
            owner_user_id=OWNER_USER_ID,
            owner_agent_running_text=OWNER_AGENT_RUNNING_TEXT,
            jarvis_agent_running_text=JARVIS_AGENT_RUNNING_TEXT,
            default_enterprise_workspace_timeout=DEFAULT_ENTERPRISE_WORKSPACE_TIMEOUT,
            heartbeat_guard_cls=HeartbeatGuard,
            progress_status_guard_cls=ProgressStatusGuard,
        )

    def build_reply_context(self, chat_id: int, message: Optional[dict]) -> str:
        return _build_reply_context_service(self, chat_id, message)

    def message_refers_to_active_subject(self, user_text: str) -> bool:
        return _message_refers_to_active_subject_service(user_text)

    def build_active_subject_context(
        self,
        chat_id: int,
        user_id: Optional[int],
        user_text: str,
        message: Optional[dict],
    ) -> str:
        return _build_active_subject_context_service(self, chat_id, user_id, user_text, message)

    def build_current_discussion_context(
        self,
        chat_id: int,
        *,
        message: Optional[dict],
        user_id: Optional[int],
        active_group_followup: bool = False,
    ) -> str:
        return self.context_pipeline.build_current_discussion_context(
            self,
            chat_id,
            message=message,
            user_id=user_id,
            active_group_followup=active_group_followup,
        )

    def build_text_context_bundle(
        self,
        *,
        chat_id: int,
        user_text: str,
        route_decision: RouteDecision,
        user_id: Optional[int],
        message: Optional[dict],
        reply_context: str,
        active_group_followup: bool = False,
    ) -> ContextBundle:
        return self.context_pipeline.build_text_context_bundle(
            self,
            chat_id=chat_id,
            user_text=user_text,
            route_decision=route_decision,
            user_id=user_id,
            message=message,
            reply_context=reply_context,
            active_group_followup=active_group_followup,
        )

    def build_attachment_context_bundle(
        self,
        *,
        chat_id: int,
        prompt_text: str,
        persona: str,
        message: Optional[dict],
        reply_context: str,
    ) -> ContextBundle:
        return self.context_pipeline.build_attachment_context_bundle(
            self,
            chat_id=chat_id,
            prompt_text=prompt_text,
            persona=persona,
            message=message,
            reply_context=reply_context,
        )

    def record_route_diagnostic(
        self,
        *,
        chat_id: int,
        user_id: Optional[int],
        route_decision: RouteDecision,
        report: SelfCheckReport,
        started_at: float,
        query_text: str,
        request_trace_id: str = "",
        task_id: str = "",
        execution_trace: Optional[ExecutionTrace] = None,
        live_records: Optional[Sequence[LiveProviderRecord]] = None,
    ) -> None:
        persisted_report = build_persisted_self_check_report(
            report,
            route_decision=route_decision,
            live_records=tuple(live_records) if live_records is not None else self.live_gateway.consume_records(),
        )
        self.state.record_request_diagnostic(
            chat_id=chat_id,
            user_id=user_id,
            chat_type=route_decision.chat_type,
            persona=route_decision.persona,
            intent=route_decision.intent,
            route_kind=route_decision.route_kind,
            source_label=route_decision.source_label,
            request_kind=route_decision.request_kind,
            used_live=route_decision.use_live,
            used_web=route_decision.use_web,
            used_events=route_decision.use_events,
            used_database=route_decision.use_database,
            used_reply=route_decision.use_reply,
            used_workspace=route_decision.use_workspace,
            guardrails=", ".join(route_decision.guardrails),
            outcome=persisted_report.outcome,
            response_mode=persisted_report.mode,
            sources=", ".join(persisted_report.sources),
            tools_used=", ".join(persisted_report.tools_used),
            memory_used=", ".join(persisted_report.memory_used),
            confidence=persisted_report.confidence,
            freshness=persisted_report.freshness,
            notes=persisted_report.notes,
            latency_ms=max(1, int((time.perf_counter() - started_at) * 1000)),
            query_text=query_text,
            request_trace_id=request_trace_id,
            task_id=task_id,
            tools_attempted=", ".join(execution_trace.tools_attempted) if execution_trace else "",
            contract_satisfied=(1 if execution_trace and execution_trace.contract_satisfied else 0),
        )
        if task_id:
            self.state.update_task_run(
                task_id,
                verification_state=persisted_report.mode,
                outcome=persisted_report.outcome,
                evidence_text=persisted_report.answer,
                tools_used=", ".join(persisted_report.tools_used),
                memory_used=", ".join(persisted_report.memory_used),
            )
            self.state.record_task_event(
                task_id=task_id,
                chat_id=chat_id,
                request_trace_id=request_trace_id,
                phase="route_diagnostic",
                status=persisted_report.mode,
                detail=f"outcome={persisted_report.outcome}; route={route_decision.route_kind}; sources={', '.join(persisted_report.sources)}",
                evidence_text=persisted_report.notes,
            )

    def request_text_with_retry(
        self,
        method: str,
        url: str,
        *,
        attempts: int = 2,
        retry_delay_seconds: float = 1.0,
        **kwargs,
    ) -> str:
        last_error: Optional[RequestException] = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                self.beat_heartbeat()
                if method.lower() == "get":
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)
                response.raise_for_status()
                self.beat_heartbeat()
                return response.text
            except RequestException as error:
                last_error = error
                self.beat_heartbeat()
                if attempt >= max(1, attempts):
                    break
                time.sleep(retry_delay_seconds)
        assert last_error is not None
        raise last_error

    def request_json_with_retry(
        self,
        method: str,
        url: str,
        *,
        attempts: int = 2,
        retry_delay_seconds: float = 1.0,
        **kwargs,
    ) -> dict:
        text = self.request_text_with_retry(
            method,
            url,
            attempts=attempts,
            retry_delay_seconds=retry_delay_seconds,
            **kwargs,
        )
        return json.loads(text or "{}")

    def fetch_weather_answer(self, location_query: str) -> str:
        answer, _records = self.live_gateway.fetch_weather_answer(location_query)
        return answer

    def fetch_exchange_rate_answer(self, base_currency: str, quote_currency: str) -> str:
        answer, _records = self.live_gateway.fetch_exchange_rate_answer(base_currency, quote_currency)
        return answer

    def fetch_exchange_rate_answer_yahoo(self, base_currency: str, quote_currency: str) -> str:
        answer, _records = self.live_gateway.fetch_exchange_rate_answer_yahoo(base_currency, quote_currency)
        return answer

    def fetch_exchange_rate_answer_open_er(self, base_currency: str, quote_currency: str) -> str:
        answer, _records = self.live_gateway.fetch_exchange_rate_answer_open_er(base_currency, quote_currency)
        return answer

    def fetch_crypto_price_answer(self, crypto_id: str) -> str:
        answer, _records = self.live_gateway.fetch_crypto_price_answer(crypto_id)
        return answer

    def fetch_stock_price_answer(self, stock_symbol: str) -> str:
        answer, _records = self.live_gateway.fetch_stock_price_answer(stock_symbol)
        return answer

    def fetch_news_answer(self, query: str, limit: int = 3) -> str:
        answer, _records = self.live_gateway.fetch_news_answer(query, limit=limit)
        return answer

    def fetch_current_fact_answer(self, query: str, limit: int = 3) -> str:
        answer, _records = self.live_gateway.fetch_current_fact_answer(query, limit=limit)
        return answer

    def ask_codex_with_image(self, chat_id: int, image_path: Path, caption: str, message: Optional[dict] = None) -> str:
        return _ask_codex_with_image_service(
            self,
            chat_id,
            image_path,
            caption,
            message=message,
            default_image_prompt=DEFAULT_IMAGE_PROMPT,
            build_prompt_func=build_prompt,
            normalize_whitespace_func=normalize_whitespace,
            truncate_text_func=truncate_text,
        )

    def ask_codex_with_document(
        self,
        chat_id: int,
        document_path: Path,
        document: dict,
        caption: str,
        file_excerpt: str,
        message: Optional[dict] = None,
    ) -> str:
        return _ask_codex_with_document_service(
            self,
            chat_id,
            document_path,
            document,
            caption,
            file_excerpt,
            message=message,
            build_prompt_func=build_prompt,
            format_file_size_func=format_file_size,
            normalize_whitespace_func=normalize_whitespace,
            truncate_text_func=truncate_text,
        )

    def run_codex(self, prompt: str, image_path: Optional[Path] = None, sandbox_mode: Optional[str] = None, approval_policy: Optional[str] = None, json_output: bool = False, postprocess: bool = True) -> str:
        return self.js_enterprise.run(
            prompt,
            image_path=image_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            json_output=json_output,
            postprocess=postprocess,
        )

    def run_codex_with_progress(
        self,
        chat_id: int,
        prompt: str,
        *,
        initial_status: str,
        status_message_id: Optional[int] = None,
        image_path: Optional[Path] = None,
        sandbox_mode: Optional[str] = None,
        approval_policy: Optional[str] = None,
        json_output: bool = False,
        postprocess: bool = True,
        timeout_seconds: Optional[int] = None,
        progress_style: str = "jarvis",
        replace_status_with_answer: bool = False,
        show_status_message: bool = True,
        target_label: str = "",
        delivery_chat_id: Optional[int] = None,
        request_trace_id: str = "",
        task_kind: str = "",
        route_kind: str = "",
        persona: str = "",
        request_kind: str = "",
        user_id: Optional[int] = None,
        message_id: Optional[int] = None,
        summary: str = "",
    ) -> str:
        return self.js_enterprise.run_with_progress(
            chat_id=chat_id,
            prompt=prompt,
            initial_status=initial_status,
            status_message_id=status_message_id,
            image_path=image_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            json_output=json_output,
            postprocess=postprocess,
            timeout_seconds=timeout_seconds,
            progress_style=progress_style,
            replace_status_with_answer=replace_status_with_answer,
            show_status_message=show_status_message,
            target_label=target_label,
            delivery_chat_id=delivery_chat_id,
            request_trace_id=request_trace_id,
            task_kind=task_kind,
            route_kind=route_kind,
            persona=persona,
            request_kind=request_kind,
            user_id=user_id,
            message_id=message_id,
            summary=summary,
        )

    def _update_progress_status(
        self,
        chat_id: int,
        status_message_id: Optional[int],
        initial_status: str,
        elapsed_seconds: int,
        phase_index: int,
        progress_style: str = "jarvis",
        target_label: str = "",
    ) -> None:
        if status_message_id is None:
            return
        status_text = build_progress_status(initial_status, elapsed_seconds, phase_index, progress_style, target_label)
        self.edit_status_message(chat_id, status_message_id, status_text)

    def _finish_progress_status(
        self,
        chat_id: int,
        status_message_id: Optional[int],
        initial_status: str,
        answer: str,
        progress_style: str = "jarvis",
        replace_status_with_answer: bool = False,
        target_label: str = "",
    ) -> None:
        if status_message_id is None:
            return
        if replace_status_with_answer and answer and answer not in {JARVIS_OFFLINE_TEXT, JARVIS_NETWORK_ERROR_TEXT}:
            self.edit_status_message(chat_id, status_message_id, answer)
            self.mark_answer_delivered_via_status(chat_id)
            return
        if progress_style == "enterprise":
            if answer in {JARVIS_OFFLINE_TEXT, JARVIS_NETWORK_ERROR_TEXT}:
                status_text = (
                    f"{initial_status}\n\n"
                    "✖ Enterprise сейчас недоступен.\n"
                    "Похоже, движок не поднялся или пропала сеть до внешнего сервиса.\n"
                    "Нужен рабочий маршрут, а не повтор сырой ошибки."
                )
            elif answer == UPGRADE_TIMEOUT_TEXT or answer.startswith("Слишком долгий ответ."):
                status_text = (
                    f"{initial_status}\n\n"
                    "⌛ Время вышло.\n"
                    "Задача всё ещё живая, но лимит ожидания уже кончился.\n"
                    "Если нужно, можно дожать её более узким заходом."
                )
            elif answer.startswith(UPGRADE_FAILED_TEXT) or answer.startswith("Ошибка Enterprise Core:"):
                status_text = (
                    f"{initial_status}\n\n"
                    "⚠ Выполнение завершилось с ошибкой.\n"
                    "Я не замял это под ковёр, детали уже в ответе ниже.\n"
                    "Это реальный сбой, а не ложная тревога."
                )
            else:
                status_text = (
                    f"{initial_status}\n\n"
                    "✔ Готово.\n"
                    "Задача дожата.\n"
                    "Результат готов к просмотру."
                )
        else:
            if answer in {JARVIS_OFFLINE_TEXT, JARVIS_NETWORK_ERROR_TEXT}:
                status_text = (
                    f"{initial_status}\n\n"
                    "✖ Jarvis сейчас не отвечает как надо.\n"
                    "Проблема либо в запуске, либо в сети до внешнего сервиса."
                )
            elif answer == UPGRADE_TIMEOUT_TEXT or answer.startswith("Слишком долгий ответ."):
                status_text = (
                    f"{initial_status}\n\n"
                    "⌛ Я упёрся во временной лимит.\n"
                    "Но мысль не потерял, просто задачу лучше сузить."
                )
            elif answer.startswith(UPGRADE_FAILED_TEXT) or answer.startswith("Ошибка Enterprise Core:"):
                status_text = (
                    f"{initial_status}\n\n"
                    "⚠ Не всё пошло гладко.\n"
                    "Произошёл реальный сбой, детали уже есть ниже."
                )
            else:
                status_text = (
                    f"{initial_status}\n\n"
                    "✔ Всё готово.\n"
                    "Ответ собран."
                )
        self.edit_status_message(chat_id, status_message_id, status_text)

    def run_codex_short(self, prompt: str, timeout_seconds: int = 35) -> str:
        command = self.build_codex_command(sandbox_mode="read-only", approval_policy="never")
        stdin_command = command + ["-"]
        sandbox_mode = "read-only"
        approval_policy = "never"
        try:
            with HeartbeatGuard(self):
                result = subprocess.run(
                    stdin_command,
                    capture_output=True,
                    text=True,
                    input=prompt,
                    timeout=max(10, timeout_seconds),
                    env=build_subprocess_env(),
                )
        except (subprocess.TimeoutExpired, OSError) as error:
            log(f"short codex failed: {shorten_for_log(str(error))}")
            return build_codex_failure_answer(
                str(error),
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
            )
        stdout = normalize_whitespace(result.stdout or "")
        stderr = normalize_whitespace(result.stderr or "")
        if result.returncode != 0:
            details = stderr or stdout or f"Enterprise Core завершился с кодом {result.returncode} без текста ошибки."
            log(f"short codex error code={result.returncode} stderr={shorten_for_log(details)}")
            return build_codex_failure_answer(
                details,
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
            )
        return extract_codex_text_response(stdout)

    def cleanup_voice_transcript_with_ai(self, chat_id: int, transcript: str) -> str:
        cleaned = normalize_whitespace(transcript)
        if not should_attempt_voice_ai_cleanup(cleaned):
            return cleaned
        context_terms = ", ".join(self.state.get_voice_prompt_terms(chat_id, limit=28))
        prompt = _build_voice_cleanup_prompt(cleaned, context_terms=context_terms)
        fixed = extract_codex_text_response(
            self.run_codex(
                prompt,
                sandbox_mode="read-only",
                approval_policy="never",
                postprocess=False,
            )
        )
        fixed = normalize_whitespace(fixed)
        if not fixed or fixed == cleaned:
            return cleaned
        if is_term_only_voice_cleanup(cleaned, fixed, context_terms) or is_safe_voice_cleanup(cleaned, fixed):
            return fixed
        return cleaned

    def transcribe_voice_with_ai(self, source_path: Path, chat_id: int = 0) -> str:
        transcript = ""
        if self.config.stt_backend in {"openai", "ai"} and self.config.openai_api_key:
            transcript = self._transcribe_voice_with_openai(source_path, chat_id=chat_id)
        else:
            transcript = self._transcribe_voice_offline(source_path, chat_id=chat_id)
        if not transcript:
            return ""
        try:
            file_size = int(source_path.stat().st_size)
        except OSError:
            file_size = 0
        if file_size and file_size <= 96_000:
            return transcript
        improved = self.cleanup_voice_transcript_with_ai(chat_id, transcript)
        if improved != transcript:
            log(f"voice transcript improved chat={chat_id} old={shorten_for_log(transcript)} new={shorten_for_log(improved)}")
        return improved

    def _transcribe_voice_with_openai(self, source_path: Path, chat_id: int = 0) -> str:
        endpoint = f"{self.config.openai_base_url}/audio/transcriptions"
        upload_name = source_path.name
        suffix = source_path.suffix.lower()
        if suffix == ".oga":
            upload_name = f"{source_path.stem}.ogg"
        mime_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
        if suffix in {".oga", ".ogg"}:
            mime_type = "audio/ogg"
        data = {
            "model": self.config.audio_transcribe_model,
            "language": self.config.stt_language,
            "prompt": self.build_voice_initial_prompt(chat_id, strict_trigger=False),
            "temperature": "0",
        }
        try:
            with HeartbeatGuard(self):
                with source_path.open("rb") as audio_handle:
                    response = self.session.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                        data=data,
                        files={"file": (upload_name, audio_handle, mime_type)},
                        timeout=(30, max(self.config.codex_timeout, 300)),
                    )
        except RequestException as error:
            log(f"voice transcription request failed: {shorten_for_log(str(error))}")
            return ""
        if not response.ok:
            details = normalize_whitespace(response.text or response.reason or "")
            log(f"voice transcription http_error status={response.status_code} details={shorten_for_log(details)}")
            return ""
        transcript = ""
        try:
            payload = response.json()
        except ValueError:
            transcript = normalize_whitespace(response.text or "")
        else:
            if isinstance(payload, dict):
                transcript = normalize_whitespace(str(payload.get("text") or ""))
        if not transcript:
            log("voice transcription returned empty text")
            return ""
        return transcript

    def _transcribe_voice_offline(self, source_path: Path, chat_id: int = 0) -> str:
        del chat_id
        model_name = (self.config.audio_transcribe_model or "").strip()
        if model_name.startswith("gpt-") or not model_name:
            try:
                file_size = int(source_path.stat().st_size)
            except OSError:
                file_size = 0
            model_name = "tiny" if file_size and file_size <= 160_000 else "small"
        log(f"offline voice transcription start model={model_name} file={source_path.name}")
        try:
            model = getattr(self, "_offline_whisper_model", None)
            current_name = getattr(self, "_offline_whisper_model_name", "")
            if model is None or current_name != model_name:
                from faster_whisper import WhisperModel

                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                self._offline_whisper_model = model
                self._offline_whisper_model_name = model_name
            segments, _info = model.transcribe(
                str(source_path),
                language=(self.config.stt_language or "ru"),
                vad_filter=True,
                condition_on_previous_text=False,
            )
        except Exception as error:
            log(f"offline voice transcription failed model={model_name}: {shorten_for_log(str(error))}")
            return ""
        parts = [normalize_whitespace(getattr(segment, "text", "")) for segment in segments]
        transcript = normalize_whitespace(" ".join(part for part in parts if part))
        if not transcript:
            log("offline voice transcription returned empty text")
            return ""
        log(f"offline voice transcription done model={model_name} text={shorten_for_log(transcript)}")
        return transcript

    def send_chat_action(self, chat_id: int, action: str) -> None:
        try:
            self.telegram_api("sendChatAction", data={"chat_id": chat_id, "action": action})
        except RequestException as error:
            log(f"failed to send chat action chat={chat_id}: {error}")

    def safe_send_status(self, chat_id: int, text: str) -> None:
        self.safe_send_text(chat_id, text)

    def fit_single_telegram_message(self, text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
        cleaned = text or ""
        if len(cleaned) <= limit:
            return cleaned
        truncation_note = "\n\n[сообщение обрезано под лимит Telegram]"
        cutoff = max(0, limit - len(truncation_note))
        candidate = cleaned[:cutoff].rstrip()
        split_at = max(candidate.rfind("\n\n"), candidate.rfind("\n"))
        if split_at >= max(0, cutoff - 800):
            candidate = candidate[:split_at].rstrip()
        return (candidate or cleaned[:cutoff]).rstrip() + truncation_note

    def split_console_stream_chunks(self, text: str, limit: int = CONSOLE_STREAM_CHUNK_LIMIT) -> List[str]:
        raw = (text or "").replace("\r", "")
        if not raw:
            return []
        chunks: List[str] = []
        remaining = raw
        bounded_limit = max(256, min(limit, TELEGRAM_TEXT_LIMIT - 64))
        while remaining:
            if len(remaining) <= bounded_limit:
                chunks.append(remaining.rstrip("\n"))
                break
            split_at = remaining.rfind("\n", 0, bounded_limit)
            if split_at < bounded_limit // 3:
                split_at = bounded_limit
            chunk = remaining[:split_at].rstrip("\n")
            if chunk:
                chunks.append(chunk)
            remaining = remaining[split_at:].lstrip("\n")
        return [chunk for chunk in chunks if chunk]

    def send_console_stream_chunks(
        self,
        chat_id: int,
        command: str,
        text: str,
        *,
        include_header: bool = True,
        reply_to_message_id: Optional[int] = None,
    ) -> int:
        total_sent = 0
        for index, chunk in enumerate(self.split_console_stream_chunks(text)):
            if include_header and index == 0:
                body = f"Enterprise Core | console\n$ {command}\n\n{chunk}"
            else:
                body = chunk
            rendered = f"<pre>{html.escape(body)}</pre>"
            payload = {"chat_id": chat_id, "text": rendered, "parse_mode": "HTML"}
            if reply_to_message_id is not None:
                payload["reply_to_message_id"] = int(reply_to_message_id)
            self.telegram_api("sendMessage", data=payload)
            total_sent += len(chunk)
        return total_sent

    def send_enterprise_stream_chunks(
        self,
        chat_id: int,
        title: str,
        text: str,
        *,
        include_header: bool = True,
        reply_to_message_id: Optional[int] = None,
    ) -> int:
        total_sent = 0
        for index, chunk in enumerate(self.split_console_stream_chunks(text)):
            if include_header and index == 0:
                body = f"Enterprise Core\n{title}\n\n{chunk}"
            else:
                body = chunk
            rendered = f"<pre>{html.escape(body)}</pre>"
            payload = {"chat_id": chat_id, "text": rendered, "parse_mode": "HTML"}
            if reply_to_message_id is not None:
                payload["reply_to_message_id"] = int(reply_to_message_id)
            self.telegram_api("sendMessage", data=payload)
            total_sent += len(chunk)
        return total_sent

    def format_console_stream_entry(self, entry: Dict[str, object]) -> str:
        kind = str(entry.get("kind") or "").strip().lower()
        allowed_kinds = {"assistant_text", "codex_json"}
        if kind not in allowed_kinds:
            return ""
        if kind == "assistant_text":
            text = str(entry.get("text") or "").strip()
            if not text:
                return ""
            state = str(entry.get("state") or "").strip().lower()
            if state != "completed":
                return ""
            return f"# {text}"
        if kind == "codex_json":
            payload = entry.get("payload") or {}
            if not isinstance(payload, dict):
                return ""
            event_type = str(payload.get("type") or "").strip()
            if event_type != "item.completed":
                return ""
            item = payload.get("item") or {}
            item_type = str(item.get("type") or "").strip()
            allowed_item_types = {"exec_command", "command_execution", "agent_message"}
            if item_type not in allowed_item_types:
                return ""
            if item_type in {"exec_command", "command_execution"}:
                command = normalize_whitespace(str(item.get("command") or item.get("title") or ""))
                return f"$ {truncate_text(command, 220)}" if command else ""
            if item_type == "agent_message":
                return ""
            return ""
        return ""

    def send_console_stream_copy_document(
        self,
        chat_id: int,
        command: str,
        stream_entries: List[Dict[str, object]],
        *,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        if not stream_entries:
            return
        raw = "\n".join(json.dumps(item, ensure_ascii=False) for item in stream_entries)
        if not raw.strip():
            return
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", prefix="enterprise_stream_", delete=False) as handle:
                handle.write(raw)
                temp_path = Path(handle.name)
            caption = truncate_text(f"Копия stream-ленты Enterprise Core\n$ {command}", 900)
            with temp_path.open("rb") as handle:
                response = self.session.post(
                    f"{self.config.base_url}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption, **({"reply_to_message_id": int(reply_to_message_id)} if reply_to_message_id is not None else {})},
                    files={"document": (temp_path.name, handle, "application/json")},
                    timeout=180,
                )
            ensure_telegram_ok(response)
        finally:
            if temp_path is not None:
                cleanup_temp_file(temp_path)

    def send_console_output_document(
        self,
        chat_id: int,
        command: str,
        output_text: str,
        *,
        exit_code: int,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        raw = (output_text or "").replace("\r", "")
        if len(raw) < CONSOLE_DOCUMENT_THRESHOLD:
            return
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".log", prefix="console_", delete=False) as handle:
                handle.write(raw)
                temp_path = Path(handle.name)
            caption = truncate_text(f"Полный лог консоли\n$ {command}\nКод выхода: {exit_code}", 900)
            with temp_path.open("rb") as handle:
                response = self.session.post(
                    f"{self.config.base_url}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption, **({"reply_to_message_id": int(reply_to_message_id)} if reply_to_message_id is not None else {})},
                    files={"document": (temp_path.name, handle, "text/plain")},
                    timeout=180,
                )
            ensure_telegram_ok(response)
        finally:
            if temp_path is not None:
                cleanup_temp_file(temp_path)

    def send_status_message(self, chat_id: int, text: str) -> Optional[int]:
        try:
            payload = self.telegram_api("sendMessage", data={"chat_id": chat_id, "text": self.fit_single_telegram_message(text)})
            result = payload.get("result") or {}
            message_id = result.get("message_id")
            return int(message_id) if message_id is not None else None
        except RequestException as error:
            log(f"failed to send status message chat={chat_id}: {error}")
            return None

    def edit_status_message(self, chat_id: int, message_id: int, text: str) -> bool:
        chunks = split_long_message(text)
        primary_text = chunks[0] if chunks else ""
        try:
            self.telegram_api(
                "editMessageText",
                data={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": self.fit_single_telegram_message(primary_text),
                },
            )
            for extra_chunk in chunks[1:]:
                self.safe_send_text(chat_id, extra_chunk)
            return True
        except RequestException as error:
            if "message is not modified" in str(error).lower():
                return True
            log(f"failed to edit status message chat={chat_id} message_id={message_id}: {error}")
            return False

    def send_document(self, chat_id: int, file_path: Path, caption: str = "") -> None:
        with file_path.open("rb") as handle:
            response = self.session.post(
                f"{self.config.base_url}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (file_path.name, handle, "application/octet-stream")},
                timeout=180,
            )
        ensure_telegram_ok(response)

    def send_inline_message(self, chat_id: int, text: str, reply_markup: dict) -> Optional[int]:
        payload = self.telegram_api(
            "sendMessage",
            data={"chat_id": chat_id, "text": self.fit_single_telegram_message(text), "reply_markup": json.dumps(reply_markup)},
        )
        result = payload.get("result") or {}
        message_id = result.get("message_id")
        return int(message_id) if message_id is not None else None

    def edit_inline_message(self, chat_id: int, message_id: int, text: str, reply_markup: dict) -> None:
        try:
            self.telegram_api(
                "editMessageText",
                data={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": self.fit_single_telegram_message(text),
                    "reply_markup": json.dumps(reply_markup),
                },
            )
        except RequestException as error:
            if "message is not modified" in str(error).lower():
                return
            raise

    def answer_callback_query(self, callback_query_id: str) -> None:
        self.telegram_api("answerCallbackQuery", data={"callback_query_id": callback_query_id})

    def send_message_with_html_fallback(self, payload: dict) -> None:
        html_payload = dict(payload)
        html_payload["parse_mode"] = "HTML"
        try:
            self.telegram_api("sendMessage", data=html_payload)
            return
        except RequestException as error:
            if not is_telegram_parse_mode_error(error):
                raise
        self.telegram_api("sendMessage", data=payload)

    def send_reply_message(self, chat_id: int, text: str, reply_to_message_id: int, parse_mode: str = "") -> None:
        for chunk in split_long_message(text):
            payload = {"chat_id": chat_id, "text": chunk, "reply_to_message_id": reply_to_message_id}
            if parse_mode:
                payload["parse_mode"] = parse_mode
                response = self.session.post(
                    f"{self.config.base_url}/sendMessage",
                    data=payload,
                    timeout=TELEGRAM_TIMEOUT,
                )
                ensure_telegram_ok(response)
            else:
                self.send_message_with_html_fallback(payload)

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        response = self.session.post(
            f"{self.config.base_url}/deleteMessage",
            data={"chat_id": chat_id, "message_id": message_id},
            timeout=TELEGRAM_TIMEOUT,
        )
        ensure_telegram_ok(response)
        return True

    def fix_grammar_text(self, text: str) -> str:
        prompt = _build_grammar_fix_prompt(text)
        return extract_codex_text_response(self.run_codex(prompt, postprocess=False))

    def run_owner_autofix_task(self, chat_id: int, message_id: Optional[int], original_text: str, author_name: str) -> None:
        if not message_id:
            return
        try:
            fixed_text = normalize_whitespace(self.fix_grammar_text(original_text))
            if not fixed_text or not is_meaningfully_corrected(original_text, fixed_text):
                return
            outgoing = f"{author_name}:\n{fixed_text}"
            self.send_reply_message(chat_id, outgoing, message_id)
            try:
                self.delete_message(chat_id, message_id)
            except RequestException as error:
                log(f"owner autofix delete failed chat={chat_id} message_id={message_id}: {error}")
        except RequestException as error:
            log(f"owner autofix telegram error chat={chat_id} message_id={message_id}: {error}")
        except Exception as error:
            log_exception(f"owner autofix failed chat={chat_id} message_id={message_id}", error, limit=8)

    def maybe_start_weekly_backup(self) -> None:
        now = time.time()
        if now < self.next_backup_check_ts:
            return
        self.next_backup_check_ts = now + 3600
        interval_seconds = self.config.backup_interval_days * 86400
        last_backup_raw = self.state.get_meta("last_backup_ts", "0")
        try:
            last_backup_ts = float(last_backup_raw or "0")
        except ValueError:
            last_backup_ts = 0.0
        if now - last_backup_ts < interval_seconds:
            return
        with self.backup_lock:
            if self.backup_in_progress:
                return
            self.backup_in_progress = True
        worker = Thread(target=self.run_scheduled_backup, daemon=True)
        worker.start()

    def run_scheduled_backup(self) -> None:
        try:
            with self.temp_workspace() as workspace:
                archive_path = self.create_backup_archive(workspace, full_project=True)
                part_paths = split_file_parts(archive_path, self.config.backup_part_size_mb * 1024 * 1024)
                total_parts = len(part_paths)
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for index, part_path in enumerate(part_paths, start=1):
                    caption = ""
                    if index == 1:
                        caption = f"Weekly backup {stamp}. Parts: {total_parts}"
                    self.send_document(self.config.backup_chat_id, part_path, caption=caption)
                self.state.set_meta("last_backup_ts", str(time.time()))
                log(f"weekly backup sent parts={total_parts}")
        except Exception as error:
            log_exception("weekly backup failed", error, limit=10)
        finally:
            with self.backup_lock:
                self.backup_in_progress = False

    def maybe_start_scheduled_reports(self) -> None:
        now = time.time()
        if now < self.next_report_check_ts:
            return
        self.next_report_check_ts = now + 3600
        worker = Thread(target=self.run_scheduled_reports, daemon=True)
        worker.start()

    def run_scheduled_reports(self) -> None:
        now = datetime.utcnow()
        try:
            self.maybe_send_daily_owner_digest(now)
            self.maybe_send_weekly_owner_report(now)
        except Exception as error:
            log_exception("scheduled reports failed", error, limit=10)

    def maybe_start_owner_chat_alerts(self) -> None:
        now = time.time()
        if now < self.next_owner_alert_check_ts:
            return
        self.next_owner_alert_check_ts = now + 300
        worker = Thread(target=self.run_owner_chat_alerts, daemon=True)
        worker.start()

    def run_owner_chat_alerts(self) -> None:
        try:
            now_ts = int(time.time())
            for chat_id in self.state.get_managed_group_chat_ids():
                alert_text = self.build_owner_chat_alert_text(chat_id, now_ts=now_ts)
                if not alert_text:
                    continue
                self.notify_owner(alert_text)
        except Exception as error:
            log_exception("owner chat alerts failed", error, limit=10)

    def build_owner_chat_alert_text(self, chat_id: int, now_ts: Optional[int] = None) -> str:
        current_ts = int(now_ts or time.time())
        rows = self.state.get_recent_chat_rows(chat_id, limit=80)
        if not rows:
            return ""
        recent_rows = [row for row in rows if int(row[0] or 0) >= current_ts - 3600]
        user_rows = [row for row in recent_rows if row[5] == "user"]
        if not user_rows:
            return ""
        user_count = len(user_rows)
        troublemaker_summary = render_chat_troublemaker_summary(recent_rows)
        trouble_detected = "явного провокатора не видно" not in troublemaker_summary.lower()
        activity_spike = user_count >= 25
        unanswered_questions = self.get_chat_unanswered_questions(chat_id, now_ts=current_ts, limit=3)
        newcomer_summary = self.get_chat_newcomer_summary(chat_id, now_ts=current_ts)
        suspect_summary = self.get_chat_suspect_summary(chat_id, now_ts=current_ts)
        unanswered_detected = bool(unanswered_questions)
        newcomer_detected = bool(newcomer_summary)
        suspect_detected = bool(suspect_summary)
        if not activity_spike and not trouble_detected and not unanswered_detected and not newcomer_detected and not suspect_detected:
            return ""
        alert_kind = (
            "conflict" if trouble_detected else
            "unanswered" if unanswered_detected else
            "suspect" if suspect_detected else
            "newcomer" if newcomer_detected else
            "activity"
        )
        cooldown_key = f"owner_alert:{alert_kind}:{chat_id}"
        last_sent_raw = self.state.get_meta(cooldown_key, "0")
        try:
            last_sent_ts = int(float(last_sent_raw or "0"))
        except ValueError:
            last_sent_ts = 0
        cooldown_seconds = 3600 if trouble_detected else 7200 if unanswered_detected else 10800 if suspect_detected else 14400 if newcomer_detected else 21600
        if current_ts - last_sent_ts < cooldown_seconds:
            return ""
        chat_title = self.state.get_chat_title(chat_id)
        top_counts: Dict[str, int] = {}
        highlights: List[str] = []
        for created_at, user_id, username, first_name, last_name, role, message_type, content in user_rows:
            actor = self._format_owner_actor_label(user_id, username or "", first_name or "", last_name or "", role)
            top_counts[actor] = top_counts.get(actor, 0) + 1
            if len(highlights) < 4 and message_type in {"text", "caption", "edited_text"}:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                highlights.append(f"- [{stamp}] {actor}: {truncate_text(normalize_whitespace(content or ''), 140)}")
        sorted_top_participants = sorted(top_counts.items(), key=lambda item: (-item[1], item[0]))[:4]
        lines = [
            f"OWNER ALERT • {truncate_text(chat_title, 80)}",
            f"Чат: {truncate_text(chat_title, 80)}",
            f"chat_id: {chat_id}",
            f"Сигнал: {'конфликт/шум' if trouble_detected else 'вопросы без ответа' if unanswered_detected else 'подозрительный участник' if suspect_detected else 'новый заметный участник' if newcomer_detected else 'всплеск активности'}",
            f"signal={'конфликт/шум' if trouble_detected else 'вопросы без ответа' if unanswered_detected else 'подозрительный участник' if suspect_detected else 'новый заметный участник' if newcomer_detected else 'всплеск активности'}",
            f"Сообщений пользователей за час: {user_count}",
            f"user_messages_last_hour={user_count}",
        ]
        if sorted_top_participants:
            lines.extend(["", "Кто активнее всего за последний час:"])
            lines.extend(
                f"- {name}: {count} сообщений" for name, count in sorted_top_participants
            )
        if trouble_detected:
            lines.extend(["", troublemaker_summary.replace("Кто гонит беса:", "Вероятные источники шума:")])
        if unanswered_questions:
            lines.extend(["", "Вопросы без ответа:", "unanswered_questions:"])
            lines.extend(f"- {item}" for item in unanswered_questions)
        if newcomer_summary:
            lines.extend(["", newcomer_summary])
        if suspect_summary:
            lines.extend(["", suspect_summary])
        if highlights:
            lines.extend(["", "Свежие реплики:"])
            lines.extend(highlights)
        self.state.set_meta(cooldown_key, str(current_ts))
        return "\n".join(lines)

    def _format_owner_actor_label(self, user_id: Optional[int], username: str, first_name: str, last_name: str, role: str) -> str:
        if role == "assistant":
            return "Jarvis"
        if is_owner_identity(user_id):
            display = " ".join(part for part in [first_name, last_name] if part).strip() or "Дмитрий"
            return f"{display} (owner)"
        display = " ".join(part for part in [first_name, last_name] if part).strip()
        if display and username:
            return f"{display} (@{username} id={user_id})"
        if display:
            return f"{display} id={user_id}" if user_id is not None else display
        if username:
            return f"@{username} id={user_id}" if user_id is not None else f"@{username}"
        return f"user_id={user_id}" if user_id is not None else "user"

    def get_chat_unanswered_questions(self, chat_id: int, now_ts: Optional[int] = None, limit: int = 3) -> List[str]:
        current_ts = int(now_ts or time.time())
        rows = self.state.get_recent_chat_rows(chat_id, limit=60)
        recent_rows = [row for row in rows if int(row[0] or 0) >= current_ts - 7200]
        unanswered: List[str] = []
        for index, row in enumerate(recent_rows):
            created_at, user_id, username, first_name, last_name, role, message_type, content = row
            if role != "user" or message_type not in {"text", "edited_text", "caption"}:
                continue
            text = normalize_whitespace(content or "")
            if "?" not in text:
                continue
            followup_rows = recent_rows[index + 1:index + 7]
            if any(followup[5] == "assistant" for followup in followup_rows):
                continue
            actor = self._format_owner_actor_label(user_id, username or "", first_name or "", last_name or "", role)
            stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
            unanswered.append(f"[{stamp}] {actor}: {truncate_text(text, 140)}")
            if len(unanswered) >= limit:
                break
        return unanswered

    def get_chat_newcomer_summary(self, chat_id: int, now_ts: Optional[int] = None) -> str:
        current_ts = int(now_ts or time.time())
        with self.state.db_lock:
            row = self.state.db.execute(
                """
                SELECT user_id, username, first_name, last_name, first_seen_at, last_seen_at
                FROM chat_participants
                WHERE chat_id = ? AND is_bot = 0
                  AND first_seen_at >= ?
                  AND last_seen_at >= ?
                ORDER BY last_seen_at DESC
                LIMIT 1
                """,
                (chat_id, current_ts - 86400, current_ts - 7200),
            ).fetchone()
        if not row:
            return ""
        label = self._format_owner_actor_label(row["user_id"], row["username"] or "", row["first_name"] or "", row["last_name"] or "", "user")
        first_seen = datetime.fromtimestamp(int(row["first_seen_at"] or 0)).strftime("%m-%d %H:%M") if row["first_seen_at"] else "--:--"
        return f"Новый заметный участник: {label}\nnewcomer_signal: {label}; first_seen={first_seen}"

    def get_chat_suspect_summary(self, chat_id: int, now_ts: Optional[int] = None) -> str:
        current_ts = int(now_ts or time.time())
        with self.state.db_lock:
            row = self.state.db.execute(
                """
                SELECT p.user_id, p.display_name, p.username, p.risk_flags_json, p.notes_summary, v.analysis_text
                FROM participant_chat_profiles p
                LEFT JOIN participant_visual_signals v
                  ON v.chat_id = p.chat_id AND v.user_id = p.user_id
                WHERE p.chat_id = ?
                  AND p.updated_at >= ?
                  AND (
                    p.risk_flags_json LIKE '%scam_risk%'
                    OR p.risk_flags_json LIKE '%likely_bot_like%'
                    OR p.risk_flags_json LIKE '%sexual_bait%'
                    OR p.risk_flags_json LIKE '%suspicious_visual%'
                  )
                ORDER BY p.updated_at DESC
                LIMIT 1
                """,
                (chat_id, current_ts - 21600),
            ).fetchone()
        if not row:
            return ""
        label = str(row["display_name"] or (f"@{row['username']}" if row["username"] else f"user_id={int(row['user_id'] or 0)}"))
        try:
            flags = ", ".join(json.loads(row["risk_flags_json"] or "[]")[:5]) or "none"
        except ValueError:
            flags = "none"
        analysis = truncate_text(normalize_visual_analysis_text(row["analysis_text"] or row["notes_summary"] or ""), 180)
        return f"Подозрительный участник: {label}\nsuspect_signal: {label}; flags={flags}; why={analysis}"

    def maybe_start_memory_refresh(self) -> None:
        now = time.time()
        if now < self.next_memory_refresh_check_ts:
            return
        self.next_memory_refresh_check_ts = now + DEFAULT_MEMORY_REFRESH_INTERVAL_SECONDS
        with self.memory_refresh_lock:
            if self.memory_refresh_in_progress:
                return
            self.memory_refresh_in_progress = True
        worker = Thread(target=self.run_memory_refresh, daemon=True)
        worker.start()

    def run_memory_refresh(self) -> None:
        try:
            for chat_id, last_event_id, new_events in self.state.get_chats_due_for_memory_refresh(limit=3):
                summary_done = self.refresh_ai_chat_summary(chat_id)
                relations_done = self.state.refresh_relation_memory(chat_id)
                users_done = self.refresh_ai_user_memory(chat_id)
                self.state.mark_memory_refresh(
                    chat_id,
                    last_event_id,
                    summary_refreshed=summary_done,
                    users_refreshed=users_done,
                )
                log(
                    f"memory refresh chat={chat_id} new_events={new_events} "
                    f"summary={'yes' if summary_done else 'no'} "
                    f"relations={'yes' if relations_done else 'no'} "
                    f"users={'yes' if users_done else 'no'}"
                )
        except Exception as error:
            log_exception("memory refresh failed", error, limit=10)
        finally:
            with self.memory_refresh_lock:
                self.memory_refresh_in_progress = False

    def maybe_run_auto_repair_loop(self) -> None:
        if not self.owner_autofix_enabled():
            return
        now = time.time()
        if now < self.next_auto_self_heal_check_ts:
            return
        self.next_auto_self_heal_check_ts = now + self.config.auto_self_heal_interval_seconds
        try:
            self.run_auto_repair_loop("periodic")
        except SystemExit:
            raise
        except Exception as error:
            log_exception("auto self-heal loop failed", error, limit=10)

    def refresh_world_state_registry(self, source: str = "runtime_tick", chat_id: Optional[int] = None) -> Dict[str, object]:
        return self.runtime_service.refresh_world_state_registry(self, source, chat_id)

    def recompute_drive_scores(self, operational_state: Optional[Dict[str, object]] = None) -> Dict[str, float]:
        return self.runtime_service.recompute_drive_scores(self, operational_state)

    def run_self_heal_cycle(self, source: str, auto_execute: bool = False) -> str:
        from services.self_heal_manager import run_self_heal_cycle

        return run_self_heal_cycle(self, source=source, auto_execute=auto_execute)

    def run_auto_repair_loop(self, source: str) -> str:
        from services.auto_repair_loop import run_auto_repair_loop

        return run_auto_repair_loop(self, source=source)

    def finalize_pending_auto_restart(self) -> str:
        from services.auto_repair_loop import finalize_pending_auto_restart

        return finalize_pending_auto_restart(self)

    def apply_persistent_pressures_to_route(self, route_decision: RouteDecision, user_text: str) -> RouteDecision:
        drive_map = {row["drive_name"]: float(row["score"] or 0) for row in self.state.get_drive_scores()}
        guardrails = list(route_decision.guardrails)
        if drive_map.get("uncertainty_pressure", 0.0) >= 40.0 and "heightened-uncertainty" not in guardrails:
            guardrails.append("heightened-uncertainty")
        if drive_map.get("runtime_risk_pressure", 0.0) >= 45.0 and "runtime-risk-attention" not in guardrails:
            guardrails.append("runtime-risk-attention")
        if drive_map.get("doc_sync_pressure", 0.0) >= 35.0 and "doc-sync-attention" not in guardrails:
            guardrails.append("doc-sync-attention")
        if detect_local_chat_query(user_text) and drive_map.get("stale_memory_pressure", 0.0) >= 35.0 and "stale-memory-attention" not in guardrails:
            guardrails.append("stale-memory-attention")
        return RouteDecision(
            persona=route_decision.persona,
            intent=route_decision.intent,
            chat_type=route_decision.chat_type,
            route_kind=route_decision.route_kind,
            source_label=route_decision.source_label,
            use_live=route_decision.use_live,
            use_web=route_decision.use_web,
            use_events=route_decision.use_events,
            use_database=route_decision.use_database,
            use_reply=route_decision.use_reply,
            use_workspace=route_decision.use_workspace,
            guardrails=tuple(dict.fromkeys(guardrails)),
        )

    def run_post_task_reflection(
        self,
        *,
        chat_id: Optional[int],
        user_id: Optional[int],
        route_decision: RouteDecision,
        user_text: str,
        report: SelfCheckReport,
        source: str,
    ) -> None:
        significant = route_decision.use_workspace or route_decision.use_live or route_decision.use_web or report.outcome != "ok" or detect_local_chat_query(user_text)
        if not significant:
            return
        observed_outcome = f"outcome={report.outcome}; flags={', '.join(report.flags) or '-'}; basis={', '.join(report.observed_basis) or '-'}"
        uncertainty = ", ".join(report.uncertain_points) if report.uncertain_points else "нет явной неопределённости"
        lesson_parts: List[str] = []
        recommended_updates: List[str] = []
        applied_updates: List[str] = []
        if route_decision.use_live or route_decision.use_web:
            lesson_parts.append("для внешних данных сохранять источник и freshness-marker")
            recommended_updates.append("держать live honesty contract")
            self.state.mark_skill_used("live_verification", report.outcome == "ok")
        if route_decision.use_workspace:
            lesson_parts.append("workspace-ответы подтверждать только реальным runtime/tool execution")
            recommended_updates.append("сохранять workspace grounding")
            self.state.mark_skill_used("runtime_triage", report.outcome == "ok")
        if detect_local_chat_query(user_text):
            lesson_parts.append("локальные запросы про чат должны опираться на chat/relation/user memory, а не на web")
            applied_updates.append("local chat grounding confirmed")
            self.state.mark_skill_used("chat_grounding", report.outcome == "ok")
        if "doc-sync-attention" in route_decision.guardrails:
            recommended_updates.append("проверить sync docs/runtime_backups после правок")
            self.state.mark_skill_used("doc_sync", report.outcome == "ok")
        if "runtime-risk-attention" in route_decision.guardrails:
            lesson_parts.append("при высоком runtime-risk усиливать честные ограничения и diagnostics")
        if not lesson_parts:
            lesson_parts.append("текущий route сработал без отдельного урока")
        self.state.record_reflection(
            chat_id=chat_id,
            user_id=user_id,
            route_kind=route_decision.route_kind,
            task_summary=user_text,
            observed_outcome=observed_outcome,
            uncertainty=uncertainty,
            lesson="; ".join(lesson_parts),
            recommended_updates="; ".join(recommended_updates) or "нет",
            applied_updates="; ".join(applied_updates) or "нет",
            tags=f"{source},{route_decision.persona},{route_decision.intent}",
        )
        self.state.record_autobiographical_event(
            category="reflection",
            event_type=source,
            chat_id=chat_id,
            user_id=user_id,
            route_kind=route_decision.route_kind,
            title=truncate_text(user_text, 140),
            details=f"{observed_outcome}. lesson={'; '.join(lesson_parts)}. uncertainty={uncertainty}",
            status=report.outcome,
            importance=35 if report.outcome == "ok" else 65,
            open_state="closed",
            tags=f"{route_decision.persona},{route_decision.intent},{source}",
            observed_payload={"flags": report.flags, "observed_basis": report.observed_basis, "uncertain_points": report.uncertain_points},
        )

    def refresh_ai_chat_summary(self, chat_id: int) -> bool:
        return self.memory_service.refresh_ai_chat_summary(self, chat_id)

    def refresh_ai_user_memory(self, chat_id: int) -> bool:
        return self.memory_service.refresh_ai_user_memory(self, chat_id)

    def maybe_send_daily_owner_digest(self, now: datetime) -> None:
        if now.hour < self.config.owner_daily_digest_hour_utc:
            return
        target_day = datetime.utcfromtimestamp(time.time() - 86400).strftime("%Y-%m-%d")
        if self.state.get_meta("owner_daily_digest_sent", "") == target_day:
            return
        report = self.render_global_digest_text(target_day)
        self.notify_owner(report)
        self.state.set_meta("owner_daily_digest_sent", target_day)
        log(f"daily owner digest sent day={target_day}")

    def maybe_send_weekly_owner_report(self, now: datetime) -> None:
        if now.weekday() != self.config.owner_weekly_digest_weekday_utc:
            return
        if now.hour < self.config.owner_daily_digest_hour_utc:
            return
        iso_year, iso_week, _iso_weekday = now.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        if self.state.get_meta("owner_weekly_report_sent", "") == week_key:
            return
        report = self.render_weekly_owner_report_text(now)
        self.notify_owner(report)
        self.state.set_meta("owner_weekly_report_sent", week_key)
        log(f"weekly owner report sent week={week_key}")

    def render_global_digest_text(self, target_day: str) -> str:
        chat_ids = self.state.get_managed_group_chat_ids()
        if not chat_ids:
            return f"Daily digest за {target_day}\n\nГрупповые чаты для сводки пока не найдены."
        total_events = 0
        total_user_messages = 0
        chat_stats: List[Tuple[str, int, int, str]] = []
        user_counts: Dict[str, int] = {}
        highlights: List[str] = []
        for chat_id in chat_ids:
            day_value, rows = self.state.get_daily_summary_context(chat_id, target_day)
            if not rows:
                continue
            group_events = len(rows)
            group_user_messages = sum(1 for row in rows if row[5] == "user")
            total_events += group_events
            total_user_messages += group_user_messages
            chat_title = self.state.get_chat_title(chat_id)
            flags: List[str] = []
            troublemaker_summary = render_chat_troublemaker_summary(rows)
            if "явного провокатора не видно" not in troublemaker_summary.lower():
                flags.append("conflict")
            if self.get_chat_unanswered_questions(chat_id, now_ts=int(time.time()), limit=1):
                flags.append("unanswered")
            if self.get_chat_newcomer_summary(chat_id, now_ts=int(time.time())):
                flags.append("newcomer")
            chat_stats.append((truncate_text(chat_title, 80), group_events, group_user_messages, ",".join(flags) or "-"))
            for created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
                if role != "user":
                    continue
                actor = build_actor_name(user_id, username or "", first_name or "", last_name or "", role)
                user_counts[actor] = user_counts.get(actor, 0) + 1
                if len(highlights) < 8 and message_type in {"text", "caption", "edited_text", "photo", "voice", "document"}:
                    stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                    highlights.append(f"[chat {chat_id} {stamp}] {actor}: {truncate_text(content, 120)}")
        if total_events == 0:
            return f"Daily digest за {target_day}\n\nЗа этот день по группам событий не нашлось."
        lines = [
            f"DAILY DIGEST • {target_day}",
            f"Групп с активностью: {len(chat_stats)}",
            f"Всего событий: {total_events}",
            f"Сообщений пользователей: {total_user_messages}",
        ]
        top_chats = sorted(chat_stats, key=lambda item: (-item[1], item[0]))[:5]
        if top_chats:
            lines.extend(["", "Топ чатов по активности:"])
            lines.extend(
                f"- {chat_title}: событий {events}, user-msg {user_messages}, flags={flags}"
                for chat_title, events, user_messages, flags in top_chats
            )
        top_users = sorted(user_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        if top_users:
            lines.extend(["", "Топ участников по сообщениям:"])
            lines.extend(f"- {name}: {count}" for name, count in top_users)
        if highlights:
            lines.extend(["", "Ключевые куски дня:"])
            lines.extend(f"- {item}" for item in highlights)
        return "\n".join(lines)

    def render_weekly_owner_report_text(self, now: datetime) -> str:
        lines = [
            f"WEEKLY OWNER REPORT • {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            self.render_owner_report_text(OWNER_USER_ID),
        ]
        day_labels: List[str] = []
        for delta in range(1, 8):
            target_day = datetime.utcfromtimestamp(time.time() - delta * 86400).strftime("%Y-%m-%d")
            digest = self.render_global_digest_text(target_day)
            first_line = digest.splitlines()[0] if digest else f"Daily digest за {target_day}"
            summary_line = next((line for line in digest.splitlines() if line.startswith("Всего событий:")), "Всего событий: 0")
            day_labels.append(f"- {first_line} | {summary_line}")
        if day_labels:
            lines.extend(["", "Последние 7 дней:"])
            lines.extend(day_labels)
        return "\n\n".join(lines)

    def create_backup_archive(self, workspace: Path, full_project: bool = True) -> Path:
        archive_name = f"jarvis_backup_{datetime.now().strftime('%Y-%m-%d')}.zip"
        archive_path = workspace / archive_name
        base = self.script_path.parent
        exclude_names = {"__pycache__", ".git", ".venv", "venv"}
        exclude_files = {self.config.lock_path, archive_name}
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in base.rglob('*'):
                rel = file_path.relative_to(base)
                if any(part in exclude_names for part in rel.parts):
                    continue
                if file_path.name in exclude_files:
                    continue
                if file_path.suffix.lower() in {".pyc", ".pyo"}:
                    continue
                if not full_project and not should_include_code_backup_file(file_path):
                    continue
                if file_path.is_file():
                    zf.write(file_path, rel.as_posix())
        return archive_path

    def safe_send_text(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
        normalized_text = normalize_whitespace(text)
        if normalized_text:
            now = time.time()
            with self.outgoing_dedupe_lock:
                recent = self.recent_outgoing_messages.get(chat_id)
                if recent and recent[0] == normalized_text and now - recent[1] <= 12:
                    log(f"duplicate outgoing suppressed chat={chat_id} text={shorten_for_log(normalized_text)}")
                    return
                self.recent_outgoing_messages[chat_id] = (normalized_text, now)
        for chunk in split_long_message(text):
            try:
                payload = {"chat_id": chat_id, "text": chunk}
                if reply_to_message_id is not None:
                    payload["reply_to_message_id"] = int(reply_to_message_id)
                self.send_message_with_html_fallback(payload)
            except RequestException as error:
                log(f"failed to send message chat={chat_id}: {error}")
                break

    def temp_workspace(self):
        return TemporaryWorkspace(self.config.tmp_dir)


class TemporaryWorkspace:
    def __init__(self, base_dir: Optional[Path]) -> None:
        self.base_dir = base_dir
        self.temp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory(dir=str(self.base_dir) if self.base_dir else None)
        self.path = Path(self.temp_dir.name)
        return self.path

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self.path is not None:
            for item in self.path.iterdir():
                cleanup_temp_file(item)
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


class HeartbeatGuard:
    def __init__(self, bridge: "TelegramBridge", interval_seconds: int = 10) -> None:
        self.bridge = bridge
        self.interval_seconds = max(3, interval_seconds)
        self._stop = Event()
        self._thread: Optional[Thread] = None

    def __enter__(self):
        def worker() -> None:
            while not self._stop.wait(self.interval_seconds):
                try:
                    self.bridge.beat_heartbeat()
                except Exception as error:
                    log_exception("heartbeat guard failed", error, limit=4)

        self._thread = Thread(target=worker, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


class ProgressStatusGuard:
    def __init__(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        status_message_id: Optional[int],
        initial_status: str,
        progress_style: str = "jarvis",
        interval_seconds: int = CODEX_PROGRESS_UPDATE_SECONDS,
    ) -> None:
        self.bridge = bridge
        self.chat_id = chat_id
        self.status_message_id = status_message_id
        self.initial_status = initial_status
        self.progress_style = progress_style
        self.interval_seconds = max(3, interval_seconds)
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self._started_at = 0.0

    def __enter__(self):
        if self.status_message_id is None:
            return self
        self._started_at = time.perf_counter()

        def worker() -> None:
            phase_index = 0
            while not self._stop.wait(self.interval_seconds):
                elapsed = int(max(1, time.perf_counter() - self._started_at))
                try:
                    self.bridge.beat_heartbeat()
                    self.bridge.send_chat_action(self.chat_id, "typing")
                    self.bridge._update_progress_status(
                        self.chat_id,
                        self.status_message_id,
                        self.initial_status,
                        elapsed,
                        phase_index,
                        self.progress_style,
                    )
                except Exception as error:
                    log_exception("progress guard failed", error, limit=4)
                phase_index += 1

        self._thread = Thread(target=worker, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def should_include_code_backup_file(path: Path) -> bool:
    return _should_include_code_backup_file(path)


def split_file_parts(file_path: Path, part_size_bytes: int) -> List[Path]:
    return _split_file_parts(file_path, part_size_bytes)


def read_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    return _read_int_env(name, default, minimum, maximum)


def read_bool_env(name: str, default: bool) -> bool:
    return _read_bool_env(name, default)


def prepare_tmp_dir(raw_path: str) -> Optional[Path]:
    return _prepare_tmp_dir(raw_path)


def normalize_mode(raw_mode: Optional[str]) -> str:
    return _resolve_prompt_profile_name(raw_mode or DEFAULT_MODE_NAME, DEFAULT_MODE_NAME)


def parse_mode_command(text: str) -> Optional[str]:
    return _parse_mode_command(text, set(MODE_PROMPTS), DEFAULT_MODE_NAME)


def parse_upgrade_command(text: str) -> Optional[str]:
    return _parse_upgrade_command(text)


def parse_remember_command(text: str) -> Optional[str]:
    return _parse_remember_command(text)


def parse_recall_command(text: str) -> Optional[str]:
    return _parse_recall_command(text)


def parse_search_command(text: str) -> Optional[str]:
    return _parse_search_command(text)


def parse_sd_list_command(text: str) -> Optional[str]:
    return _parse_sd_list_command(text)


def parse_sd_send_command(text: str) -> Optional[str]:
    return _parse_sd_send_command(text)


def parse_sd_save_command(text: str) -> Optional[str]:
    return _parse_sd_save_command(text)


def extract_assistant_persona(text: str) -> Tuple[str, str]:
    return _extract_assistant_persona(text, normalize_whitespace)


def is_explicit_runtime_restart_request(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return False
    direct_markers = (
        "restart run_jarvis_supervisor",
        "рестарт run_jarvis_supervisor",
        "перезапусти run_jarvis_supervisor",
        "restart supervisor",
        "рестарт supervisor",
        "перезапусти supervisor",
        "перезапусти супервизор",
        "рестарт супервизор",
        "рестарт супервизора",
        "перезапусти бот",
        "перезапусти бота",
        "рестарт бота",
        "сделай рестарт",
        "сделай перезапуск",
        "перезапуск бота",
        "перезапуск супервизора",
    )
    if any(marker in lowered for marker in direct_markers):
        return True
    if "restart" in lowered and any(token in lowered for token in ("jarvis", "bridge", "bot", "supervisor")):
        return True
    return False


def parse_who_said_command(text: str) -> Optional[str]:
    return _parse_who_said_command(text)


def parse_history_command(text: str) -> Optional[str]:
    return _parse_history_command(text)


def parse_daily_command(text: str) -> Optional[str]:
    return _parse_daily_command(text)


def parse_digest_command(text: str) -> Optional[str]:
    return _parse_digest_command(text)


def parse_chat_watch_command(text: str) -> bool:
    return _parse_chat_watch_command(text)


def parse_owner_report_command(text: str) -> bool:
    return _parse_owner_report_command(text)


def parse_routes_command(text: str) -> Optional[str]:
    return _parse_routes_command(text)


def parse_memory_chat_command(text: str) -> Optional[str]:
    return _parse_memory_chat_command(text)


def parse_memory_user_command(text: str) -> Optional[str]:
    return _parse_memory_user_command(text)


def parse_memory_summary_command(text: str) -> bool:
    return _parse_memory_summary_command(text)


def parse_self_state_command(text: str) -> bool:
    return _parse_self_state_command(text)


def parse_world_state_command(text: str) -> bool:
    return _parse_world_state_command(text)


def parse_drives_command(text: str) -> bool:
    return _parse_drives_command(text)


def parse_autobio_command(text: str) -> Optional[str]:
    return _parse_autobio_command(text)


def parse_skills_command(text: str) -> Optional[str]:
    return _parse_skills_command(text)


def parse_reflections_command(text: str) -> Optional[str]:
    return _parse_reflections_command(text)


def parse_chat_digest_command(text: str) -> Optional[str]:
    return _parse_chat_digest_command(text)


def parse_git_status_command(text: str) -> bool:
    return _parse_git_status_command(text)


def parse_git_last_command(text: str) -> Optional[str]:
    return _parse_git_last_command(text)


def parse_errors_command(text: str) -> Optional[str]:
    return _parse_errors_command(text)


def parse_events_command(text: str) -> Optional[str]:
    return _parse_events_command(text)


def parse_export_command(text: str) -> Optional[str]:
    return _parse_export_command(text)


def parse_portrait_command(text: str) -> Optional[str]:
    return _parse_portrait_command(text)


def parse_owner_autofix_command(text: str) -> Optional[str]:
    return _parse_owner_autofix_command(text)


def parse_password_command(text: str) -> Optional[str]:
    return _parse_password_command(text)


def parse_moderation_command(text: str) -> Optional[Tuple[str, str]]:
    return _parse_moderation_command(text)


def parse_warn_command(text: str) -> Optional[Tuple[str, str]]:
    return _parse_warn_command(text)


def parse_welcome_command(text: str) -> Optional[Tuple[str, str]]:
    for command in ("setwelcome", "resetwelcome", "welcome"):
        prefix = f"/{command}"
        if text.startswith(prefix):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            return command, payload
    return None


def split_duration_and_rest(text: str) -> Tuple[str, str]:
    parts = (text or "").split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()


def parse_duration_to_seconds(value: str) -> Optional[int]:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    match = re.fullmatch(r"(\d+)([mhdw])", cleaned)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    factors = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    return amount * factors[unit]


def format_duration_seconds(seconds: int) -> str:
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{max(1, seconds // 60)}m"


def format_progress_elapsed(seconds: int) -> str:
    seconds = max(1, int(seconds))
    minutes, rem_seconds = divmod(seconds, 60)
    if minutes <= 0:
        return f"{rem_seconds} сек"
    if rem_seconds == 0:
        return f"{minutes} мин"
    return f"{minutes} мин {rem_seconds} сек"


def format_signed_value(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric > 0:
        return f"+{numeric:.1f}".rstrip("0").rstrip(".")
    return f"{numeric:.1f}".rstrip("0").rstrip(".")


def normalize_location_query(text: str) -> str:
    cleaned = normalize_whitespace(text)
    cleaned = re.sub(r"^[\s,:-]+|[\s?!.,:;-]+$", "", cleaned)
    return cleaned


def build_location_query_variants(text: str) -> List[str]:
    normalized = normalize_location_query(text)
    if not normalized:
        return []
    variants: List[str] = [normalized]
    lowered = normalized.lower()
    irregular_forms = {
        "брянске": "Брянск",
        "москве": "Москва",
        "донбасс": "Донецк",
        "донбассе": "Донецк",
        "петербурге": "Санкт-Петербург",
        "питере": "Санкт-Петербург",
        "екатеринбурге": "Екатеринбург",
        "калининграде": "Калининград",
        "новосибирске": "Новосибирск",
        "челябинске": "Челябинск",
        "иркутске": "Иркутск",
        "красноярске": "Красноярск",
        "смоленске": "Смоленск",
        "курске": "Курск",
        "омске": "Омск",
        "томске": "Томск",
        "воронеже": "Воронеж",
        "краснодаре": "Краснодар",
    }
    if lowered in irregular_forms:
        variants.append(irregular_forms[lowered])
    if len(normalized.split()) == 1:
        if lowered.endswith("ске") and len(normalized) > 4:
            variants.append(normalized[:-1])
        if lowered.endswith("граде") and len(normalized) > 6:
            variants.append(normalized[:-1])
        if lowered.endswith("бурге") and len(normalized) > 6:
            variants.append(normalized[:-1])
    deduped: List[str] = []
    seen: Set[str] = set()
    for candidate in variants:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def detect_weather_location(text: str) -> str:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return ""
    weather_markers = ("погода", "температур", "прогноз", "дожд", "снег", "ветер", "weather")
    if not any(marker in lowered for marker in weather_markers):
        return ""
    patterns = [
        r"(?:погода|прогноз)(?:\s+сейчас|\s+сегодня|\s+на\s+сегодня|\s+завтра)?\s+в\s+(.+)$",
        r"(?:какая\s+)?погода\s+в\s+(.+)$",
        r"(?:температура|прогноз)\s+в\s+(.+)$",
    ]
    cleaned = normalize_whitespace(text)
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1)
            candidate = re.split(
                r"(?i)(?:[!?]|,\s*(?:и\s+на|и\s+в|курс|какой|когда|кто|что|как)|\b(?:курс|какой|когда|кто|что|как)\b)",
                candidate,
                maxsplit=1,
            )[0]
            return normalize_location_query(candidate)
    words = cleaned.split()
    if len(words) >= 2 and words[0].lower() in {"погода", "weather"}:
        return normalize_location_query(" ".join(words[1:]))
    return ""


def detect_weather_locations(text: str, limit: int = 3) -> List[str]:
    cleaned = normalize_whitespace(text)
    lowered = cleaned.lower()
    if not cleaned or "погод" not in lowered:
        return []
    candidates: List[str] = []
    primary = detect_weather_location(cleaned)
    if primary:
        candidates.append(primary)
    segment_match = re.search(r"(?i)(?:погода|прогноз)(?:\s+сейчас|\s+сегодня|\s+на\s+сегодня|\s+завтра)?\s+в\s+(.+)", cleaned)
    if segment_match:
        segment = segment_match.group(1)
        segment = re.split(r"(?i)\b(?:курс|битко|bitcoin|смартфон|как меня звать|кто в чате|какие были|важные события)\b", segment, maxsplit=1)[0]
        for part in re.split(r"(?i),|\s+и\s+на\s+|\s+и\s+в\s+|\s+и\s+", segment):
            candidate = normalize_location_query(part)
            if not candidate:
                continue
            lowered_candidate = candidate.lower()
            if lowered_candidate in {"на", "в", "и", "донбассе"}:
                if lowered_candidate == "донбассе":
                    candidates.append("Донбасс")
                continue
            candidates.append(candidate)
    deduped: List[str] = []
    seen: Set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def detect_currency_pair(text: str) -> Optional[Tuple[str, str]]:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return None
    if not any(token in lowered for token in ("курс", "usd", "eur", "rub", "руб", "доллар", "евро", "юань", "тенге", "гривн", "фунт")):
        return None
    codes: List[str] = []
    for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ]+", lowered):
        code = CURRENCY_ALIASES.get(token)
        if code and code not in codes:
            codes.append(code)
    if len(codes) >= 2:
        return codes[0], codes[1]
    if "курс дол" in lowered or "доллар" in lowered or "usd" in lowered:
        return "USD", "RUB"
    if "курс евр" in lowered or "евро" in lowered or "eur" in lowered:
        return "EUR", "RUB"
    if "курс юан" in lowered or "cny" in lowered:
        return "CNY", "RUB"
    return None


def detect_crypto_asset(text: str) -> str:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return ""
    if not any(token in lowered for token in ("crypto", "крипт", "монет", "coin", "price", "цена", "сколько стоит", "курс")):
        return ""
    for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_-]+", lowered):
        asset = CRYPTO_ALIASES.get(token)
        if asset:
            return asset
    return ""




def detect_stock_symbol(text: str) -> str:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return ""
    if not any(token in lowered for token in ("акци", "ticker", "тикер", "stock", "price", "цена", "сколько стоит", "котиров")):
        return ""
    for token in re.findall(r"[a-zA-Z]{1,10}|[а-яА-ЯёЁ]{2,20}", lowered):
        symbol = STOCK_ALIASES.get(token)
        if symbol:
            return symbol
        if re.fullmatch(r"[A-Z]{1,5}", token):
            return token
    return ""


def detect_news_query(text: str) -> str:
    cleaned = normalize_whitespace(text)
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if is_purchase_advice_request(lowered) or is_comparison_request(lowered) or is_recommendation_request(lowered):
        return ""
    if detect_local_chat_query(lowered) and not has_external_research_signal(lowered):
        return ""
    news_markers = (
        "новост",
        "latest",
        "today",
        "сегодня",
        "за последний день",
        "за день",
        "за сутки",
        "важные события",
        "что нового",
        "что случилось",
        "что происходит",
        "что произошло",
        "последние",
        "свежие",
        "breaking",
        "headline",
    )
    if not any(marker in lowered for marker in news_markers):
        return ""
    if (
        any(marker in lowered for marker in ("важные события", "что в мире творится", "в мире"))
        and any(marker in lowered for marker in ("за последний день", "за день", "за сутки", "сегодня", "последние", "свежие"))
    ):
        return "важные события в мире за последний день"
    query = lowered
    replacements = (
        "последние новости",
        "свежие новости",
        "новости",
        "что нового",
        "что случилось",
        "latest news",
        "latest",
        "today",
        "сегодня",
        "на сегодня",
        "что происходит",
        "что произошло",
        "проверь",
        "найди",
    )
    for token in replacements:
        query = query.replace(token, " ")
    normalized = normalize_location_query(query)
    return normalized or normalize_whitespace(cleaned)


def detect_smartphone_sales_query(text: str) -> str:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return ""
    if "смартфон" not in lowered and "iphone" not in lowered and "android" not in lowered:
        return ""
    sales_markers = ("самый продаваем", "лидер продаж", "больше всего прода", "топ продаж")
    if not any(marker in lowered for marker in sales_markers):
        return ""
    if "в мире" in lowered or "world" in lowered:
        return "самый продаваемый смартфон в мире сейчас"
    return "самый продаваемый смартфон сейчас"


def detect_bitcoin_market_query(text: str) -> str:
    lowered = normalize_whitespace(text).lower()
    if "битко" not in lowered and "bitcoin" not in lowered:
        return ""
    if any(marker in lowered for marker in ("бум", "рост", "когда", "прогноз", "рынок")):
        return "биткойн прогноз роста сейчас"
    return ""


def is_model_identity_query(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return False
    direct_variants = {
        "enterprise",
        "enterprise?",
        "enterprise core",
        "enterprise core?",
        "кто ты",
        "кто ты?",
        "ты кто",
        "ты кто?",
    }
    if lowered in direct_variants:
        return True
    markers = (
        "на какой ты модели",
        "какая у тебя модель",
        "что у тебя за модель",
        "на чем ты работаешь",
        "на чём ты работаешь",
        "что у тебя внутри",
        "ты gpt",
        "ты codex",
        "ты openai",
    )
    return any(marker in lowered for marker in markers)


def is_prompt_meta_query(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    if not lowered:
        return False
    if "промт" not in lowered and "prompt" not in lowered and "инструкц" not in lowered:
        return False
    markers = (
        "покажи промт",
        "покажи prompt",
        "что у тебя в промте",
        "что у тебя в prompt",
        "какой у тебя промт",
        "какие у тебя инструкции",
        "служебные рамки",
        "в промт сделали",
    )
    return any(marker in lowered for marker in markers)


def build_meta_identity_answer(user_text: str, *, persona: str) -> str:
    if is_model_identity_query(user_text):
        return "Я Enterprise." if persona == "enterprise" else "Я Jarvis."
    if is_prompt_meta_query(user_text):
        del persona
        return (
            "Служебный промт целиком не показываю.\n\n"
            "По сути там зафиксированы роль Enterprise, краткий стиль ответа и запрет на вывод внутренней кухни наружу."
        )
    return ""


def build_owner_contact_reply(user_text: str, *, persona: str) -> str:
    lowered = normalize_whitespace(user_text).lower()
    if not _is_simple_greeting(lowered):
        return ""
    if persona == "enterprise":
        variants = ("На связи, Дмитрий.",)
    else:
        variants = (
            "Привет, Дмитрий. На связи.",
            "Здесь, Дмитрий. Чем займёмся?",
            "На месте, Дмитрий.",
            "Привет. Я в контексте.",
        )
    index = sum(ord(char) for char in lowered) % len(variants)
    return variants[index]


def detect_current_fact_query(text: str) -> str:
    cleaned = normalize_whitespace(text)
    lowered = cleaned.lower()
    if not lowered:
        return ""
    role_markers = (
        "президент",
        "премьер",
        "премьер-министр",
        "мэр",
        "губернатор",
        "ceo",
        "cfo",
        "cto",
        "owner",
        "владелец",
        "глава",
        "руковод",
        "директор",
        "гендир",
        "генеральный директор",
        "председатель",
        "канцлер",
        "министр",
    )
    freshness_markers = ("кто", "сейчас", "current", "latest", "сегодня", "последний", "последняя", "последнее", "текущий", "нынешний")
    markers = (
        "кто сейчас",
        "кто президент",
        "кто премьер",
        "кто мэр",
        "кто губернатор",
        "кто ceo",
        "кто cfo",
        "кто owner",
        "кто владелец",
        "кто гендир",
        "кто генеральный директор",
        "who is the",
        "who is",
        "current ceo",
        "current president",
        "кто сейчас глава",
        "кто сейчас руководит",
        "кто сейчас владеет",
        "кто сейчас министр",
        "кто сейчас директор",
        "кто сейчас председатель",
        "кто сейчас канцлер",
        "кто сейчас премьер-министр",
        "кто сейчас правит",
        "кто сейчас управляет",
    )
    if any(marker in lowered for marker in markers):
        return cleaned
    if any(role in lowered for role in role_markers) and any(marker in lowered for marker in freshness_markers):
        return cleaned
    if any(role in lowered for role in role_markers) and len(cleaned.split()) >= 2:
        return cleaned
    return ""


def build_progress_bar(phase_index: int, elapsed_seconds: int, width: int = 10) -> str:
    width = max(5, width)
    animated_fill = (phase_index + max(1, elapsed_seconds // CODEX_PROGRESS_UPDATE_SECONDS)) % (width + 1)
    filled = min(width, max(1, animated_fill))
    return "█" * filled + "·" * (width - filled)


def progress_style_config(style: str) -> Tuple[List[Tuple[str, str]], Tuple[str, ...], List[str], List[Tuple[int, str]]]:
    normalized = (style or "jarvis").strip().lower()
    if normalized == "enterprise":
        return (
            ENTERPRISE_PROGRESS_STEPS,
            ENTERPRISE_PROGRESS_SPINNERS,
            ENTERPRISE_PROGRESS_MICRO_JOKES,
            ENTERPRISE_PROGRESS_LONG_NOTES,
        )
    return (
        JARVIS_PROGRESS_STEPS,
        JARVIS_PROGRESS_SPINNERS,
        JARVIS_PROGRESS_MICRO_JOKES,
        JARVIS_PROGRESS_LONG_NOTES,
    )


def select_long_progress_note(elapsed_seconds: int, notes: List[Tuple[int, str]]) -> str:
    note = ""
    for threshold, text in notes:
        if elapsed_seconds >= threshold:
            note = text
    return note


def build_progress_status(
    initial_status: str,
    elapsed_seconds: int,
    phase_index: int,
    style: str = "jarvis",
    target_label: str = "",
) -> str:
    elapsed_text = format_progress_elapsed(elapsed_seconds)
    target_line = f"\nСобеседник: {truncate_text(target_label, 28)}" if target_label else ""
    return (
        f"{initial_status}\n\n"
        f"Выполняю...\n"
        f"Прошло: {elapsed_text}"
        f"{target_line}"
    )


def build_context_budget_status(
    *,
    prompt_len: int,
    history_items: int,
    history_limit: int,
    soft_limit: int = DEFAULT_BRIDGE_CONTEXT_SOFT_LIMIT,
) -> str:
    bounded_prompt = max(0, int(prompt_len))
    bounded_history = max(0, int(history_items))
    bounded_limit = max(1, int(history_limit))
    remaining = max(0, soft_limit - bounded_prompt)
    remaining_pct = int(max(0.0, min(100.0, (remaining / max(1, soft_limit)) * 100.0)))
    compression_flag = "да" if bounded_prompt >= soft_limit or bounded_history >= bounded_limit else "нет"
    return (
        f"Контекст bridge: ~{bounded_prompt}/{soft_limit} симв.\n"
        f"История: {bounded_history}/{bounded_limit}\n"
        f"Запас: ~{remaining_pct}%\n"
        f"Сжатие: {compression_flag}"
    )


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")

def can_owner_use_workspace_mode(user_id: Optional[int], chat_type: str, assistant_persona: str = "") -> bool:
    return _bridge_can_owner_use_workspace_mode(
        user_id,
        chat_type,
        assistant_persona,
        owner_user_id=OWNER_USER_ID,
    )


def is_owner_private_chat(user_id: Optional[int], chat_id: int) -> bool:
    return bool(chat_id > 0 and is_owner_identity(user_id) and int(chat_id) == int(user_id or 0))


def has_chat_access(_authorized_user_ids: Set[int], user_id: Optional[int]) -> bool:
    return bool(is_owner_identity(user_id))


def has_public_command_access(text: str) -> bool:
    return _bridge_has_public_command_access(text, allowed_commands=PUBLIC_ALLOWED_COMMANDS)


def has_public_callback_access(data: str) -> bool:
    return _bridge_has_public_callback_access(data, allowed_callbacks=PUBLIC_ALLOWED_CALLBACKS)


def is_group_chat(chat_type: str) -> bool:
    return chat_type in {"group", "supergroup"}


def contains_profanity(text: str) -> bool:
    return _bridge_contains_profanity(text)


def should_attempt_owner_autofix(text: str, message: dict) -> bool:
    return _bridge_should_attempt_owner_autofix(text, message)


def is_codex_unavailable_output(text: str) -> bool:
    lowered = (text or "").lower()
    markers = (
        "failed to refresh available models",
        "403 forbidden",
        "backend-api/codex/models",
        "error sending request for url",
        "stream disconnected before completion",
        "unexpected status 403",
    )
    return any(marker in lowered for marker in markers)


def is_codex_network_error_output(text: str) -> bool:
    lowered = normalize_whitespace(text or "").lower()
    markers = (
        "api connection error",
        "apiconnectionerror",
        "network error",
        "connection error",
        "connection reset",
        "connection aborted",
        "connection refused",
        "connection timed out",
        "connect timeout",
        "read timeout",
        "timed out",
        "timeout was reached",
        "temporary failure in name resolution",
        "name or service not known",
        "nodename nor servname provided",
        "failed to resolve host",
        "could not resolve host",
        "dns",
        "econnreset",
        "econnrefused",
        "enetunreach",
        "ehostunreach",
        "enotfound",
        "service unavailable",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "stream disconnected before completion",
        "error sending request for url",
        "connection to api.openai.com",
        "peer closed connection",
        "socket is not connected",
        "clientconnectorerror",
        "all connection attempts failed",
    )
    return any(marker in lowered for marker in markers)


def extract_usable_codex_stdout(stdout: str) -> str:
    candidate = extract_codex_text_response(stdout)
    if not candidate:
        return ""
    lowered = candidate.lower()
    blocked_prefixes = (
        "openai codex v",
        "workdir:",
        "model:",
        "provider:",
        "approval:",
        "sandbox:",
        "reasoning effort:",
        "session id:",
        "mcp startup:",
    )
    if any(lowered.startswith(prefix) for prefix in blocked_prefixes):
        return ""
    return candidate


def extract_codex_error_summary(text: str) -> str:
    cleaned = normalize_whitespace(text or "")
    if not cleaned:
        return ""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return cleaned
    ignored_prefixes = (
        "OpenAI Codex v",
        "workdir:",
        "model:",
        "provider:",
        "approval:",
        "sandbox:",
        "reasoning effort:",
        "reasoning summaries:",
        "session id:",
        "user",
        "mcp startup:",
        "--------",
        "System:",
    )
    informative_lines = [
        line for line in lines
        if not any(line.startswith(prefix) for prefix in ignored_prefixes)
    ]
    if not informative_lines:
        return cleaned
    priority_markers = (
        "ERROR:",
        "error sending request",
        "stream disconnected before completion",
        "failed to connect",
        "connection refused",
        "connection timed out",
        "connection error",
        "network error",
        "failed to refresh available models",
        "403 forbidden",
        "unexpected status 403",
    )
    for line in reversed(informative_lines):
        lowered = line.lower()
        if any(marker.lower() in lowered for marker in priority_markers):
            return normalize_whitespace(line)
    return normalize_whitespace(informative_lines[-1])


def build_codex_failure_answer(
    details: str,
    *,
    sandbox_mode: Optional[str] = None,
    approval_policy: Optional[str] = None,
) -> str:
    summary = extract_codex_error_summary(details)
    if is_codex_network_error_output(details) or is_codex_network_error_output(summary):
        return JARVIS_NETWORK_ERROR_TEXT
    if is_codex_unavailable_output(details) or is_codex_unavailable_output(summary):
        return JARVIS_OFFLINE_TEXT
    if approval_policy == "never" and sandbox_mode == "workspace-write":
        return f"{UPGRADE_FAILED_TEXT}\n{truncate_text(summary or details, 600)}"
    concise = summary or details or "Движок Enterprise Core v194.95. завершился с ошибкой без вывода."
    return f"Ошибка Enterprise Core:\n{truncate_text(concise, 400)}"


def build_help_panel_text(section: str) -> str:
    return _bridge_build_help_panel_text(
        section,
        owner_username=OWNER_USERNAME,
        owner_user_id=OWNER_USER_ID,
        public_help_text=PUBLIC_HELP_TEXT,
        public_achievements_help_text=PUBLIC_ACHIEVEMENTS_HELP_TEXT,
        public_appeal_help_text=PUBLIC_APPEAL_HELP_TEXT,
    )


def build_help_panel_markup(section: str) -> dict:
    return _bridge_build_help_panel_markup(section)


def build_welcome_text(template: str, user: dict, chat_title: str) -> str:
    return _bridge_build_welcome_text(template, user, chat_title, default_template=WELCOME_DEFAULT_TEMPLATE)


def build_user_autofix_label(user: dict) -> str:
    return _bridge_build_user_autofix_label(user)


def normalize_compare_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def extract_codex_text_response(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    if "\ncodex\n" in cleaned:
        tail = cleaned.split("\ncodex\n")[-1]
        if "\ntokens used" in tail:
            tail = tail.split("\ntokens used", 1)[0]
        return normalize_whitespace(tail)
    return cleaned


def extract_alpha_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё]+", text or "")


def has_obvious_typo_markers(text: str) -> bool:
    cleaned = text or ""
    return any((
        re.search(r"([A-Za-zА-Яа-яЁё])\1{2,}", cleaned) is not None,
        re.search(r"[A-Za-z]+[А-Яа-яЁё]+|[А-Яа-яЁё]+[A-Za-z]+", cleaned) is not None,
        re.search(r"[,.;:!?][^\s\n]", cleaned) is not None,
        re.search(r"[!?.,]{3,}", cleaned) is not None,
        re.search(r"\b[А-Яа-яЁё]{4,}\b", cleaned) is not None and cleaned.lower() != cleaned,
    ))


def has_word_level_correction(original_text: str, fixed_text: str) -> bool:
    original_words = extract_alpha_words(original_text)
    fixed_words = extract_alpha_words(fixed_text)
    if not original_words or len(original_words) != len(fixed_words):
        return False
    for original_word, fixed_word in zip(original_words, fixed_words):
        if original_word == fixed_word:
            continue
        ratio = SequenceMatcher(None, original_word.lower(), fixed_word.lower()).ratio()
        if len(original_word) >= 4 and ratio >= 0.55:
            return True
    return False


def is_meaningfully_corrected(original_text: str, fixed_text: str) -> bool:
    original_norm = normalize_compare_text(original_text)
    fixed_norm = normalize_compare_text(fixed_text)
    if original_norm == fixed_norm:
        return False
    similarity = SequenceMatcher(None, original_norm, fixed_norm).ratio()
    original_words = extract_alpha_words(original_text)
    fixed_words = extract_alpha_words(fixed_text)
    if len(original_words) == 1 and len(fixed_words) == 1:
        if len(original_words[0]) >= 4 and similarity >= 0.68:
            return True
        return False
    if similarity < 0.88:
        return False
    if has_word_level_correction(original_text, fixed_text):
        return True
    if has_obvious_typo_markers(original_text) and similarity >= 0.94:
        return True
    return False


def should_attempt_voice_ai_cleanup(text: str) -> bool:
    cleaned = normalize_whitespace(text)
    if not cleaned or len(cleaned) < 8:
        return False
    if has_obvious_typo_markers(cleaned):
        return True
    tokens = extract_alpha_words(cleaned)
    weird_tokens = 0
    for token in tokens:
        lowered = token.lower()
        if len(lowered) <= 3:
            continue
        if re.search(r"(.)\1{2,}", lowered):
            weird_tokens += 1
            continue
        if re.search(r"[a-z]", token) and re.search(r"[а-яё]", token.lower()):
            weird_tokens += 1
            continue
        if lowered in {"джаря", "джависты", "колосса", "голосого"}:
            weird_tokens += 1
    return weird_tokens > 0


def is_safe_voice_cleanup(original_text: str, fixed_text: str) -> bool:
    original_words = extract_alpha_words(original_text)
    fixed_words = extract_alpha_words(fixed_text)
    if not original_words or not fixed_words:
        return False
    if abs(len(original_words) - len(fixed_words)) > 1:
        return False
    if len(fixed_text) > len(original_text) + max(12, len(original_text) // 4):
        return False
    changed_pairs = 0
    for original_word, fixed_word in zip(original_words, fixed_words):
        if original_word == fixed_word:
            continue
        changed_pairs += 1
        ratio = SequenceMatcher(None, original_word.lower(), fixed_word.lower()).ratio()
        if ratio < 0.55:
            return False
        if len(fixed_word) - len(original_word) >= 3 and ratio < 0.8:
            return False
    return changed_pairs > 0


def is_known_voice_term(word: str, context_terms: str) -> bool:
    normalized = (word or "").lower().replace("ё", "е").strip()
    if not normalized:
        return False
    builtins = {"джарвис", "джервис", "jarvis", "enterprise", "codex", "рейтинг", "ачивки", "достижения", "апелляция", "апелляции", "санкции", "модерация", "уровень", "престиж"}
    if normalized in builtins:
        return True
    for term in [part.strip() for part in (context_terms or "").split(",") if part.strip()]:
        candidate = term.lower().replace("ё", "е")
        if normalized == candidate:
            return True
        if SequenceMatcher(None, normalized, candidate).ratio() >= 0.82:
            return True
    return False


def is_term_only_voice_cleanup(original_text: str, fixed_text: str, context_terms: str) -> bool:
    original_words = extract_alpha_words(original_text)
    fixed_words = extract_alpha_words(fixed_text)
    if len(original_words) != len(fixed_words):
        return False
    changed = 0
    for original_word, fixed_word in zip(original_words, fixed_words):
        if original_word == fixed_word:
            continue
        changed += 1
        original_known = is_known_voice_term(original_word, context_terms)
        fixed_known = is_known_voice_term(fixed_word, context_terms)
        triggerish = (
            SequenceMatcher(None, original_word.lower().replace("ё", "е"), "джарвис").ratio() >= 0.6
            or SequenceMatcher(None, fixed_word.lower().replace("ё", "е"), "джарвис").ratio() >= 0.75
            or SequenceMatcher(None, original_word.lower(), "jarvis").ratio() >= 0.65
            or SequenceMatcher(None, fixed_word.lower(), "jarvis").ratio() >= 0.8
        )
        if not (original_known or fixed_known or triggerish):
            return False
    return changed > 0


def should_process_group_message(message: dict, text: str, bot_username: str, trigger_name: str, bot_user_id: Optional[int] = None, allow_owner_reply: bool = False) -> bool:
    return _bridge_should_process_group_message(
        message,
        text,
        bot_username,
        trigger_name,
        owner_user_id=OWNER_USER_ID,
        owner_username=OWNER_USERNAME,
        extract_assistant_persona_func=extract_assistant_persona,
        default_trigger_name=DEFAULT_TRIGGER_NAME,
        bot_user_id=bot_user_id,
        allow_owner_reply=allow_owner_reply,
    )


def contains_voice_trigger_name(text: str, trigger_name: str, bot_username: str) -> bool:
    return _bridge_contains_voice_trigger_name(
        text,
        trigger_name,
        bot_username,
        default_trigger_name=DEFAULT_TRIGGER_NAME,
    )

def resolve_sdcard_path(raw_path: str, *, allow_missing: bool, default_to_root: bool) -> Path:
    return _bridge_resolve_sdcard_path(
        raw_path,
        allow_missing=allow_missing,
        default_to_root=default_to_root,
        usage_text=SD_SEND_USAGE_TEXT,
    )


def resolve_sdcard_save_target(raw_target: str, suggested_name: str) -> Path:
    return _bridge_resolve_sdcard_save_target(
        raw_target,
        suggested_name,
        default_sd_save_alias=DEFAULT_SD_SAVE_ALIAS,
        usage_text=SD_SEND_USAGE_TEXT,
    )


def ensure_sdcard_save_target_writable(destination: Path) -> None:
    _bridge_ensure_sdcard_save_target_writable(destination)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def normalize_sdcard_alias(raw_path: str) -> str:
    return _bridge_normalize_sdcard_alias(raw_path)


def extract_message_media_file(message: dict) -> Optional[Tuple[str, str]]:
    return _bridge_extract_message_media_file(message)


def format_file_size(size: int) -> str:
    return _bridge_format_file_size(size)


def normalize_incoming_text(text: str, bot_username: str) -> str:
    return _bridge_normalize_incoming_text(text, bot_username)


def format_reaction_payload(reactions: List[dict]) -> str:
    return _format_reaction_payload(reactions)


def build_service_actor_name(user: dict) -> str:
    return _build_service_actor_name(user, build_actor_name)


def extract_forward_origin(message: dict) -> str:
    return _extract_forward_origin(message, build_service_actor_name)


def summarize_message_for_pin(message: dict) -> str:
    return _summarize_message_for_pin(message, truncate_text)


def describe_message_media_kind(message: dict) -> str:
    return _describe_message_media_kind(message)


def read_recent_log_highlights(log_path: Path, limit: int = 8) -> List[str]:
    return _bridge_read_recent_log_highlights(
        log_path,
        normalize_whitespace_func=normalize_whitespace,
        truncate_text_func=truncate_text,
        limit=limit,
    )


def is_error_log_line(lowered_line: str) -> bool:
    return _bridge_is_error_log_line(lowered_line)


def read_recent_operational_highlights(log_path: Path, limit: int = 8, category: str = "all") -> List[str]:
    return _bridge_read_recent_operational_highlights(
        log_path,
        normalize_whitespace_func=normalize_whitespace,
        truncate_text_func=truncate_text,
        limit=limit,
        category=category,
    )


def is_operational_log_line(lowered_line: str, category: str = "all") -> bool:
    return _bridge_is_operational_log_line(lowered_line, category)


def inspect_runtime_log(log_path: Path, window_seconds: int = 86400) -> Dict[str, object]:
    return _bridge_inspect_runtime_log(log_path, window_seconds)


def run_git_command(repo_path: Path, args: List[str], timeout_seconds: int = 20) -> str:
    return _bridge_run_git_command(
        repo_path,
        args,
        build_subprocess_env_func=build_subprocess_env,
        normalize_whitespace_func=normalize_whitespace,
        timeout_seconds=timeout_seconds,
    )


def render_git_status_summary(repo_path: Path) -> str:
    return _bridge_render_git_status_summary(repo_path, run_git_command_func=run_git_command)


def render_git_last_commits(repo_path: Path, limit: int = 5) -> str:
    return _bridge_render_git_last_commits(repo_path, run_git_command_func=run_git_command, limit=limit)


def read_document_excerpt(file_path: Path, mime_type: str, max_chars: int = 3500) -> str:
    return _bridge_read_document_excerpt(file_path, mime_type, truncate_text_func=truncate_text, max_chars=max_chars)


def format_reaction_count_payload(reactions: List[dict]) -> str:
    return _format_reaction_count_payload(reactions)


def is_dangerous_request(text: str) -> bool:
    lowered = text.lower()
    danger_markers = [
        "создай файл",
        "создать файл",
        "удали файл",
        "удалить файл",
        "измени файл",
        "изменить файл",
        "запусти команд",
        "выполни команд",
        "run command",
        "shell command",
        "terminal command",
        "apt install",
        "pkg install",
        "pip install",
        "npm install",
        "rm -rf",
        "sudo ",
        "chmod ",
        "chown ",
        "git clone",
    ]
    return any(marker in lowered for marker in danger_markers)


def build_prompt(
    mode: str,
    history: List[Tuple[str, str]],
    user_text: str,
    attachment_note: str = "",
    summary_text: str = "",
    facts_text: str = "",
    event_context: str = "",
    database_context: str = "",
    reply_context: str = "",
    discussion_context: str = "",
    identity_label: str = "Jarvis",
    include_identity_prompt: bool = True,
    persona_note: str = "",
    owner_note: str = "",
    web_context: str = "",
    route_summary: str = "",
    guardrail_note: str = "",
    self_model_text: str = "",
    autobiographical_text: str = "",
    skill_memory_text: str = "",
    world_state_text: str = "",
    drive_state_text: str = "",
    user_memory_text: str = "",
    relation_memory_text: str = "",
    chat_memory_text: str = "",
    summary_memory_text: str = "",
    task_context_text: str = "",
    memory_trace_text: str = "",
) -> str:
    return _build_prompt(
        mode=mode,
        history=history,
        user_text=user_text,
        mode_prompts=MODE_PROMPTS,
        default_mode_name=DEFAULT_MODE_NAME,
        base_system_prompt=BASE_SYSTEM_PROMPT,
        detect_intent_func=detect_intent,
        response_shape_hint_func=response_shape_hint,
        truncate_text_func=truncate_text,
        max_history_item_chars=MAX_HISTORY_ITEM_CHARS,
        attachment_note=attachment_note,
        summary_text=summary_text,
        facts_text=facts_text,
        event_context=event_context,
        database_context=database_context,
        reply_context=reply_context,
        discussion_context=discussion_context,
        identity_label=identity_label,
        include_identity_prompt=include_identity_prompt,
        persona_note=persona_note,
        owner_note=owner_note,
        web_context=web_context,
        route_summary=route_summary,
        guardrail_note=guardrail_note,
        self_model_text=self_model_text,
        autobiographical_text=autobiographical_text,
        skill_memory_text=skill_memory_text,
        world_state_text=world_state_text,
        drive_state_text=drive_state_text,
        user_memory_text=user_memory_text,
        relation_memory_text=relation_memory_text,
        chat_memory_text=chat_memory_text,
        summary_memory_text=summary_memory_text,
        task_context_text=task_context_text,
        memory_trace_text=memory_trace_text,
    )

def format_history(history: List[Tuple[str, str]], user_text: str) -> str:
    return _format_history(history, user_text, truncate_text, MAX_HISTORY_ITEM_CHARS)


def dedupe_history(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return _dedupe_history(items)


def extract_keywords(text: str) -> Set[str]:
    return _extract_keywords(text)


def build_fts_query(text: str) -> str:
    return _build_fts_query(text)


def build_actor_name(user_id: Optional[int], username: str, first_name: str, last_name: str, role: str) -> str:
    if role == "assistant":
        return "Jarvis"
    if user_id == OWNER_USER_ID:
        display = " ".join(part for part in [first_name, last_name] if part).strip()
        owner_name = display or OWNER_USERNAME.lstrip("@").strip() or "Дмитрий"
        return f"{owner_name} (owner)"
    display = " ".join(part for part in [first_name, last_name] if part).strip()
    if username:
        return f"@{username} id={user_id}" if user_id is not None else f"@{username}"
    if display:
        return f"{display} id={user_id}" if user_id is not None else display
    return f"user_id={user_id}" if user_id is not None else "user"


CHAT_TROUBLEMAKER_RISK_MARKERS = (
    "нах",
    "охуе",
    "заеб",
    "пизд",
    "ебан",
    "долбо",
    "идиот",
    "туп",
    "чмо",
    "говно",
    "бред",
    "бес",
    "задолбал",
    "заткнись",
)

CHAT_TROUBLEMAKER_TAUNT_MARKERS = (
    "ахах",
    "хаха",
    "ору",
    "лол",
    "кек",
    ")))",
    "😂",
    "😁",
    "😄",
)


def is_owner_identity(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return int(user_id) == OWNER_USER_ID or int(user_id) in OWNER_ALIAS_USER_IDS


def translate_risk_flag(flag: str) -> str:
    mapping = {
        "suspicious_visual": "подозрительный визуальный паттерн",
        "likely_bot_like": "похоже на неаутентичный/ботоподобный аккаунт",
        "likely_bot": "похоже на неаутентичный/ботоподобный аккаунт",
        "bot_like": "ботоподобный стиль",
        "engagement_bait": "вовлекающая приманка",
        "mass_bait": "массовая приманка",
        "fake_identity": "возможная фейковая личность",
        "promo_bait": "рекламная приманка",
        "scam_risk": "риск скама/развода",
        "romance_scam": "романтический скам",
        "sexual_bait": "сексуализированная приманка",
        "adult_promo": "18+ промо",
        "sexualized_profile": "сексуализированный профиль",
        "toxic": "токсичный",
        "high_conflict": "конфликтный",
        "spammy": "спамит",
        "flood_prone": "склонен к флуду",
        "emotionally_unstable": "эмоционально нестабилен",
        "helpful": "полезный",
        "technically_reliable": "технически надёжен",
        "owner_hostile": "враждебен к владельцу",
    }
    return mapping.get(flag, flag)


def normalize_visual_analysis_text(text: str) -> str:
    cleaned = normalize_whitespace(text or "")
    if not cleaned:
        return ""
    replacements = {
        "scene:": "Сцена:",
        "profile_style:": "Стиль профиля:",
        "risk_flags:": "Флаги риска:",
        "why:": "Почему:",
        "scene :": "Сцена:",
        "profile_style :": "Стиль профиля:",
        "risk_flags :": "Флаги риска:",
        "why :": "Почему:",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    for flag in (
        "suspicious_visual",
        "likely_bot_like",
        "likely_bot",
        "bot_like",
        "engagement_bait",
        "mass_bait",
        "fake_identity",
        "promo_bait",
        "scam_risk",
        "romance_scam",
        "sexual_bait",
        "adult_promo",
        "sexualized_profile",
    ):
        cleaned = re.sub(rf"\b{re.escape(flag)}\b", translate_risk_flag(flag), cleaned)
    replacements_text = {
        "dramatic motivational/freedom-themed stock-style image, not a personal photo": "драматичная мотивационная стоковая картинка в стиле свободы, не личное фото",
        "generic symbolic image, strong emotional framing, and non-personal stock-like visual often used by low-trust or mass-engagement accounts": "символическая картинка с сильной эмоциональной подачей; визуал не похож на личное фото и часто встречается у аккаунтов с низким доверием или bait-стилем",
        "silhouette of a person breaking chains at sunset": "силуэт человека, разрывающего цепи на фоне заката",
    }
    lowered = cleaned.lower()
    for source, target in replacements_text.items():
        if source in lowered:
            cleaned = re.sub(re.escape(source), target, cleaned, flags=re.IGNORECASE)
            lowered = cleaned.lower()
    return cleaned


def render_chat_troublemaker_summary(
    rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
    *,
    top_limit: int = 3,
) -> str:
    def _pretty_actor(user_id: Optional[int], username: str, first_name: str, last_name: str, role: str) -> str:
        if role == "assistant":
            return "Jarvis"
        if is_owner_identity(user_id):
            display = " ".join(part for part in [first_name, last_name] if part).strip() or "Дмитрий"
            return f"{display} (owner)"
        display = " ".join(part for part in [first_name, last_name] if part).strip()
        if display and username:
            return f"{display} (@{username} id={user_id})"
        if display:
            return f"{display} id={user_id}" if user_id is not None else display
        if username:
            return f"@{username} id={user_id}" if user_id is not None else f"@{username}"
        return f"user_id={user_id}" if user_id is not None else "user"

    participant_stats: Dict[str, Dict[str, object]] = {}
    previous_actor = ""
    current_streak = 0

    for _created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
        if role != "user":
            previous_actor = ""
            current_streak = 0
            continue
        actor = _pretty_actor(user_id, username or "", first_name or "", last_name or "", role)
        text = normalize_whitespace(content or "")
        if not text:
            continue
        lowered = text.lower()
        stats = participant_stats.setdefault(
            actor,
            {
                "messages": 0,
                "risk_hits": 0,
                "taunt_hits": 0,
                "caps_hits": 0,
                "burst_hits": 0,
                "duplicate_hits": 0,
                "short_hits": 0,
                "examples": [],
                "last_text": "",
            },
        )
        stats["messages"] = int(stats["messages"]) + 1
        if len(text) <= 18:
            stats["short_hits"] = int(stats["short_hits"]) + 1
        if any(marker in lowered for marker in CHAT_TROUBLEMAKER_RISK_MARKERS):
            stats["risk_hits"] = int(stats["risk_hits"]) + 1
            examples = stats["examples"]
            if isinstance(examples, list) and len(examples) < 2:
                examples.append(truncate_text(text, 80))
        if any(marker in lowered for marker in CHAT_TROUBLEMAKER_TAUNT_MARKERS):
            stats["taunt_hits"] = int(stats["taunt_hits"]) + 1
        alpha_chars = [char for char in text if char.isalpha()]
        if len(alpha_chars) >= 7:
            upper_chars = sum(1 for char in alpha_chars if char.isupper())
            if upper_chars / max(1, len(alpha_chars)) >= 0.68:
                stats["caps_hits"] = int(stats["caps_hits"]) + 1
        if previous_actor == actor:
            current_streak += 1
        else:
            previous_actor = actor
            current_streak = 1
        if current_streak >= 3:
            stats["burst_hits"] = int(stats["burst_hits"]) + 1
        if lowered == stats["last_text"] and len(lowered) >= 8:
            stats["duplicate_hits"] = int(stats["duplicate_hits"]) + 1
        stats["last_text"] = lowered

    ranked_rows: List[Tuple[int, str, Dict[str, object]]] = []
    for actor, stats in participant_stats.items():
        messages = int(stats["messages"])
        risk_hits = int(stats["risk_hits"])
        taunt_hits = int(stats["taunt_hits"])
        caps_hits = int(stats["caps_hits"])
        burst_hits = int(stats["burst_hits"])
        duplicate_hits = int(stats["duplicate_hits"])
        short_hits = int(stats["short_hits"])
        score = (
            risk_hits * 4
            + taunt_hits * 2
            + caps_hits * 2
            + burst_hits * 2
            + duplicate_hits * 3
            + (1 if messages >= 10 and short_hits >= max(4, messages // 2) else 0)
        )
        if score <= 0:
            continue
        ranked_rows.append((score, actor, stats))

    ranked_rows.sort(key=lambda item: (-item[0], -int(item[2]["messages"]), item[1]))
    if not ranked_rows:
        return "Кто гонит беса: по этой выборке последних 100 сообщений явного провокатора не видно; это не вывод по всей истории чата."

    lines = [
        "Кто гонит беса: вероятные источники шума только по этой выборке последних 100 сообщений, не по всей истории чата."
    ]
    for score, actor, stats in ranked_rows[:top_limit]:
        reasons: List[str] = [f"сообщений={int(stats['messages'])}"]
        if int(stats["risk_hits"]):
            reasons.append(f"грубость/агрессия={int(stats['risk_hits'])}")
        if int(stats["taunt_hits"]):
            reasons.append(f"насмешки={int(stats['taunt_hits'])}")
        if int(stats["caps_hits"]):
            reasons.append(f"caps={int(stats['caps_hits'])}")
        if int(stats["burst_hits"]):
            reasons.append(f"серии подряд={int(stats['burst_hits'])}")
        if int(stats["duplicate_hits"]):
            reasons.append(f"повторы={int(stats['duplicate_hits'])}")
        line = f"- {actor}: эвристический_шум_score={score}; " + ", ".join(reasons)
        examples = stats["examples"]
        if isinstance(examples, list) and examples:
            line += f"; примеры: {' | '.join(examples)}"
        lines.append(line)
    return "\n".join(lines)


def build_progress_target_label(message: Optional[dict], user_id: Optional[int]) -> str:
    from_user = (message or {}).get("from") or {}
    if from_user.get("is_bot"):
        return ""
    username = (from_user.get("username") or "").strip().lstrip("@")
    first_name = normalize_whitespace(from_user.get("first_name") or "")
    last_name = normalize_whitespace(from_user.get("last_name") or "")
    display = " ".join(part for part in [first_name, last_name] if part).strip()
    if first_name:
        return first_name
    if display:
        return display
    if username:
        return f"@{username}"
    if user_id == OWNER_USER_ID:
        owner_name = OWNER_USERNAME.lstrip("@").strip()
        return owner_name or "владельца"
    return ""

def render_event_rows(rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]], title: str = "Events") -> str:
    return _render_event_rows(rows, title, build_actor_name, truncate_text)


def render_timeline_rows(label: str, rows: List[Tuple[int, Optional[int], str, str, str, str, str]]) -> str:
    return _render_timeline_rows(label, rows, truncate_text)


# Router logic migrated to `router/request_router.py`.
# Compatibility wrappers below remain as the bridge-facing API until all call sites
# are switched to direct module imports.


def compute_group_spontaneous_reply_score(user_text: str) -> int:
    lowered = normalize_whitespace(user_text).lower()
    if not lowered:
        return 0
    if not is_explicit_help_request(lowered):
        return 0
    score = 0
    if len(lowered) >= 24:
        score += 1
    if "?" in lowered:
        score += 1
    markers = (
        "не работает",
        "не получается",
        "не могу",
        "ошиб",
        "проблем",
        "что с",
        "почему",
        "как исправить",
        "что делать",
        "как решить",
        "можно ли",
        "есть ли",
    )
    if any(marker in lowered for marker in markers):
        score += 2
    if detect_local_chat_query(lowered):
        score += 2
    elif detect_intent(lowered) in {"error_analysis", "task_solving"}:
        score += 1
    structured_help_markers = (
        "выбор",
        "выбрать",
        "смартфон",
        "телефон",
        "ноутбук",
        "планшет",
        "камера",
        "бюджет",
        "до ",
        "лучше взять",
        "что выбрать",
        "что лучше",
        "игр",
        "производительност",
        "энергоэффектив",
    )
    if any(marker in lowered for marker in structured_help_markers):
        score += 2
    if any(marker in lowered for marker in ("бот", "jarvis", "джарвис", "ссылка", "ozon", "озон", "чат", "контекст")):
        score += 1
    return score


ROUTE_KIND_LIVE_MAP = {
    "live_weather": ("open-meteo", detect_weather_location),
    "live_fx": ("frankfurter+yahoo-finance", detect_currency_pair),
    "live_crypto": ("coingecko", detect_crypto_asset),
    "live_stocks": ("yahoo-finance", detect_stock_symbol),
    "live_current_fact": ("duckduckgo+Enterprise", detect_current_fact_query),
    "live_news": ("google-news-rss", detect_news_query),
}
ALLOWED_ROUTE_KINDS = {
    "codex_chat",
    "codex_workspace",
    *ROUTE_KIND_LIVE_MAP.keys(),
}


def validate_route_decision(decision: RouteDecision) -> None:
    return _validate_route_decision(decision, ALLOWED_ROUTE_KINDS)


def _build_router_runtime_deps() -> RouterRuntimeDeps:
    return RouterRuntimeDeps(
        owner_user_id=OWNER_USER_ID,
        normalize_whitespace_func=normalize_whitespace,
        detect_news_query_func=detect_news_query,
        detect_current_fact_query_func=detect_current_fact_query,
        detect_weather_location_func=detect_weather_location,
        detect_currency_pair_func=detect_currency_pair,
        detect_crypto_asset_func=detect_crypto_asset,
        detect_stock_symbol_func=detect_stock_symbol,
        can_owner_use_workspace_mode_func=can_owner_use_workspace_mode,
        is_dangerous_request_func=is_dangerous_request,
        validate_route_decision_func=_validate_route_decision,
    )


def detect_local_chat_query(user_text: str) -> bool:
    return _detect_local_chat_query_module(user_text, normalize_whitespace_func=normalize_whitespace)


def is_local_project_meta_request(user_text: str) -> bool:
    return _is_local_project_meta_request_module(user_text, normalize_whitespace_func=normalize_whitespace)


def detect_owner_admin_request(user_text: str, user_id: Optional[int]) -> bool:
    return _detect_owner_admin_request_module(
        user_text,
        user_id,
        owner_user_id=OWNER_USER_ID,
        normalize_whitespace_func=normalize_whitespace,
    )


def should_include_database_context(user_text: str) -> bool:
    return _should_include_database_context_module(user_text)


def has_external_research_signal(text: str) -> bool:
    return _has_external_research_signal_module(text, normalize_whitespace_func=normalize_whitespace)


def is_product_selection_help_request(text: str) -> bool:
    return _is_product_selection_help_request_module(text, normalize_whitespace_func=normalize_whitespace)


def is_purchase_advice_request(text: str) -> bool:
    return _is_purchase_advice_request_module(text, normalize_whitespace_func=normalize_whitespace)


def is_comparison_request(text: str) -> bool:
    return _is_comparison_request_module(text, normalize_whitespace_func=normalize_whitespace)


def is_recommendation_request(text: str) -> bool:
    return _is_recommendation_request_module(text, normalize_whitespace_func=normalize_whitespace)


def is_opinion_request(text: str) -> bool:
    return _is_opinion_request_module(text, normalize_whitespace_func=normalize_whitespace)


def should_include_event_context(user_text: str) -> bool:
    return _should_include_event_context_module(user_text, normalize_whitespace_func=normalize_whitespace)


def detect_runtime_query(user_text: str) -> bool:
    return _detect_runtime_query_module(user_text, normalize_whitespace_func=normalize_whitespace)


def is_explicit_runtime_probe_request(user_text: str) -> bool:
    lowered = normalize_whitespace(user_text).lower()
    if not lowered:
        return False
    explicit_markers = (
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
    return any(marker in lowered for marker in explicit_markers)


def detect_intent(user_text: str) -> str:
    return _detect_intent_module(user_text, normalize_whitespace_func=normalize_whitespace)


def is_explicit_help_request(text: str) -> bool:
    return _is_explicit_help_request_module(text, normalize_whitespace_func=normalize_whitespace)


def response_shape_hint(intent: str) -> str:
    return _response_shape_hint_module(intent)


def should_use_web_research(text: str) -> bool:
    return _should_use_web_research_module(text, normalize_whitespace_func=normalize_whitespace)


def classify_request_kind(
    user_text: str,
    *,
    user_id: Optional[int],
    assistant_persona: str,
    reply_context: str,
) -> str:
    return _classify_request_kind_module(
        user_text,
        user_id=user_id,
        assistant_persona=assistant_persona,
        reply_context=reply_context,
        deps=_build_router_runtime_deps(),
    )


def analyze_request_route(
    user_text: str,
    assistant_persona: str,
    chat_type: str,
    user_id: Optional[int] = None,
    reply_context: str = "",
) -> RouteDecision:
    return _analyze_request_route_module(
        user_text,
        assistant_persona,
        chat_type,
        user_id=user_id,
        reply_context=reply_context,
        deps=_build_router_runtime_deps(),
    )


def build_route_summary_text(route_info: RouteDecision) -> str:
    return _build_route_summary_text(route_info)


def build_guardrail_note(route_info: RouteDecision) -> str:
    return _build_guardrail_note(route_info)


def classify_answer_outcome(answer: str) -> str:
    return _classify_answer_outcome(answer)


def has_freshness_marker(text: str) -> bool:
    return _has_freshness_marker(text, FRESHNESS_MARKERS)


def apply_self_check_contract(
    answer: str,
    route_decision: RouteDecision,
    *,
    execution_trace: Optional[ExecutionTrace] = None,
) -> SelfCheckReport:
    return _apply_self_check_contract(
        answer,
        route_decision,
        execution_trace=execution_trace,
        normalize_whitespace_func=normalize_whitespace,
        freshness_markers=FRESHNESS_MARKERS,
        has_freshness_marker_func=_has_freshness_marker,
        classify_answer_outcome_func=_classify_answer_outcome,
        self_check_factory=SelfCheckReport,
    )


def render_route_diagnostics_rows(rows: List[sqlite3.Row]) -> str:
    return _render_route_diagnostics_rows(rows, truncate_text)


def render_resource_summary() -> str:
    return _render_resource_summary(
        psutil_module=psutil,
        format_bytes_func=format_bytes,
        format_swap_line_func=format_swap_line,
        extract_meminfo_value_func=extract_meminfo_value,
        display_timezone=DISPLAY_TIMEZONE,
    )


def render_enterprise_runtime_report() -> str:
    return _render_enterprise_runtime_report(
        psutil_module=psutil,
        format_bytes_func=format_bytes,
        format_swap_line_func=format_swap_line,
        truncate_text_func=truncate_text,
        build_subprocess_env_func=build_subprocess_env,
        render_bridge_runtime_watch_func=render_bridge_runtime_watch,
        display_timezone=DISPLAY_TIMEZONE,
    )


def render_top_processes(limit: int = 8) -> str:
    return _render_top_processes(
        psutil_module=psutil,
        format_bytes_func=format_bytes,
        truncate_text_func=truncate_text,
        limit=limit,
    )


def render_disk_summary() -> str:
    return _render_disk_summary(format_bytes)


def render_network_summary() -> str:
    return _render_network_summary(psutil_module=psutil, format_bytes_func=format_bytes)


def render_bridge_runtime_watch() -> str:
    script_dir = Path(__file__).resolve().parent
    heartbeat_path = Path(os.getenv("HEARTBEAT_PATH", DEFAULT_HEARTBEAT_PATH).strip() or DEFAULT_HEARTBEAT_PATH)
    if not heartbeat_path.is_absolute():
        heartbeat_path = script_dir / heartbeat_path
    bridge_log_path = script_dir / "tg_codex_bridge.log"
    supervisor_log_path = script_dir / "supervisor_boot.log"
    return _render_bridge_runtime_watch(
        psutil_module=psutil,
        format_bytes_func=format_bytes,
        truncate_text_func=truncate_text,
        heartbeat_path=heartbeat_path,
        bridge_log_path=bridge_log_path,
        supervisor_log_path=supervisor_log_path,
        runtime_log_snapshot=inspect_runtime_log(bridge_log_path),
    )


def format_swap_line() -> str:
    return _format_swap_line(psutil_module=psutil, format_bytes_func=format_bytes)


def extract_meminfo_value(text: str, key: str) -> Optional[int]:
    return _extract_meminfo_value(text, key)


def format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def postprocess_answer(text: str, latency_ms: Optional[int] = None) -> str:
    return _postprocess_answer(
        text,
        latency_ms=latency_ms,
        normalize_whitespace_func=normalize_whitespace,
        trim_generic_followup_func=trim_generic_followup,
        truncate_text_func=truncate_text,
        display_timezone=DISPLAY_TIMEZONE,
        max_output_chars=MAX_CODEX_OUTPUT_CHARS,
    )


def strip_banned_openers(text: str) -> str:
    return _strip_banned_openers(text)


def strip_meta_reply_wrapper(text: str) -> str:
    return _strip_meta_reply_wrapper(text)


def collapse_duplicate_answer_blocks(text: str) -> str:
    return _collapse_duplicate_answer_blocks(text)


def trim_generic_followup(text: str) -> str:
    return _trim_generic_followup(text)


def normalize_whitespace(text: str) -> str:
    return _normalize_whitespace(text)


def truncate_text(text: str, limit: int) -> str:
    return _truncate_text(text, limit)


def split_long_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    return _split_long_message(text, limit)


def build_download_name(file_path: str, fallback_name: str) -> str:
    return _build_download_name(file_path, fallback_name)


def build_voice_transcription_help(config: BotConfig) -> str:
    return _build_voice_transcription_help(
        tmp_dir=config.tmp_dir,
        stt_backend=config.stt_backend,
        audio_transcribe_model=config.audio_transcribe_model,
        openai_api_key_present=bool(config.openai_api_key),
    )


def build_subprocess_env() -> dict:
    env = os.environ.copy()
    if (env.get("STT_BACKEND", "").strip().lower() or "disabled") == "disabled":
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)
        env.pop("AUDIO_TRANSCRIBE_MODEL", None)
    current = env.get("LD_LIBRARY_PATH", "")
    if TERMUX_LIB_DIR not in current.split(":"):
        env["LD_LIBRARY_PATH"] = f"{TERMUX_LIB_DIR}:{current}" if current else TERMUX_LIB_DIR
    nvm_default_bin = Path("/home/userland/.nvm/versions/node/v18.20.8/bin")
    if nvm_default_bin.exists():
        current_path = env.get("PATH", "")
        path_parts = current_path.split(":") if current_path else []
        nvm_bin_str = str(nvm_default_bin)
        if nvm_bin_str not in path_parts:
            env["PATH"] = f"{nvm_bin_str}:{current_path}" if current_path else nvm_bin_str
    return env


def cleanup_temp_file(path: Path) -> None:
    try:
        _cleanup_temp_file(path)
    except OSError as error:
        log(f"temp cleanup failed for {path}: {error}")


def ensure_telegram_ok(response: Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        description = payload.get("description") or response.text
        raise RequestException(f"telegram http {response.status_code}: {description}")
    if not payload.get("ok"):
        raise RequestException(f"telegram api error: {payload}")


def is_message_not_modified_error(error: Exception) -> bool:
    message = str(error).lower()
    return "message is not modified" in message


def is_telegram_parse_mode_error(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "can't parse entities",
        "cannot parse entities",
        "unsupported start tag",
        "unexpected end tag",
        "tag was not found",
    )
    return any(marker in message for marker in markers)


def is_message_edit_recoverable_error(error: Exception) -> bool:
    message = str(error).lower()
    recoverable_markers = (
        "message to edit not found",
        "message can't be edited",
        "message can' t be edited",
        "there is no text in the message to edit",
    )
    return any(marker in message for marker in recoverable_markers)


INSTANCE_LOCK_HANDLE = None
EXIT_REASON = "normal"
LOCK_CONFLICT_EXIT_CODE = 75


def acquire_instance_lock(lock_path: str):
    lock_file = Path(lock_path).expanduser()
    handle = lock_file.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError(
            "Another tg_codex_bridge.py instance is already running. "
            "Single-instance lock is active; stop the old process before starting a new one."
        )
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def shorten_for_log(text: str, limit: int = 160) -> str:
    return truncate_text(" ".join((text or "").split()), limit)


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def log_exception(context: str, error: BaseException, limit: int = 8) -> None:
    details = traceback.format_exc(limit=max(1, limit))
    log(f"{context}: {error}\n{details}")


def handle_termination_signal(signum, _frame) -> None:
    global EXIT_REASON
    signal_name = signal.Signals(signum).name if signum else str(signum)
    EXIT_REASON = f"signal:{signal_name}"
    log(f"received termination signal: {signal_name}")
    raise SystemExit(0)


def main() -> None:
    global INSTANCE_LOCK_HANDLE, EXIT_REASON
    signal.signal(signal.SIGTERM, handle_termination_signal)
    signal.signal(signal.SIGINT, handle_termination_signal)
    config = BotConfig()
    try:
        INSTANCE_LOCK_HANDLE = acquire_instance_lock(config.lock_path)
    except RuntimeError as error:
        EXIT_REASON = "startup:instance_lock_conflict"
        log(f"instance lock conflict lock_path={config.lock_path}: {error}")
        raise SystemExit(LOCK_CONFLICT_EXIT_CODE)
    log(
        "config loaded "
        f"mode={config.default_mode} history_limit={config.history_limit} "
        f"owner_only=yes safe_chat_only={config.safe_chat_only} stt_backend={config.stt_backend} db_path={config.db_path} "
        f"lock_path={config.lock_path} codex_timeout={config.codex_timeout}s"
    )
    try:
        TelegramBridge(config).run()
    finally:
        log(f"process exiting reason={EXIT_REASON}")


if __name__ == "__main__":
    main()
