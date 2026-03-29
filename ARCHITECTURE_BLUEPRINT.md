# Enterprise Core Architecture Blueprint

## 1. Audit Of Current Weak Spots

- Router still mixes `intent`, `route_kind`, and source permissions too loosely.
- `RouteDecision` existed, but it did not carry a strict `request_kind` policy layer.
- `SelfCheckReport` described outcome, but not a full response contract with confidence, freshness, tools, and memory trace.
- `world_state_registry` stored status snapshots, but not TTL, confidence, verification method, or stale flag.
- Request diagnostics tracked route selection, but not response mode, memory use, source set, or tools used.
- Attachment handling existed, but image/document flow still relied mostly on prompt text instead of a typed attachment contract.
- Owner/admin commands are powerful, but they still behave more like a wide command surface than a unified operational subsystem.
- Task persistence existed, but route diagnostics and task lifecycle were not fully stitched into one causal chain.

## 2. Target Architecture

End-to-end pipeline:

`request -> request_kind -> route policy -> RouteDecision -> ContextBundle / AttachmentBundle -> runtime/live/workspace/local-state execution -> SelfCheckReport -> response contract -> diagnostics`

Current truth-oriented persistence chain:

`request_trace_id -> task_runs -> task_events -> request_diagnostics -> final owner/user outcome`

Primary routing domains:

- `chat`
- `chat_local_context`
- `project`
- `runtime`
- `live`
- `owner_admin`

This keeps source permissions explicit instead of relying on stacked heuristics.

## 2.1 Current Extraction Status

This blueprint is no longer purely aspirational. The following slices are already extracted from the legacy monolith:

- `handlers/update_dispatcher.py`
- `handlers/owner_panel_sections.py`
- `services/bridge_state_schema.py`
- `services/bridge_chat_state.py`
- `services/bridge_memory_profiles.py`
- `services/bridge_moderation_state.py`
- `services/bridge_diagnostics_state.py`
- `services/bridge_task_state.py`
- `services/reply_context_service.py`
- `services/text_task_service.py`
- `services/media_task_service.py`
- `services/ask_codex_service.py`
- `services/enterprise_console_webapp.py`
- `services/context_assembly.py`
- `services/text_route_service.py`
- `services/js_enterprise_service.py`

Current residual monolith areas:

- `BridgeState` still owns a meaningful amount of repository/state wiring
- media-task orchestration still lives in `tg_codex_bridge.py`
- `handlers/control_panel_renderer.py` remains a large UI renderer
- `tests/test_runtime_regressions.py` remains a large regression umbrella file

## 3. Module Responsibilities

- `tg_codex_bridge.py`
  runtime entrypoint and coordinator; now progressively reduced toward Telegram polling, process lifecycle and module wiring
- `models/contracts.py`
  canonical typed contracts for `RouteDecision`, `ContextBundle`, `SelfCheckReport`, `AttachmentBundle`, `LiveProviderRecord`
- `router/request_router.py`
  deterministic request classification, route policy enforcement, source constraints, no Telegram I/O
- `pipeline/diagnostics.py`
  response contract enrichment, diagnostics shaping, persisted self-check preparation
- `pipeline/context_pipeline.py`
  text/attachment context-bundle orchestration and discussion-context assembly
- `owner/admin_registry.py`
  owner/admin command catalog and metadata for audit/report surfaces
- `owner/handlers.py`
  owner/admin command execution and owner-report rendering
- `handlers/`
  Telegram message handlers, callback/UI flow, command dispatch and parser normalization
- `handlers/control_panel_renderer.py`
  owner/public panel rendering separated from callback transport and bridge lifecycle; still a candidate for further split
- `handlers/update_dispatcher.py`
  Telegram update ingress and dispatch separated from bridge lifecycle
- `handlers/owner_panel_sections.py`
  extracted owner-only panel sections for runtime, git/logs, Jarvis control and command registry views
- `services/live_gateway.py`
  normalized live-provider access, provider status, live route execution surface
- `services/runtime_service.py`
  runtime world-state refresh, drive score recomputation, runtime/storage health rollups
- `services/memory_service.py`
  AI-assisted refresh for chat memory summaries and user memory summaries
- `services/bridge_runtime_text.py`
  stateless text/access/help/group-trigger helpers used by bridge compatibility wrappers
- `services/bridge_state_schema.py`
  `BridgeState` schema bootstrap, compatibility migrations and seed helpers
- `services/bridge_chat_state.py`
  chat history, events, summary and fact persistence extracted from `BridgeState`
- `services/bridge_memory_profiles.py`
  user/participant memory, visual signals, message subjects and active subject state
