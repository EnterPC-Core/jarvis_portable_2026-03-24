#!/usr/bin/env python3
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("BOT_TOKEN", "smoke-check-token")

    import tg_codex_bridge as bridge
    from services.auto_moderation import detect_auto_moderation_decision, get_group_rules_text
    from services.diagnostics_metrics import collect_diagnostics_metrics, render_diagnostics_metrics
    from services.failure_detectors import detect_failure_signals
    from services.repair_playbooks import select_playbooks_for_signals
    from pipeline.context_pipeline import ContextPipeline

    state = bridge.BridgeState(
        bridge.DEFAULT_HISTORY_LIMIT,
        bridge.DEFAULT_MODE_NAME,
        str(ROOT / bridge.DEFAULT_DB_PATH),
    )
    try:
        snapshot = state.get_status_snapshot(bridge.OWNER_USER_ID)
        metrics = collect_diagnostics_metrics(state, window_seconds=3600)
        if "Quality diagnostics" not in render_diagnostics_metrics(metrics):
            raise RuntimeError("diagnostics metrics renderer regressed")
        metric_keys = {
            "total_requests",
            "verified_count",
            "inferred_count",
            "insufficient_count",
            "degraded_count",
            "live_stale_count",
            "runtime_probe_count",
            "prevented_false_claim_count",
        }
        if not metric_keys.issubset(metrics.__dict__.keys()):
            raise RuntimeError("diagnostics metrics shape regressed")
        required_keys = {
            "events_count",
            "facts_count",
            "history_count",
            "user_memory_profiles",
            "summary_snapshots",
            "relation_memory_rows",
        }
        missing = required_keys.difference(snapshot.keys())
        if missing:
            raise RuntimeError(f"status snapshot keys missing: {sorted(missing)}")
        self_model = state.get_self_model_state()
        if not self_model["identity"]:
            raise RuntimeError("self_model_state identity is empty")
        if len(state.get_drive_scores()) != len(bridge.DRIVE_NAMES):
            raise RuntimeError("drive_scores not initialized")
        if not bridge.has_chat_access(set(), bridge.OWNER_USER_ID):
            raise RuntimeError("owner access check failed")
        if bridge.has_chat_access(set(), bridge.OWNER_USER_ID + 1):
            raise RuntimeError("non-owner access check failed")
        if bridge.parse_mode_command("/mode jarvis") != "jarvis":
            raise RuntimeError("mode command adapter regressed")
        if "JARVIS" not in bridge.build_help_panel_text("public"):
            raise RuntimeError("help panel text wrapper regressed")
        if "inline_keyboard" not in bridge.build_help_panel_markup("public"):
            raise RuntimeError("help panel markup wrapper regressed")
        route = bridge.analyze_request_route(
            "Jarvis какая погода в Москве",
            assistant_persona="jarvis",
            chat_type="private",
            user_id=bridge.OWNER_USER_ID,
            reply_context="",
        )
        if route.route_kind != "live_weather" or not route.use_live:
            raise RuntimeError(f"unexpected weather route: {route}")
        web_route = bridge.analyze_request_route(
            "Jarvis изучи отзывы по этой ссылке https://example.com/item",
            assistant_persona="jarvis",
            chat_type="private",
            user_id=bridge.OWNER_USER_ID,
            reply_context="",
        )
        if not web_route.use_web or web_route.use_live:
            raise RuntimeError(f"unexpected web route: {web_route}")
        project_audit_route = bridge.analyze_request_route(
            "Enterprise проанализируй проект и улучши 3 критичных зоны: строгий роутинг запросов про current/latest/кто сейчас",
            assistant_persona="enterprise",
            chat_type="supergroup",
            user_id=bridge.OWNER_USER_ID,
            reply_context="",
        )
        if project_audit_route.route_kind != "codex_workspace" or project_audit_route.use_live or project_audit_route.use_web:
            raise RuntimeError(f"project audit route regressed: {project_audit_route}")
        local_incident_route = bridge.analyze_request_route(
            "Давай сначала, ты удалил сообщение, потом написал JARVIS: сообщение удалено. OLEG id=1870338495, предупреждение за нарушение правил: оскорбления JARVIS. Дальше изучи и дай ответ.",
            assistant_persona="jarvis",
            chat_type="supergroup",
            user_id=bridge.OWNER_USER_ID,
            reply_context="",
        )
        if local_incident_route.use_web or local_incident_route.use_live or not local_incident_route.use_database:
            raise RuntimeError(f"local incident route regressed: {local_incident_route}")
        if not bridge.is_query_too_broad_for_external_search("найди все ответы"):
            raise RuntimeError("broad search guard did not trigger")
        if bridge.is_query_too_broad_for_external_search("новости по NVIDIA за последние сутки"):
            raise RuntimeError("broad search guard blocked a concrete news query")
        if not bridge.is_direct_url_antibot_block(
            "https://ozon.ru/t/test",
            "Antibot Captcha",
            "",
            response_text="Access denied by antibot",
        ):
            raise RuntimeError("direct url antibot detection did not trigger")
        if not bridge.is_explicit_help_request("Подскажите, что делать с этой ошибкой?"):
            raise RuntimeError("explicit help request detector did not trigger")
        if bridge.is_explicit_help_request("ну бывает"):
            raise RuntimeError("explicit help request detector is too broad")
        if bridge.compute_group_spontaneous_reply_score("Подскажите, что делать с этой ошибкой?") < 3:
            raise RuntimeError("group spontaneous reply score too low for clear help request")
        smartphone_help = (
            "Приветствую чат. Помогите с выбором смартфона. Бюджет до 50000. "
            "За эту цену хотелось бы получить хорошую производительность для игр, "
            "хорошую основную камеру, хорошую энергоэффективность. "
            "Где покупать не имеет значения. Заранее благодарен за помощь в выборе."
        )
        if not bridge.is_purchase_advice_request(smartphone_help):
            raise RuntimeError("purchase advice detector did not trigger")
        if bridge.detect_intent(smartphone_help) != "purchase_advice":
            raise RuntimeError("purchase advice intent was not selected")
        comparison_text = "Сравни, что круче oppo find x9 ultra или vivo x300 ultra?"
        if not bridge.is_comparison_request(comparison_text):
            raise RuntimeError("comparison detector did not trigger")
        if bridge.detect_intent(comparison_text) != "comparison_request":
            raise RuntimeError("comparison intent was not selected")
        if bridge.detect_news_query(comparison_text):
            raise RuntimeError("comparison request incorrectly triggered news route")
        recommendation_text = "Посоветуйте хороший сериал на вечер"
        if not bridge.is_recommendation_request(recommendation_text):
            raise RuntimeError("recommendation detector did not trigger")
        if bridge.detect_intent(recommendation_text) != "recommendation_request":
            raise RuntimeError("recommendation intent was not selected")
        troubleshooting_text = "Помогите, пожалуйста, разобраться: почему ноутбук сильно греется?"
        if bridge.detect_intent(troubleshooting_text) != "troubleshooting_help":
            raise RuntimeError("troubleshooting intent was not selected")
        opinion_text = "Как думаешь, есть смысл брать iPhone 17 сейчас?"
        if bridge.detect_intent(opinion_text) != "opinion_request":
            raise RuntimeError("opinion intent was not selected")
        owner_prompt = bridge.build_prompt(
            mode=bridge.DEFAULT_MODE_NAME,
            history=[],
            user_text="Проверь, как ты относишься к сообщению владельца",
            owner_note=bridge.OWNER_PRIORITY_NOTE,
        )
        if "Owner priority note:" not in owner_prompt:
            raise RuntimeError("owner priority note was not injected into prompt")
        if "максимальный приоритет" not in bridge.OWNER_PRIORITY_NOTE.lower():
            raise RuntimeError("owner priority note is too weak")
        if "beta" not in bridge.START_TEXT.lower():
            raise RuntimeError("start text does not mention beta mode")
        signals = detect_failure_signals(
            runtime_snapshot={"restart_count": 4, "last_restart_at": 1, "heartbeat_kill_count": 0, "warning_count": 0, "severe_error_count": 0},
            recent_errors=[],
            recent_routes=[],
            heartbeat_timeout_seconds=90,
            now_ts=100,
        )
        playbooks = select_playbooks_for_signals(signals)
        if not any(signal.signal_code == "restart_loop" for signal in signals):
            raise RuntimeError("failure detector did not emit restart_loop signal")
        if not any(playbook.playbook_id == "restart_bridge_runtime" for playbook in playbooks):
            raise RuntimeError("repair playbook selector did not return restart_bridge_runtime")
        if "не абсолютная истина" not in bridge.PUBLIC_HOME_TEXT.lower():
            raise RuntimeError("public home text does not mention beta caution")
        all_pedals_rules = get_group_rules_text("Все педали!")
        if "Правила чата «Все педали!»" not in all_pedals_rules:
            raise RuntimeError("all pedals rules text was not selected")
        if "оскорблен" not in all_pedals_rules.lower():
            raise RuntimeError("rules text looks incomplete")
        if bridge.compute_group_spontaneous_reply_score(smartphone_help) < 4:
            raise RuntimeError("structured shopping help request score too low")
        if bridge.should_use_web_research(smartphone_help):
            raise RuntimeError("product selection help should not trigger automatic web research")
        if not bridge.should_use_web_research("Найди лучшие смартфоны до 50000 и что пишут в интернете"):
            raise RuntimeError("explicit product web research should stay enabled")
        bot_abuse_decision = detect_auto_moderation_decision(
            message={
                "text": "Jarvis, ты тупой бот",
                "from": {"id": 7777, "first_name": "Нарушитель"},
                "reply_to_message": {"from": {"id": 7913608051, "is_bot": True}},
            },
            raw_text="Jarvis, ты тупой бот",
            recent_texts=["jarvis, ты тупой бот"],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        )
        if bot_abuse_decision is None or bot_abuse_decision.action != "warn":
            raise RuntimeError("bot abuse moderation did not trigger warn")
        participant_abuse_decision = detect_auto_moderation_decision(
            message={
                "text": "Ты дебил, иди нахер",
                "from": {"id": 7777, "first_name": "Нарушитель"},
                "reply_to_message": {"from": {"id": 8888, "first_name": "Жертва", "is_bot": False}},
            },
            raw_text="Ты дебил, иди нахер",
            recent_texts=["ты дебил, иди нахер"],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        )
        if participant_abuse_decision is None or participant_abuse_decision.action != "mute":
            raise RuntimeError("severe participant abuse moderation did not trigger mute")
        spam_decision = detect_auto_moderation_decision(
            message={"text": "Купи айфон срочно", "from": {"id": 7777, "first_name": "Спамер"}},
            raw_text="Купи айфон срочно",
            recent_texts=["купи айфон срочно", "купи айфон срочно", "купи айфон срочно"],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        )
        if spam_decision is None or spam_decision.code != "repeated_spam":
            raise RuntimeError("repeated spam moderation did not trigger")
        veiled_bot_abuse = detect_auto_moderation_decision(
            message={
                "text": "Тебя обласкать, недоразвитая сето? Иди сюда, светило-жопедрило..",
                "from": {"id": 7777, "first_name": "Нарушитель"},
                "reply_to_message": {"from": {"id": 7913608051, "is_bot": True}},
            },
            raw_text="Тебя обласкать, недоразвитая сето? Иди сюда, светило-жопедрило..",
            recent_texts=["тебя обласкать, недоразвитая сето? иди сюда, светило-жопедрило.."],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        )
        if veiled_bot_abuse is None or veiled_bot_abuse.action not in {"warn", "mute"}:
            raise RuntimeError("veiled bot abuse did not trigger moderation")
        challenged_moderation = detect_auto_moderation_decision(
            message={
                "text": "Jarvis, да это разве оскорбления?",
                "from": {"id": 7777, "first_name": "Нарушитель"},
                "reply_to_message": {"from": {"id": 7913608051, "is_bot": True}},
            },
            raw_text="Jarvis, да это разве оскорбления?",
            recent_texts=[
                "тебя обласкать, недоразвитая сето? иди сюда, светило-жопедрило..",
                "ща будет тебе адресный высер",
                "jarvis, да это разве оскорбления?",
            ],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        )
        if challenged_moderation is None or challenged_moderation.action != "mute":
            raise RuntimeError("moderation challenge after toxic streak did not trigger mute")
        if bridge.strip_meta_reply_wrapper("Текст для отправки в чат: Привет") != "Привет":
            raise RuntimeError("meta reply wrapper was not stripped")
        duplicated = "Связь есть.\n\nСвязь есть."
        if bridge.collapse_duplicate_answer_blocks(duplicated) != "Связь есть.":
            raise RuntimeError("duplicate answer blocks were not collapsed")
        bot = bridge.TelegramBridge(bridge.BotConfig())
        try:
            if "JARVIS" not in bot.build_help_panel_text("public"):
                raise RuntimeError("bridge help panel adapter regressed")
            if "inline_keyboard" not in bot.build_help_panel_markup("public"):
                raise RuntimeError("bridge help panel markup adapter regressed")
            public_panel_text, public_panel_markup = bot.build_control_panel(bridge.OWNER_USER_ID + 1, "home")
            if "JARVIS" not in public_panel_text or "inline_keyboard" not in public_panel_markup:
                raise RuntimeError("public control panel renderer regressed")
            owner_panel_text, owner_panel_markup = bot.build_control_panel(bridge.OWNER_USER_ID, "owner_root")
            if "OWNER PANEL" not in owner_panel_text or "inline_keyboard" not in owner_panel_markup:
                raise RuntimeError("owner control panel renderer regressed")
            owner_report_text = bot.render_owner_report_text(bridge.OWNER_USER_ID)
            if "Quality diagnostics" not in owner_report_text:
                raise RuntimeError("owner report diagnostics section regressed")
            sent_messages: list[str] = []
            original_safe_send_text = bot.safe_send_text

            def _capture_safe_send_text(chat_id: int, text: str, *args, **kwargs):
                sent_messages.append(text)
                return {"ok": True, "chat_id": chat_id, "text": text}

            bot.safe_send_text = _capture_safe_send_text
            try:
                if not bot.handle_quality_report_command(bridge.OWNER_USER_ID, bridge.OWNER_USER_ID):
                    raise RuntimeError("quality report command was not handled")
            finally:
                bot.safe_send_text = original_safe_send_text
            if not sent_messages or "QUALITY REPORT" not in sent_messages[-1]:
                raise RuntimeError("quality report command renderer regressed")
            if not bot.should_process_group_message(
                {
                    "text": "Jarvis?",
                    "from": {"id": bridge.OWNER_USER_ID, "first_name": "Дмитрий"},
                    "chat": {"id": -1003879607896, "type": "supergroup"},
                },
                "Jarvis?",
            ):
                raise RuntimeError("bridge group trigger adapter regressed")
            pipeline = ContextPipeline()
            bundle = pipeline.build_text_context_bundle(
                bot,
                chat_id=bridge.OWNER_USER_ID,
                user_text="Привет",
                route_decision=bridge.analyze_request_route(
                    "Привет",
                    assistant_persona="jarvis",
                    chat_type="private",
                    user_id=bridge.OWNER_USER_ID,
                    reply_context="",
                ),
                user_id=bridge.OWNER_USER_ID,
                message={
                    "message_id": 1,
                    "text": "Привет",
                    "from": {"id": bridge.OWNER_USER_ID, "first_name": "Дмитрий"},
                    "chat": {"id": bridge.OWNER_USER_ID, "type": "private"},
                },
                reply_context="",
                active_group_followup=False,
            )
            if bundle is None or not hasattr(bundle, "summary_text"):
                raise RuntimeError("context pipeline adapter regressed")
        finally:
            bot.state.db.close()
        followup_message = {
            "text": "А что лучше из этих двух?",
            "from": {"id": 7104783736, "username": "maksim_vlasov_71", "first_name": "Максим"},
            "reply_to_message": {"from": {"id": 7913608051, "is_bot": True, "username": "test_aipc_bot"}},
        }
        neutral_followup_message = {
            "text": "Да, понял",
            "from": {"id": 7104783736, "username": "maksim_vlasov_71", "first_name": "Максим"},
        }
        direct_help_reply = {
            "text": "Помоги, пожалуйста, разобраться в проблеме: хочу купить смартфон в районе 30к, что лучше купить?",
            "from": {"id": 7087071466, "username": "enterpc", "first_name": "EnterPC"},
            "reply_to_message": {"message_id": 777, "from": {"id": 7913608051, "is_bot": True, "username": "test_aipc_bot"}},
            "chat": {"id": -1003879607896, "type": "supergroup"},
        }
        second_participant_reply = {
            "text": "А если нужен акцент на камеру, что тогда лучше?",
            "from": {"id": 704771331, "username": "another_user", "first_name": "Артем"},
            "reply_to_message": {"message_id": 778, "from": {"id": 7913608051, "is_bot": True, "username": "test_aipc_bot"}},
            "chat": {"id": -1003879607896, "type": "supergroup"},
        }
        neutral_second_participant = {
            "text": "Да, нормально",
            "from": {"id": 704771331, "username": "another_user", "first_name": "Артем"},
            "chat": {"id": -1003879607896, "type": "supergroup"},
        }
        unrelated_second_participant = {
            "text": "А кто вчера матч смотрел?",
            "from": {"id": 704771331, "username": "another_user", "first_name": "Артем"},
            "chat": {"id": -1003879607896, "type": "supergroup"},
        }
        parallel_branch_reply = {
            "text": "А если упор на камеру, что лучше?",
            "from": {"id": 704771331, "username": "another_user", "first_name": "Артем"},
            "reply_to_message": {"message_id": 901, "from": {"id": 7999, "username": "oleg", "first_name": "Олег"}},
            "chat": {"id": -1003879607896, "type": "supergroup"},
        }
        bot = bridge.TelegramBridge(bridge.BotConfig())
        try:
            test_chat_id = -100999000111
            with bot.state.db_lock:
                bot.state.set_meta(f"group_spontaneous_reply_last_ts:{test_chat_id}", "0")
                bot.state.set_meta(f"group_spontaneous_reply_last_message_id:{test_chat_id}", "")
                bot.state.set_meta("group_discussion_state:-1003879607896", "")
                bot.state.set_meta("group_discussion_turn_count:-1003879607896:7104783736", "0")
                bot.state.set_meta("group_discussion_block_until:-1003879607896:7104783736", "0")
            if not bot.try_claim_group_spontaneous_reply_slot(test_chat_id, 1):
                raise RuntimeError("group spontaneous reply slot was not claimed on first try")
            if bot.try_claim_group_spontaneous_reply_slot(test_chat_id, 2):
                raise RuntimeError("group spontaneous reply cooldown did not block second claim")
            bot.grant_group_followup_window(-1003879607896, 7104783736)
            if not bot.is_group_followup_message(-1003879607896, followup_message, followup_message["text"]):
                raise RuntimeError("group followup window did not allow a tagged follow-up")
            if bot.is_group_followup_message(-1003879607896, neutral_followup_message, neutral_followup_message["text"]):
                raise RuntimeError("group followup window allowed neutral chatter")
            if not bot.is_ambient_group_chatter(neutral_followup_message, neutral_followup_message["text"]):
                raise RuntimeError("ambient chatter detector did not flag neutral text")
            if not bot.is_group_spontaneous_reply_candidate(-1003879607896, direct_help_reply, direct_help_reply["text"]):
                raise RuntimeError("direct group help reply candidate detector did not allow a clear help request")
            discussion_context = bot.build_current_discussion_context(
                -1003879607896,
                message=direct_help_reply,
                user_id=7087071466,
                active_group_followup=True,
            )
            if not discussion_context or "Discussion summary:" not in discussion_context:
                raise RuntimeError("group discussion context was not built")
            if "ranked selection from last 100 messages" not in discussion_context and "Focused active thread window:" not in discussion_context:
                raise RuntimeError("group discussion context did not include any recent/focused window")
            if "current_speaker:" not in discussion_context:
                raise RuntimeError("group discussion context did not include current speaker")
            if "active_participants:" not in discussion_context:
                raise RuntimeError("group discussion context did not include active participants")
            if "Current speaker recent messages:" not in discussion_context:
                raise RuntimeError("group discussion context did not include current speaker recent messages")
            bot.mark_active_group_discussion(-1003879607896, 7087071466, direct_help_reply)
            if "active_discussion: yes" not in bot.get_group_discussion_state_hint(-1003879607896):
                raise RuntimeError("group discussion state hint was not created")
            if not bot.is_group_discussion_continuation(-1003879607896, second_participant_reply, second_participant_reply["text"]):
                raise RuntimeError("second participant was not allowed to continue active discussion")
            if bot.is_group_discussion_continuation(-1003879607896, neutral_second_participant, neutral_second_participant["text"]):
                raise RuntimeError("neutral group chatter incorrectly continued bot discussion")
            if bot.is_group_discussion_continuation(-1003879607896, unrelated_second_participant, unrelated_second_participant["text"]):
                raise RuntimeError("unrelated second-participant topic incorrectly continued bot discussion")
            if bot.is_group_discussion_continuation(-1003879607896, parallel_branch_reply, parallel_branch_reply["text"]):
                raise RuntimeError("parallel human reply branch incorrectly continued bot discussion")
            if bot.get_group_participant_priority(-1003879607896, direct_help_reply) != "reply_to_bot":
                raise RuntimeError("participant priority for first external help request is unexpected")
        finally:
            bot.state.db.close()
        print("smoke-check: ok")
        return 0
    finally:
        state.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
