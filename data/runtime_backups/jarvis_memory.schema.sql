CREATE INDEX idx_achievement_state_user_unlock ON user_achievement_state(user_id, unlocked_at DESC);

CREATE INDEX idx_appeal_events_appeal_created_at ON appeal_events(appeal_id, created_at ASC);

CREATE INDEX idx_appeals_status_created_at ON appeals(status, created_at DESC);

CREATE INDEX idx_appeals_user_created_at ON appeals(user_id, created_at DESC);

CREATE INDEX idx_autobiographical_memory_chat_id_id ON autobiographical_memory(chat_id, id DESC);

CREATE INDEX idx_autobiographical_memory_open_state ON autobiographical_memory(open_state, importance DESC, updated_at DESC);

CREATE INDEX idx_chat_events_chat_id_id ON chat_events(chat_id, id);

CREATE INDEX idx_chat_history_chat_id_id ON chat_history(chat_id, id);

CREATE INDEX idx_chat_participants_chat_id_last_seen ON chat_participants(chat_id, last_seen_at DESC);

CREATE INDEX idx_memory_facts_chat_id_id ON memory_facts(chat_id, id);

CREATE INDEX idx_moderation_actions_active_expires ON moderation_actions(active, expires_at);

CREATE INDEX idx_moderation_actions_chat_user ON moderation_actions(chat_id, user_id, action, active);

CREATE INDEX idx_moderation_journal_user_created_at ON moderation_journal(user_id, created_at DESC);

CREATE INDEX idx_reflections_chat_id_id ON reflections(chat_id, id DESC);

CREATE INDEX idx_relation_memory_chat_id_updated ON relation_memory(chat_id, updated_at DESC, last_interaction_at DESC);

CREATE INDEX idx_repair_journal_created_at ON repair_journal(created_at DESC, id DESC);

CREATE INDEX idx_request_diagnostics_chat_id_id ON request_diagnostics(chat_id, id);

CREATE INDEX idx_score_events_type_created_at ON score_events(event_type, created_at DESC);

CREATE INDEX idx_score_events_user_created_at ON score_events(user_id, created_at DESC);

CREATE INDEX idx_self_heal_attempts_incident ON self_heal_attempts(incident_id, created_at DESC);

CREATE INDEX idx_self_heal_incidents_created_at ON self_heal_incidents(created_at DESC, id DESC);

CREATE INDEX idx_self_heal_incidents_problem_state ON self_heal_incidents(problem_type, state, updated_at DESC);

CREATE INDEX idx_self_heal_lessons_incident ON self_heal_lessons(incident_id, created_at DESC);

CREATE INDEX idx_self_heal_transitions_incident ON self_heal_transitions(incident_id, created_at DESC);

CREATE INDEX idx_self_heal_verifications_incident ON self_heal_verifications(incident_id, created_at DESC);

CREATE INDEX idx_summary_snapshots_chat_id_id ON summary_snapshots(chat_id, id);

CREATE INDEX idx_user_memory_profiles_chat_id_user_id ON user_memory_profiles(chat_id, user_id);

CREATE INDEX idx_warnings_chat_user ON warnings(chat_id, user_id, id);

CREATE INDEX idx_world_state_registry_category ON world_state_registry(category, updated_at DESC);

CREATE TABLE achievement_catalog (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                badge TEXT NOT NULL,
                rarity TEXT NOT NULL,
                category TEXT NOT NULL,
                metric TEXT NOT NULL,
                target_value INTEGER NOT NULL DEFAULT 1,
                tier INTEGER NOT NULL DEFAULT 1,
                hidden INTEGER NOT NULL DEFAULT 0,
                chain_code TEXT NOT NULL DEFAULT '',
                reward_xp INTEGER NOT NULL DEFAULT 0,
                reward_score INTEGER NOT NULL DEFAULT 0,
                reward_badge TEXT NOT NULL DEFAULT '',
                is_seasonal INTEGER NOT NULL DEFAULT 0,
                is_status INTEGER NOT NULL DEFAULT 0,
                is_prestige INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT ''
            );

