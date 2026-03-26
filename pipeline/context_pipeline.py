from typing import Optional

from models.contracts import ContextBundle
from services.context_assembly import build_attachment_context_bundle, build_text_context_bundle
from services.context_bundle_utils import should_include_entity_context
from services.discussion_context import build_current_discussion_context


class ContextPipeline:
    def build_current_discussion_context(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        *,
        message: Optional[dict],
        user_id: Optional[int],
        active_group_followup: bool = False,
    ) -> str:
        active_thread = bridge.get_active_group_discussion(chat_id, message=message, raw_text=(message or {}).get("text") or "")
        discussion_context = build_current_discussion_context(
            state=bridge.state,
            chat_id=chat_id,
            message=message,
            user_id=user_id,
            query_text=(message or {}).get("text") or "",
            active_group_followup=active_group_followup,
            active_thread=active_thread,
            build_actor_name_func=bridge.build_actor_name,
            build_service_actor_name_func=bridge.build_service_actor_name,
            truncate_text_func=bridge.truncate_text,
        )
        discussion_state_hint = bridge.get_group_discussion_state_hint(chat_id)
        if discussion_state_hint:
            if discussion_context:
                return f"{discussion_context}\n\n{discussion_state_hint}"
            return discussion_state_hint
        return discussion_context

    def build_text_context_bundle(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        user_text: str,
        route_decision,
        user_id: Optional[int],
        message: Optional[dict],
        reply_context: str,
        active_group_followup: bool = False,
    ) -> ContextBundle:
        return build_text_context_bundle(
            context_bundle_factory=ContextBundle,
            state=bridge.state,
            chat_id=chat_id,
            user_text=user_text,
            route_decision=route_decision,
            user_id=user_id,
            message=message,
            reply_context=reply_context,
            active_group_followup=active_group_followup,
            detect_local_chat_query_func=bridge.detect_local_chat_query,
            should_include_database_context_func=bridge.should_include_database_context,
            is_owner_private_chat_func=bridge.is_owner_private_chat,
            build_current_discussion_context_func=lambda **kwargs: self.build_current_discussion_context(bridge, **kwargs),
            build_external_research_context_func=bridge.build_external_research_context,
            build_route_summary_text_func=bridge.build_route_summary_text,
            build_guardrail_note_func=bridge.build_guardrail_note,
            should_include_entity_context_func=should_include_entity_context,
        )

    def build_attachment_context_bundle(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        prompt_text: str,
        message: Optional[dict],
        reply_context: str,
    ) -> ContextBundle:
        return build_attachment_context_bundle(
            context_bundle_factory=ContextBundle,
            state=bridge.state,
            chat_id=chat_id,
            prompt_text=prompt_text,
            message=message,
            reply_context=reply_context,
            should_include_event_context_func=bridge.should_include_event_context,
            should_include_database_context_func=bridge.should_include_database_context,
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