- `services/bridge_moderation_state.py`
  moderation/warn/welcome/task lock persistence extracted from `BridgeState`
- `services/bridge_diagnostics_state.py`
  request diagnostics, repair journal, self-heal state and world-state row access
- `services/bridge_task_state.py`
  persistent task lifecycle, `task_runs`, `task_events`, task continuity rendering
- `services/media_task_service.py`
  photo/document/voice task orchestration and attachment-aware media prompting
- `services/bridge_file_helpers.py`
  stateless sdcard/file/media helper wrappers used by bridge compatibility wrappers
- `services/bridge_ops_helpers.py`
  stateless git/log/runtime ops helper wrappers used by bridge compatibility wrappers
- `services/context_assembly.py`
  `ContextBundle` composition for text and attachments
- `services/text_route_service.py`
  route-aware prompt/runtime preparation for text requests
- `services/js_enterprise_service.py`
  long-running enterprise job transport, progress flow and bridge/server continuity
- `services/discussion_context.py`
  local discussion and reply-aware context with safe fallback on sparse databases
- `services/group_reply_policy.py`
  group reply gating without conflating reply intent with chat volume
- `services/failure_detectors.py`
  machine-readable failure signals for runtime, route, storage and live domains
- `services/repair_playbooks.py`
  safe repair-playbook catalog and verification discipline
- `services/orchestration_utils.py`
  route validation, route summary, self-check policy
- `services/answer_postprocess.py`
  answer cleanup only, never route selection
- `utils/ops_utils.py`
  runtime and git probes
- `utils/report_utils.py`
  rendering diagnostics and runtime reports
- `tools/smoke_check.py`
  routing and contract regression guard

Controlled migration note:

- the bridge still contains compatibility wrappers for legacy call sites
- `services/route_contracts.py`, `services/diagnostics_pipeline.py` and `services/admin_registry.py`
  remain as compatibility layers that re-export or bridge to the new package layout
- bridge helper wrappers are now progressively backed by `services/bridge_runtime_text.py`, `services/bridge_file_helpers.py` and `services/bridge_ops_helpers.py`
- storage/state compatibility wrappers are now progressively backed by `services/bridge_state_schema.py`, `services/bridge_chat_state.py`, `services/bridge_memory_profiles.py`, `services/bridge_moderation_state.py` and `services/bridge_diagnostics_state.py`
- task continuity wrappers are now progressively backed by `services/bridge_task_state.py`
- this keeps behavior stable while reducing the legacy file incrementally instead of rewriting it in one pass

## 3.1 Truthfulness And Verification Discipline

- `tool_observed` means the system has observed a real tool/runtime completion, but has not yet upgraded that result to a stronger truth claim.
- final `verified/inferred/insufficient` semantics belong to diagnostics/self-check, not to raw process exit.
- attachment and enterprise flows therefore write lifecycle first, and truth-marker second.
- `task_events` preserve causality across restarts and long-running jobs instead of inferring it from a single final row.

## 4. Improved Data Contracts

### RouteDecision

Now carries:

- `request_kind`
- `allowed_sources`
- `forbidden_sources`
- `required_tools`
- `answer_contract`

### SelfCheckReport

Now carries:

- `mode`
- `route`
- `sources`
- `tools_used`
- `memory_used`
- `confidence`
- `freshness`
- `notes`

### New Contracts

- `RequestRoutePolicy`
- `LiveProviderRecord`
- `AttachmentBundle`

## 5. Router Policy Matrix

### chat

- Allowed: `chat_history`, `chat_memory`, `summary_memory`
- Forbidden: `runtime_probe`, `live_provider`
- Required tools: none
- Refuse when: fresh/runtime/project verification is actually required
- Answer style: compact conversational answer

### chat_local_context

- Allowed: `chat_events`, `reply_context`, `user_memory`, `relation_memory`, `chat_memory`, `summary_memory`
- Forbidden: `live_provider`, `generic_web_search`
- Required tools: `local_chat_context`
- Refuse when: local evidence is too weak
- Answer style: local grounded analysis

### project

- Allowed: `workspace`, `project_files`, `logs`, `world_state`
- Forbidden: `live_provider`, `generic_web_search`
- Required tools: `workspace_route`
- Refuse when: workspace execution is unavailable
- Answer style: engineering analysis of local project state

### runtime

- Allowed: `runtime_probe`, `world_state`, `logs`
- Forbidden: free conversational inference
- Required tools: `direct_runtime_probe`
- Refuse when: probe did not run
- Answer style: verified runtime report

### live

