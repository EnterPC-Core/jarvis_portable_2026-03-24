import unittest
from types import SimpleNamespace

from services.context_assembly import build_text_context_bundle
from tg_codex_bridge import TelegramBridge


class _FakeState:
    history_limit = 2

    def get_history(self, _chat_id):
        return [("user", "one"), ("assistant", "two")]

    def get_summary(self, _chat_id):
        return "summary"

    def render_facts(self, _chat_id, query, limit):
        del query, limit
        return "facts"

    def get_event_context(self, _chat_id, _user_text):
        return "events"

    def get_database_context(self, _chat_id, _user_text):
        return "database"

    def get_self_model_context(self, _persona):
        return "self-model"

    def get_autobiographical_context(self, _chat_id, query, limit):
        del query, limit
        return "autobio"

    def get_skill_memory_context(self, _user_text, route_kind, limit):
        del route_kind, limit
        return "skills"

    def get_world_state_context(self, limit):
        del limit
        return "world"

    def get_drive_context(self):
        return "drives"

    def get_user_memory_context(self, _chat_id, user_id=None, reply_to_user_id=None):
        del user_id, reply_to_user_id
        return "user-memory"

    def get_relation_memory_context(self, _chat_id, user_id=None, reply_to_user_id=None, query=""):
        del user_id, reply_to_user_id, query
        return "relation-memory"

    def get_chat_memory_context(self, _chat_id, query=""):
        del query
        return "chat-memory"

    def get_summary_memory_context(self, _chat_id, limit=0):
        del limit
        return "summary-memory"


class RuntimeRegressionTests(unittest.TestCase):
    def test_context_assembly_uses_entity_context_keyword_contract(self):
        captured = {}

        def context_bundle_factory(**kwargs):
            return kwargs

        def should_include_entity_context_func(**kwargs):
            captured.update(kwargs)
            return True

        route_decision = SimpleNamespace(
            persona="enterprise",
            use_workspace=False,
            route_kind="codex_workspace",
        )
        bundle = build_text_context_bundle(
            context_bundle_factory=context_bundle_factory,
            state=_FakeState(),
            chat_id=42,
            user_text="Проверь проект",
            route_decision=route_decision,
            user_id=6102780373,
            message={"reply_to_message": {"from": {"id": 11}}},
            reply_context="reply",
            active_group_followup=False,
            detect_local_chat_query_func=lambda _text: False,
            should_include_database_context_func=lambda _text: True,
            is_owner_private_chat_func=lambda _user_id, _chat_id: False,
            build_current_discussion_context_func=lambda *_args, **_kwargs: "discussion",
            build_route_summary_text_func=lambda _route: "route-summary",
            build_guardrail_note_func=lambda _route: "guardrails",
            should_include_entity_context_func=should_include_entity_context_func,
        )

        self.assertEqual(captured["persona"], "enterprise")
        self.assertEqual(captured["query_text"], "Проверь проект")
        self.assertFalse(captured["use_workspace"])
        self.assertIn("continuity", bundle["route_summary"].lower())
        self.assertEqual(bundle["self_model_text"], "self-model")
        self.assertEqual(bundle["database_context"], "database")

    def test_webapp_html_accepts_screen_text_and_prompt_value(self):
        html_text = TelegramBridge.build_webapp_html(
            SimpleNamespace(),
            screen_text="runtime ok",
            prompt_value="diagnose",
            auto_refresh_seconds=0,
        )

        self.assertIn("runtime ok", html_text)
        self.assertIn('value="diagnose"', html_text)
        self.assertIn("/enterprise-console/api/jobs/", html_text)


if __name__ == "__main__":
    unittest.main()
