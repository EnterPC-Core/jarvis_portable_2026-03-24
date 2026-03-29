import unittest
from pathlib import Path

from prompts.builders import build_prompt
from prompts.profile_loader import load_runtime_profile, normalize_prompt_profile_name
from services.answer_postprocess import postprocess_answer
from tg_codex_bridge import build_owner_contact_reply
from utils.text_utils import trim_generic_followup


class PromptProfileTests(unittest.TestCase):
    def test_correct_profile_selection(self):
        self.assertEqual(load_runtime_profile("jarvis").name, "jarvis")
        self.assertEqual(load_runtime_profile("enterprise").name, "enterprise")

    def test_legacy_modes_collapse_to_jarvis(self):
        self.assertEqual(normalize_prompt_profile_name("code"), "jarvis")
        self.assertEqual(normalize_prompt_profile_name("strict"), "jarvis")
        self.assertEqual(normalize_prompt_profile_name("chat"), "jarvis")

    def test_jarvis_prompt_stays_concise(self):
        prompt = load_runtime_profile("jarvis").system_prompt
        self.assertIn("Ты Jarvis.", prompt)
        self.assertIn("Ты личный ассистент Дмитрия.", prompt)
        self.assertIn("Не выдавай сырую поисковую выдачу как финальный ответ.", prompt)
        self.assertIn("Если сообщение — простое приветствие", prompt)
        self.assertIn("Не дописывай в конце \"Следующий шаг\"", prompt)
        self.assertNotIn("один понятный следующий шаг", prompt)
        self.assertLess(len(prompt), 1250)

    def test_enterprise_prompt_stays_separate(self):
        jarvis = load_runtime_profile("jarvis").system_prompt
        enterprise = load_runtime_profile("enterprise").system_prompt
        self.assertIn("Ты Enterprise Core v194.95.", enterprise)
        self.assertIn("Ты профиль Дмитрия.", enterprise)
        self.assertIn("Не ври о выполненных действиях.", enterprise)
        self.assertIn("Всегда разделяй observed, inferred и unknown.", enterprise)
        self.assertNotEqual(jarvis, enterprise)
        self.assertNotIn("Ты Jarvis.", enterprise)

    def test_no_prompt_leakage_between_profiles(self):
        jarvis_prompt = build_prompt(
            mode="jarvis",
            history=[("user", "Привет")],
            user_text="Что нового?",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            persona_note="",
            owner_note="",
        )
        enterprise_prompt = build_prompt(
            mode="enterprise",
            history=[("user", "Проверь проект")],
            user_text="Проверь проект",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            persona_note="",
            owner_note="",
        )
        self.assertTrue(jarvis_prompt.startswith("Ты Jarvis.\n"))
        self.assertTrue(enterprise_prompt.startswith("Ты Enterprise Core v194.95.\n"))
        self.assertNotIn("Ты Enterprise.", jarvis_prompt)
        self.assertNotIn("Ты личный ассистент Дмитрия.", enterprise_prompt)
        self.assertNotIn("Persona note:", jarvis_prompt)
        self.assertNotIn("Owner priority note:", jarvis_prompt)
        self.assertNotIn("Identity:", jarvis_prompt)

    def test_enterprise_prompt_only_keeps_dm_context_user_profile_and_message(self):
        history = []
        for idx in range(1, 10):
            history.append(("user", f"старый контекст {idx}"))
            history.append(("assistant", f"промежуточный ответ {idx}"))
        prompt = build_prompt(
            mode="enterprise",
            history=history,
            user_text="Проверь это",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            attachment_note="attachment",
            summary_text="summary",
            facts_text="facts",
            event_context="events",
            database_context="database",
            reply_context="reply",
            discussion_context="discussion",
            web_context="web",
            route_summary="route",
            guardrail_note="guardrail",
            self_model_text="self-model",
            autobiographical_text="autobio",
            skill_memory_text="skills",
            world_state_text="world",
            drive_state_text="drives",
            user_memory_text="Дмитрий (owner)",
            relation_memory_text="relations",
            chat_memory_text="chat-memory",
            summary_memory_text="summary-memory",
        )
        self.assertIn("Ты Enterprise Core v194.95.", prompt)
        self.assertIn("User profile:\nДмитрий (owner)", prompt)
        self.assertIn("Relevant chat context:", prompt)
        self.assertIn("User: старый контекст 9", prompt)
        self.assertIn("Jarvis: промежуточный ответ 9", prompt)
        self.assertIn("User message:\nПроверь это", prompt)
        self.assertIn("Reply context:", prompt)
        self.assertNotIn("Route contract:", prompt)
        self.assertNotIn("Guardrails:", prompt)
        self.assertNotIn("Rolling summary:", prompt)
        self.assertIn("Facts:", prompt)
        self.assertIn("Discussion context:", prompt)
        self.assertIn("Event context:", prompt)
        self.assertIn("Database context:", prompt)
        self.assertNotIn("Relation memory:", prompt)
        self.assertNotIn("Chat memory:", prompt)
        self.assertNotIn("Summary memory:", prompt)

    def test_enterprise_prompt_keeps_wider_dm_history_window(self):
        history = []
        for idx in range(1, 15):
            history.append(("user", f"сообщение пользователя {idx}"))
            history.append(("assistant", f"ответ ассистента {idx}"))
        prompt = build_prompt(
            mode="enterprise",
            history=history,
            user_text="Проверь это",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            attachment_note="attachment",
            summary_text="summary",
            facts_text="facts",
            event_context="events",
            database_context="database",
            reply_context="reply",
            discussion_context="discussion",
            web_context="web",
            route_summary="route",
            guardrail_note="guardrail",
            self_model_text="self-model",
            autobiographical_text="autobio",
            skill_memory_text="skills",
            world_state_text="world",
            drive_state_text="drives",
            user_memory_text="Дмитрий (owner)",
            relation_memory_text="relations",
            chat_memory_text="chat-memory",
            summary_memory_text="summary-memory",
        )
        self.assertIn("User: сообщение пользователя 14", prompt)
        self.assertIn("Jarvis: ответ ассистента 14", prompt)
        self.assertIn("User: сообщение пользователя 12", prompt)

    def test_enterprise_prompt_uses_lighter_context_for_short_requests(self):
        history = []
        for idx in range(1, 15):
            history.append(("user", f"короткий вопрос {idx}"))
            history.append(("assistant", f"короткий ответ {idx}"))
        prompt = build_prompt(
            mode="enterprise",
            history=history,
            user_text="ты тут?",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            user_memory_text="Дмитрий (owner): " + ("x" * 1000),
        )
        self.assertIn("User: короткий вопрос 14", prompt)
        self.assertNotIn("User: короткий вопрос 10", prompt)
        self.assertLess(len(prompt), 1800)

    def test_jarvis_prompt_blocks_internal_architecture_talk(self):
        prompt = load_runtime_profile("jarvis").system_prompt
        self.assertIn("Ты не рассказываешь пользователю внутреннюю архитектуру", prompt)
        self.assertIn("Не показывай внутренние рассуждения", prompt)
        self.assertIn("Enterprise Core v194.95.", prompt)
        self.assertIn("Не упоминай внешние названия моделей или провайдеров", prompt)

    def test_prompt_builder_no_longer_injects_prompt_spaghetti_sections(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[("user", "Привет")],
            user_text="Что нового?",
            mode_prompts={"jarvis": "legacy"},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            route_summary="route details should not leak",
            guardrail_note="guardrails should not leak",
        )
        self.assertNotIn("Mode:\n", prompt)
        self.assertNotIn("Profile:\n", prompt)
        self.assertNotIn("Intent:\n", prompt)
        self.assertNotIn("Response shape:\n", prompt)
        self.assertNotIn("Route summary:\n", prompt)
        self.assertNotIn("Self-check and guardrails:\n", prompt)
        self.assertNotIn("Response contract:\n", prompt)
        self.assertNotIn("Route contract:\n", prompt)
        self.assertNotIn("Guardrails:\n", prompt)

    def test_chat_dynamics_prompt_includes_stronger_response_contract(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[("user", "Что происходит в чате?")],
            user_text="Расскажи про чат подробнее",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "chat_dynamics",
            response_shape_hint_func=lambda _intent: "Сначала коротко, потом блоки по участникам и динамике.",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            discussion_context="Discussion summary: ...",
            chat_memory_text="Chat memory: ...",
        )
        self.assertIn("Discussion context:\nDiscussion summary: ...", prompt)
        self.assertNotIn("Response contract:\n", prompt)

    def test_prompt_builder_ignores_owner_and_persona_fragments(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[],
            user_text="Привет",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            persona_note="legacy persona",
            owner_note="Owner priority note body",
        )
        self.assertNotIn("Owner priority note:", prompt)
        self.assertNotIn("Persona note:", prompt)
        self.assertNotIn("Identity:", prompt)

    def test_bridge_no_longer_contains_legacy_service_prompt_definitions(self):
        bridge_text = Path("/home/userland/projects/bots/jarvis_portable_2026-03-24/tg_codex_bridge.py").read_text()
        blocked_fragments = (
            "UPGRADE_REQUEST_TEMPLATE",
            "def build_upgrade_prompt",
            "def build_grammar_fix_prompt",
            "def build_voice_cleanup_prompt",
            "def build_voice_transcription_prompt",
            "def build_portrait_prompt",
            "def build_ai_chat_memory_prompt",
            "def build_ai_user_memory_prompt",
        )
        for fragment in blocked_fragments:
            self.assertNotIn(fragment, bridge_text)

    def test_simple_greeting_uses_minimal_prompt_path(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[("assistant", "Суть: ..."), ("user", "что нового")],
            user_text="Привет",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            reply_context="старый reply context",
        )
        self.assertIn("Ты Jarvis.", prompt)
        self.assertIn("User message:\nПривет", prompt)
        self.assertIn("Ответь естественно и коротко.", prompt)
        self.assertNotIn("Relevant chat context:", prompt)
        self.assertNotIn("Reply context:", prompt)

    def test_prompt_builder_includes_user_profile_when_present(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[("user", "Раньше говорили про проект")],
            user_text="Продолжим",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            user_memory_text="Дмитрий (owner): любит короткие ответы и часто пишет про проект.",
        )
        self.assertIn("User profile:", prompt)
        self.assertIn("Дмитрий (owner)", prompt)

    def test_prompt_builder_includes_discussion_and_memory_blocks_for_jarvis(self):
        prompt = build_prompt(
            mode="jarvis",
            history=[("user", "Что тут происходит"), ("assistant", "Смотрю контекст")],
            user_text="Jarvis, разложи по полочкам",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "general",
            response_shape_hint_func=lambda _intent: "short",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            reply_context="Ответ на сообщение Дмитрия (owner)",
            discussion_context="current_speaker: Дмитрий (owner)",
            facts_text="Факт: в чате сейчас обсуждают runtime.",
            event_context="Событие: owner ответил на алерт.",
            database_context="DB: найдено 3 релевантных записи.",
            task_context_text="attachment_analysis: status=tool_observed",
            memory_trace_text="Memory trace: reply_context -> chat_events -> user_memory",
            relation_memory_text="Дмитрий (owner) часто инициирует техпроверки.",
            chat_memory_text="В чате тестируют Jarvis и проверяют память.",
            summary_memory_text="ai_rollup: owner тестирует reply-aware поведение.",
        )
        self.assertIn("Facts:", prompt)
        self.assertIn("Event context:", prompt)
        self.assertIn("Database context:", prompt)
        self.assertIn("Reply context:", prompt)
        self.assertIn("Discussion context:", prompt)
        self.assertIn("Task continuity:", prompt)
        self.assertIn("Memory trace:", prompt)
        self.assertIn("Relation memory:", prompt)
        self.assertIn("Chat memory:", prompt)
        self.assertIn("Summary memory:", prompt)
        self.assertIn("Дмитрий (owner)", prompt)

    def test_prompt_builder_includes_database_event_and_task_blocks_for_enterprise(self):
        prompt = build_prompt(
            mode="enterprise",
            history=[("user", "Проверь runtime"), ("assistant", "Смотрю")],
            user_text="Покажи, что реально произошло с задачей",
            mode_prompts={},
            default_mode_name="jarvis",
            base_system_prompt="legacy should be ignored",
            detect_intent_func=lambda _text: "runtime",
            response_shape_hint_func=lambda _intent: "strict",
            truncate_text_func=lambda text, limit: text[:limit],
            max_history_item_chars=120,
            summary_text="Короткая сводка",
            facts_text="Факт: task_id=abc",
            event_context="event: queued -> finished",
            database_context="db: task_runs row found",
            reply_context="reply target present",
            discussion_context="owner requested audit",
            task_context_text="enterprise_route: status=tool_observed",
            memory_trace_text="Memory trace: database_context -> task_context",
            world_state_text="bridge_alive=yes",
            user_memory_text="owner prefers direct answers",
        )
        self.assertIn("Summary:", prompt)
        self.assertIn("Facts:", prompt)
        self.assertIn("Event context:", prompt)
        self.assertIn("Database context:", prompt)
        self.assertIn("Task continuity:", prompt)
        self.assertIn("Memory trace:", prompt)

    def test_postprocess_rewrites_gpt_identity_leak(self):
        result = postprocess_answer(
            "Я работаю на современной GPT-модели, настроенной под роль Jarvis для Дмитрия.",
            latency_ms=None,
            normalize_whitespace_func=lambda text: " ".join((text or "").split()),
            trim_generic_followup_func=lambda text: text,
            truncate_text_func=lambda text, limit: text[:limit],
            display_timezone=__import__("zoneinfo").ZoneInfo("Europe/Moscow"),
            max_output_chars=4000,
        )
        self.assertIn("Enterprise Core v194.95.", result)
        self.assertNotIn("GPT", result)
        self.assertNotIn("Codex", result)
        self.assertNotIn("OpenAI", result)

    def test_postprocess_keeps_technical_answer_that_mentions_codex_in_logs(self):
        result = postprocess_answer(
            "По логу видно, что Codex session завершилась с ошибкой sandbox, но сам bridge не упал.",
            latency_ms=None,
            normalize_whitespace_func=lambda text: " ".join((text or "").split()),
            trim_generic_followup_func=lambda text: text,
            truncate_text_func=lambda text, limit: text[:limit],
            display_timezone=__import__("zoneinfo").ZoneInfo("Europe/Moscow"),
            max_output_chars=4000,
        )
        self.assertIn("Codex session", result)
        self.assertIn("bridge не упал", result)

    def test_postprocess_trims_next_step_followup_paragraph(self):
        result = postprocess_answer(
            "Лучше без такого.\n\nЛёгкая шутка ещё ок.\n\nСледующий шаг: если хочешь, сформулирую короткий ответ в чат.",
            latency_ms=None,
            normalize_whitespace_func=lambda text: text.strip(),
            trim_generic_followup_func=trim_generic_followup,
            truncate_text_func=lambda text, limit: text[:limit],
            display_timezone=__import__("zoneinfo").ZoneInfo("Europe/Moscow"),
            max_output_chars=4000,
        )
        self.assertIn("Лучше без такого.", result)
        self.assertNotIn("Следующий шаг:", result)

    def test_owner_contact_reply_is_personalized(self):
        reply = build_owner_contact_reply("Привет", persona="jarvis")
        self.assertTrue(reply)
        self.assertIn("Дмитрий", reply)


if __name__ == "__main__":
    unittest.main()