CREATE TABLE appeal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appeal_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                status_from TEXT NOT NULL DEFAULT '',
                status_to TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

CREATE TABLE appeals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                status TEXT NOT NULL DEFAULT 'new',
                resolution TEXT NOT NULL DEFAULT '',
                moderator_id INTEGER,
                reviewed_at INTEGER,
                auto_result TEXT NOT NULL DEFAULT '',
                cooldown_until INTEGER NOT NULL DEFAULT 0
            , updated_at INTEGER NOT NULL DEFAULT 0, closed_at INTEGER, decision_type TEXT NOT NULL DEFAULT 'manual', source_action TEXT NOT NULL DEFAULT '', review_comment TEXT NOT NULL DEFAULT '', snapshot_json TEXT NOT NULL DEFAULT '{}');

CREATE TABLE autobiographical_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT '',
                    chat_id INTEGER,
                    user_id INTEGER,
                    route_kind TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    importance INTEGER NOT NULL DEFAULT 0,
                    open_state TEXT NOT NULL DEFAULT 'closed',
                    tags TEXT NOT NULL DEFAULT '',
                    observed_json TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE bot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE chat_events (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER, role TEXT NOT NULL, message_type TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), message_id INTEGER, username TEXT, first_name TEXT, last_name TEXT, chat_type TEXT, reply_to_message_id INTEGER, reply_to_user_id INTEGER, reply_to_username TEXT, forward_origin TEXT, has_media INTEGER, file_kind TEXT, is_edited INTEGER);

CREATE VIRTUAL TABLE chat_events_fts USING fts5(text, content='chat_events', content_rowid='id', tokenize='unicode61');

CREATE TABLE 'chat_events_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'chat_events_fts_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'chat_events_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'chat_events_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TABLE chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE chat_modes (chat_id INTEGER PRIMARY KEY, mode TEXT NOT NULL);

CREATE TABLE chat_participants (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    first_name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '',
                    is_bot INTEGER NOT NULL DEFAULT 0,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    last_status TEXT NOT NULL DEFAULT '',
                    first_seen_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    last_seen_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    last_join_at INTEGER,
                    last_leave_at INTEGER,
                    PRIMARY KEY(chat_id, user_id)
                );

CREATE TABLE chat_runtime_cache (
                    chat_id INTEGER PRIMARY KEY,
                    member_count INTEGER NOT NULL DEFAULT 0,
                    admins_synced_at INTEGER NOT NULL DEFAULT 0,
                    member_count_synced_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE chat_summaries (chat_id INTEGER PRIMARY KEY, summary TEXT NOT NULL, updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE drive_scores (
                    drive_name TEXT PRIMARY KEY,
                    score REAL NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE memory_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, created_by_user_id INTEGER, fact TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE memory_refresh_state (
                    chat_id INTEGER PRIMARY KEY,
                    last_event_id INTEGER NOT NULL DEFAULT 0,
                    last_run_at INTEGER NOT NULL DEFAULT 0,
                    last_user_refresh_at INTEGER NOT NULL DEFAULT 0,
                    last_summary_refresh_at INTEGER NOT NULL DEFAULT 0
                );

CREATE TABLE moderation_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_by_user_id INTEGER, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), expires_at INTEGER, active INTEGER NOT NULL DEFAULT 1, completed_at INTEGER);

CREATE TABLE moderation_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                reason TEXT NOT NULL DEFAULT '',
                created_by_user_id INTEGER,
                points_delta INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER,
                resolved_at INTEGER,
                source_ref TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

CREATE TABLE progression_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                msg_count INTEGER NOT NULL DEFAULT 0,
                reactions_given INTEGER NOT NULL DEFAULT 0,
                reactions_received INTEGER NOT NULL DEFAULT 0,
                activity_score INTEGER NOT NULL DEFAULT 0,
                contribution_score INTEGER NOT NULL DEFAULT 0,
                achievement_score INTEGER NOT NULL DEFAULT 0,
                behavior_score INTEGER NOT NULL DEFAULT 100,
                moderation_penalty INTEGER NOT NULL DEFAULT 0,
                total_xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 0,
                prestige INTEGER NOT NULL DEFAULT 0,
                rank_name TEXT NOT NULL DEFAULT 'Наблюдатель',
                rank_badge TEXT NOT NULL DEFAULT '🌫️',
                status_label TEXT NOT NULL DEFAULT 'Новичок',
                total_score INTEGER NOT NULL DEFAULT 0,
                weekly_score INTEGER NOT NULL DEFAULT 0,
                monthly_score INTEGER NOT NULL DEFAULT 0,
                season_id TEXT NOT NULL DEFAULT '',
                season_score INTEGER NOT NULL DEFAULT 0,
                dynamic_score INTEGER NOT NULL DEFAULT 0,
                helpful_messages INTEGER NOT NULL DEFAULT 0,
                meaningful_messages INTEGER NOT NULL DEFAULT 0,
                long_messages INTEGER NOT NULL DEFAULT 0,
                media_messages INTEGER NOT NULL DEFAULT 0,
                replied_messages INTEGER NOT NULL DEFAULT 0,
                unique_days INTEGER NOT NULL DEFAULT 0,
                streak_days INTEGER NOT NULL DEFAULT 0,
                best_streak INTEGER NOT NULL DEFAULT 0,
                clean_streak_days INTEGER NOT NULL DEFAULT 0,
                good_standing_days INTEGER NOT NULL DEFAULT 0,
                last_message_at INTEGER NOT NULL DEFAULT 0,
                first_seen_at INTEGER NOT NULL DEFAULT 0,
                last_day_key TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL DEFAULT 0
            );

