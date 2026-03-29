#!/usr/bin/env python3
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("BOT_TOKEN", "behavioral-check-token")

    import tg_codex_bridge as bridge
    from services.auto_moderation import detect_auto_moderation_decision

    bot = bridge.TelegramBridge(bridge.BotConfig())
    try:
        chat_id = -100555000111
        help_message = {
            "message_id": 101,
            "text": "Подскажите, что лучше выбрать: смартфон до 50000 для игр и камеры?",
            "from": {"id": 7001, "username": "max", "first_name": "Максим"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        neutral_message = {
            "message_id": 102,
            "text": "Ну да, бывает",
            "from": {"id": 7002, "username": "ivan", "first_name": "Иван"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        followup_message = {
            "message_id": 103,
            "text": "А что лучше из этих двух?",
            "from": {"id": 7001, "username": "max", "first_name": "Максим"},
            "chat": {"id": chat_id, "type": "supergroup"},
            "reply_to_message": {"message_id": 500, "from": {"id": 7913608051, "is_bot": True, "username": "test_aipc_bot"}},
        }
        neutral_followup = {
            "message_id": 104,
            "text": "Понял, спасибо",
            "from": {"id": 7001, "username": "max", "first_name": "Максим"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        second_participant_join = {
            "message_id": 105,
            "text": "А если нужен упор на камеру, что тогда лучше?",
            "from": {"id": 7003, "username": "irina", "first_name": "Ирина"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        neutral_second_participant = {
            "message_id": 106,
            "text": "Да, я тоже так думаю",
            "from": {"id": 7003, "username": "irina", "first_name": "Ирина"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        unrelated_second_participant = {
            "message_id": 107,
            "text": "А кто смотрел матч вчера?",
            "from": {"id": 7003, "username": "irina", "first_name": "Ирина"},
            "chat": {"id": chat_id, "type": "supergroup"},
        }
        parallel_branch_reply = {
            "message_id": 108,
            "text": "А если упор на камеру, что лучше?",
            "from": {"id": 7003, "username": "irina", "first_name": "Ирина"},
            "chat": {"id": chat_id, "type": "supergroup"},
            "reply_to_message": {"message_id": 900, "from": {"id": 7999, "username": "other_user", "first_name": "Олег"}},
        }
        bot_abuse_message = {
            "message_id": 109,
            "text": "Jarvis, ты тупой бот",
            "from": {"id": 7004, "username": "toxic", "first_name": "Токсик"},
            "chat": {"id": chat_id, "type": "supergroup", "title": "Все педали!"},
            "reply_to_message": {"message_id": 501, "from": {"id": 7913608051, "is_bot": True}},
        }
        participant_abuse_message = {
            "message_id": 110,
            "text": "Ты дебил, иди нахер",
            "from": {"id": 7004, "username": "toxic", "first_name": "Токсик"},
            "chat": {"id": chat_id, "type": "supergroup", "title": "Все педали!"},
            "reply_to_message": {"message_id": 777, "from": {"id": 7003, "is_bot": False, "first_name": "Ирина"}},
        }
        veiled_bot_abuse = {
            "message_id": 111,
            "text": "Тебя обласкать, недоразвитая сето? Иди сюда, светило-жопедрило..",
            "from": {"id": 7004, "username": "toxic", "first_name": "Токсик"},
            "chat": {"id": chat_id, "type": "supergroup", "title": "Все педали!"},
            "reply_to_message": {"message_id": 778, "from": {"id": 7913608051, "is_bot": True}},
        }
        challenge_after_toxic = {
            "message_id": 112,
            "text": "Jarvis, да это разве оскорбления?",
            "from": {"id": 7004, "username": "toxic", "first_name": "Токсик"},
            "chat": {"id": chat_id, "type": "supergroup", "title": "Все педали!"},
            "reply_to_message": {"message_id": 779, "from": {"id": 7913608051, "is_bot": True}},
        }

        with bot.state.db_lock:
            bot.state.set_meta(f"group_spontaneous_reply_last_ts:{chat_id}", "0")
            bot.state.set_meta(f"group_spontaneous_reply_last_message_id:{chat_id}", "")
            bot.state.set_meta(f"group_discussion_state:{chat_id}", "")
            bot.state.set_meta(f"group_discussion_turn_count:{chat_id}:7001", "0")
            bot.state.set_meta(f"group_discussion_block_until:{chat_id}:7001", "0")
        for idx in range(90):
            bot.state.record_event(
                chat_id,
                6000 + idx,
                "user",
                "text",
                f"seed event {idx}",
                1000 + idx,
                username=f"user{idx}",
                first_name=f"User{idx}",
                last_name="",
                chat_type="supergroup",
            )

        if not bot.is_group_spontaneous_reply_candidate(chat_id, help_message, help_message["text"]):
            raise RuntimeError("clear help request was not accepted as candidate")
        if bot.is_group_spontaneous_reply_candidate(chat_id, neutral_message, neutral_message["text"]):
            raise RuntimeError("neutral chatter was accepted as spontaneous candidate")
        if not bot.is_ambient_group_chatter(neutral_message, neutral_message["text"]):
            raise RuntimeError("neutral chatter was not detected as ambient")

        bot.grant_group_followup_window(chat_id, 7001)
        if not bot.is_group_followup_message(chat_id, followup_message, followup_message["text"]):
            raise RuntimeError("explicit follow-up was not accepted")
        if bot.is_group_followup_message(chat_id, neutral_followup, neutral_followup["text"]):
            raise RuntimeError("neutral follow-up chatter was accepted")
        for _ in range(bot.config.group_discussion_max_turns_per_user):
            if not bot.record_group_discussion_turn(chat_id, 7001):
                raise RuntimeError("discussion turn budget exhausted too early")
        if bot.record_group_discussion_turn(chat_id, 7001):
            raise RuntimeError("discussion turn budget did not block excessive questions")
        if bot.is_group_followup_message(chat_id, followup_message, followup_message["text"]):
            raise RuntimeError("rate-limited participant still passed follow-up gate")

        bot.mark_active_group_discussion(chat_id, 7001, help_message)
        bot.mark_active_group_discussion(chat_id, 7001, followup_message)
        discussion_context = bot.build_current_discussion_context(
            chat_id,
            message=followup_message,
            user_id=7001,
            active_group_followup=True,
        )
        if "Focused active thread window (" not in discussion_context and "active_thread_keywords:" not in discussion_context:
            raise RuntimeError("thread-aware discussion context was not built")
        if not bot.is_group_discussion_continuation(chat_id, second_participant_join, second_participant_join["text"]):
            raise RuntimeError("meaningful second-participant join was not accepted")
        if bot.is_group_discussion_continuation(chat_id, neutral_second_participant, neutral_second_participant["text"]):
            raise RuntimeError("neutral second-participant chatter was accepted")
        if bot.is_group_discussion_continuation(chat_id, unrelated_second_participant, unrelated_second_participant["text"]):
            raise RuntimeError("unrelated second-participant topic was accepted")
        if bot.is_group_discussion_continuation(chat_id, parallel_branch_reply, parallel_branch_reply["text"]):
            raise RuntimeError("parallel human reply branch was accepted as bot discussion continuation")
        if bot.get_group_participant_priority(chat_id, help_message) != "active_participant":
            raise RuntimeError("initial help-message priority is unexpected")
        if bot.get_group_participant_priority(chat_id, followup_message) != "reply_to_bot":
            raise RuntimeError("reply-to-bot priority is unexpected")
        if detect_auto_moderation_decision(
            message=bot_abuse_message,
            raw_text=bot_abuse_message["text"],
            recent_texts=["jarvis, ты тупой бот"],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        ).action != "warn":
            raise RuntimeError("bot abuse did not route to warn in behavioral check")
        if detect_auto_moderation_decision(
            message=participant_abuse_message,
            raw_text=participant_abuse_message["text"],
            recent_texts=["ты дебил, иди нахер"],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        ).action != "mute":
            raise RuntimeError("participant abuse did not route to mute in behavioral check")
        if detect_auto_moderation_decision(
            message=veiled_bot_abuse,
            raw_text=veiled_bot_abuse["text"],
            recent_texts=[veiled_bot_abuse["text"].lower()],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        ).action not in {"warn", "mute"}:
            raise RuntimeError("veiled bot abuse did not route to moderation in behavioral check")
        if detect_auto_moderation_decision(
            message=challenge_after_toxic,
            raw_text=challenge_after_toxic["text"],
            recent_texts=[
                veiled_bot_abuse["text"].lower(),
                "ща будет тебе адресный высер",
                challenge_after_toxic["text"].lower(),
            ],
            chat_title="Все педали!",
            bot_username="Jarvis_3_0_bot",
            trigger_name="jarvis",
            contains_profanity_func=bridge.contains_profanity,
        ).action != "mute":
            raise RuntimeError("challenge after toxic streak did not route to mute in behavioral check")

        comparison_text = "Сравни, что круче oppo find x9 ultra или vivo x300 ultra?"
        if bridge.detect_intent(comparison_text) != "comparison_request":
            raise RuntimeError("comparison intent regression in behavioral check")
        if bridge.detect_news_query(comparison_text):
            raise RuntimeError("comparison request incorrectly routed to news in behavioral check")
        print("behavioral-check: ok")
        return 0
    finally:
        bot.state.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