- Allowed: `live_provider`
- Forbidden: weak general web inference
- Required tools: `live_route`
- Refuse when: provider failed or data is stale and no fallback confirmed
- Answer style: source + freshness + bounded conclusion

### owner_admin

- Allowed: `owner_commands`, `runtime_probe`, `workspace`, `diagnostics`
- Forbidden: unverified claims
- Required tools: `owner_permission_check`
- Refuse when: permission or tool route is unavailable
- Answer style: operational output with trace

## 6. Memory Precedence Rules

Strict precedence:

1. direct runtime/tool/file evidence
2. reply-target and thread context
3. chat events
4. user memory
5. relation memory
6. chat memory
7. summary memory
8. self/world/drive overlays

Rules:

- No more than 4 memory layers should materially influence a single answer.
- `chat_local_context` should prefer `reply_context + chat_events + relation/user memory`.
- `project` should prefer `workspace/logs/world_state`, not conversational memory.
- `live` should avoid chat memory unless the query explicitly mixes local and external state.
- Persistent entity layer should shape guardrails and diagnostics, not invent facts.

## 7. Live Provider Interface

Canonical provider record:

```json
{
  "provider": "open-meteo",
  "category": "weather",
  "data": "...",
  "timestamp": 1774550000,
  "freshness": "live",
  "status": "ok",
  "reliability": 0.92,
  "normalized": true
}
```

Fallback chain:

1. dedicated provider
2. secondary provider for same category
3. bounded failure response with explicit insufficient mode

Freshness rules:

- runtime: `<= 2 min`
- price/weather/fx/crypto/stocks: `<= 15 min`
- news/current fact: `<= 60 min`

`current/latest/сейчас` queries must never fall back to generic weak HTML scraping.

## 8. Attachment Pipeline

Attachment pipeline should produce `AttachmentBundle`:

- `attachment_type`
- `extracted_text`
- `structured_features`
- `source_message_link`
- `relevance_score`
- `used_in_response`

Interpretation split:

- file as object of analysis
- file as supporting context

Required stages:

1. attachment type detection
2. metadata extraction
3. text excerpt extraction when possible
4. bundle creation
5. relevance decision before prompt assembly

## 9. Owner/Admin Subsystem

Recommended operational domains:

- permission layer
- command registry
- diagnostics domain
- route audit domain
- runtime audit domain
- memory audit domain

Owner/admin design rule:

commands should not directly embed business logic in each handler if the same data can be served by shared audit services.

## 10. Observability Plan

Structured metrics to track:

- `verified_count`
- `inferred_count`
- `insufficient_count`
- `route_kind_count`
- `request_kind_count`
- `live_provider_failures`
- `stale_live_records`
- `runtime_probe_required_count`
- `self_check_failure_count`
- `memory_layer_usage_count`
- `prevented_false_claim_count`

Structured diagnostics row should include:

- request kind
- route kind
- response mode
- source labels
- tools used
- memory used
- confidence
- freshness
- latency

Useful owner dashboard blocks:

- route mix
- verified/inferred/insufficient ratio
- stale live provider pressure
- world-state stale entries
- top memory layers used

## 11. Migration Plan

1. Add typed contracts without breaking old routes.
2. Expand SQLite schema with additive columns only.
3. Enrich diagnostics first, then tighten routing decisions.
4. Move live providers behind a normalized interface.
5. Split attachment handling into a dedicated attachment service.
6. Remove compatibility wrappers from `tg_codex_bridge.py` after all call sites use `router/`, `pipeline/`, `owner/` and `models/` directly.
7. Add world-state revalidation worker.
8. Add route audit screens based on new diagnostics fields.

## 12. Example Traces

### Example A: Runtime Question

- Request: `Enterprise состояние среды?`
- Route: `runtime -> codex_workspace`
- Memory: `world_state`
- Tools: `direct_runtime_probe`
- Self-check: `verified`
- Final mode: `verified`

### Example B: Local Chat Incident

- Request: `Ты удалил сообщение, потом написал предупреждение. Изучи и дай ответ.`
- Route: `chat_local_context -> codex_chat`
- Memory: `reply_context`, `chat_events`, `database_context`
- Tools: `sqlite_memory`, `reply_context`
- Self-check: `verified` or `inferred` depending on evidence density
- Final mode: never `live`

### Example C: Current Fact

- Request: `Кто сейчас CEO компании X?`
- Route: `live -> live_current_fact`
- Memory: none or bounded local context only
- Tools: `live_provider`
- Self-check: `verified` if source and freshness confirmed, otherwise `insufficient`
- Final mode: never free conversational guess