CREATE TABLE reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    route_kind TEXT NOT NULL DEFAULT '',
                    task_summary TEXT NOT NULL DEFAULT '',
                    observed_outcome TEXT NOT NULL DEFAULT '',
                    uncertainty TEXT NOT NULL DEFAULT '',
                    lesson TEXT NOT NULL DEFAULT '',
                    recommended_updates TEXT NOT NULL DEFAULT '',
                    applied_updates TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE relation_memory (
                    chat_id INTEGER NOT NULL,
                    user_low_id INTEGER NOT NULL,
                    user_high_id INTEGER NOT NULL,
                    reply_count_low_to_high INTEGER NOT NULL DEFAULT 0,
                    reply_count_high_to_low INTEGER NOT NULL DEFAULT 0,
                    co_presence_count INTEGER NOT NULL DEFAULT 0,
                    humor_markers INTEGER NOT NULL DEFAULT 0,
                    rough_markers INTEGER NOT NULL DEFAULT 0,
                    support_markers INTEGER NOT NULL DEFAULT 0,
                    topic_markers TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    last_interaction_at INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY(chat_id, user_low_id, user_high_id)
                );

CREATE TABLE repair_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_code TEXT NOT NULL DEFAULT '',
                    playbook_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    verification_result TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE request_diagnostics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER,
                    chat_type TEXT NOT NULL DEFAULT '',
                    persona TEXT NOT NULL DEFAULT '',
                    intent TEXT NOT NULL DEFAULT '',
                    route_kind TEXT NOT NULL DEFAULT '',
                    source_label TEXT NOT NULL DEFAULT '',
                    used_live INTEGER NOT NULL DEFAULT 0,
                    used_web INTEGER NOT NULL DEFAULT 0,
                    used_events INTEGER NOT NULL DEFAULT 0,
                    used_database INTEGER NOT NULL DEFAULT 0,
                    used_reply INTEGER NOT NULL DEFAULT 0,
                    used_workspace INTEGER NOT NULL DEFAULT 0,
                    guardrails TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT '',
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    query_text TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                , request_kind TEXT NOT NULL DEFAULT '', response_mode TEXT NOT NULL DEFAULT '', sources TEXT NOT NULL DEFAULT '', tools_used TEXT NOT NULL DEFAULT '', memory_used TEXT NOT NULL DEFAULT '', confidence REAL NOT NULL DEFAULT 0.0, freshness TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '');

CREATE TABLE score_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                source_message_id INTEGER,
                event_type TEXT NOT NULL,
                xp_delta INTEGER NOT NULL DEFAULT 0,
                score_delta INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                abuse_flag TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

CREATE TABLE self_heal_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL,
                    playbook_id TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    execution_summary TEXT NOT NULL DEFAULT '',
                    executed_steps_json TEXT NOT NULL DEFAULT '',
                    failed_step TEXT NOT NULL DEFAULT '',
                    artifacts_changed_json TEXT NOT NULL DEFAULT '',
                    verification_required INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    stdout_json TEXT NOT NULL DEFAULT '',
                    stderr_json TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE self_heal_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_type TEXT NOT NULL DEFAULT '',
                    signal_code TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    risk_level TEXT NOT NULL DEFAULT '',
                    autonomy_level TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    suggested_playbook TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT '',
                    lesson_text TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE self_heal_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL,
                    lesson_key TEXT NOT NULL DEFAULT '',
                    lesson_text TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE self_heal_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL,
                    from_state TEXT NOT NULL DEFAULT '',
                    to_state TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE self_heal_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL,
                    attempt_id INTEGER,
                    verified INTEGER NOT NULL DEFAULT 0,
                    before_state_json TEXT NOT NULL DEFAULT '',
                    after_state_json TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    remaining_issues_json TEXT NOT NULL DEFAULT '',
                    regressions_json TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE self_model_state (
                    state_id TEXT PRIMARY KEY,
                    identity TEXT NOT NULL DEFAULT '',
                    active_mode TEXT NOT NULL DEFAULT '',
                    capabilities TEXT NOT NULL DEFAULT '',
                    hard_limitations TEXT NOT NULL DEFAULT '',
                    trusted_tools TEXT NOT NULL DEFAULT '',
                    confidence_policy TEXT NOT NULL DEFAULT '',
                    current_goals TEXT NOT NULL DEFAULT '',
                    active_constraints TEXT NOT NULL DEFAULT '',
                    honesty_rules TEXT NOT NULL DEFAULT '',
                    jarvis_style_invariants TEXT NOT NULL DEFAULT '',
                    enterprise_style_invariants TEXT NOT NULL DEFAULT '',
                    last_route_kind TEXT NOT NULL DEFAULT '',
                    last_outcome TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE skill_memory (
                    skill_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    trigger_tags TEXT NOT NULL DEFAULT '',
                    procedure TEXT NOT NULL DEFAULT '',
                    reliability REAL NOT NULL DEFAULT 0.5,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    last_used_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE summary_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'rolling',
                    summary TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );

CREATE TABLE ui_sessions (user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL DEFAULT 0, active_panel TEXT NOT NULL DEFAULT 'home', pending_action TEXT NOT NULL DEFAULT '', pending_payload TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE user_achievement_state (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                progress_value INTEGER NOT NULL DEFAULT 0,
                progress_target INTEGER NOT NULL DEFAULT 0,
                unlocked_at INTEGER,
                tier_achieved INTEGER NOT NULL DEFAULT 0,
                last_evaluated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, code)
            );

CREATE TABLE user_memory_profiles (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    style_notes TEXT NOT NULL DEFAULT '',
                    topics TEXT NOT NULL DEFAULT '',
                    last_message_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), ai_summary TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(chat_id, user_id)
                );

CREATE TABLE warn_settings (chat_id INTEGER PRIMARY KEY, warn_limit INTEGER NOT NULL DEFAULT 3, warn_mode TEXT NOT NULL DEFAULT 'mute', warn_expire_seconds INTEGER NOT NULL DEFAULT 0);

CREATE TABLE warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', created_by_user_id INTEGER, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), expires_at INTEGER);

CREATE TABLE welcome_settings (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, template TEXT NOT NULL DEFAULT 'Добро пожаловать, {full_name}!');

CREATE TABLE world_state_registry (
                    state_key TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    value_text TEXT NOT NULL DEFAULT '',
                    value_number REAL,
                    source TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                , confidence REAL NOT NULL DEFAULT 0.0, ttl_seconds INTEGER NOT NULL DEFAULT 0, verification_method TEXT NOT NULL DEFAULT '', stale_flag INTEGER NOT NULL DEFAULT 0);

CREATE TABLE world_state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );
