from typing import Callable, Sequence


def initialize_bridge_state_db(
    state: "BridgeState",
    *,
    normalize_visual_analysis_text_func: Callable[[str], str],
    self_model_defaults: dict[str, str],
    default_skill_library: Sequence[tuple[str, str, str, str]],
    drive_names: Sequence[str],
) -> None:
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS chat_modes (chat_id INTEGER PRIMARY KEY, mode TEXT NOT NULL)"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS chat_events (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER, user_id INTEGER, username TEXT, first_name TEXT, last_name TEXT, chat_type TEXT, role TEXT NOT NULL, message_type TEXT NOT NULL, text TEXT NOT NULL, reply_to_message_id INTEGER, reply_to_user_id INTEGER, reply_to_username TEXT, forward_origin TEXT, has_media INTEGER NOT NULL DEFAULT 0, file_kind TEXT, is_edited INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS chat_summaries (chat_id INTEGER PRIMARY KEY, summary TEXT NOT NULL, updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS memory_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, created_by_user_id INTEGER, fact TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS user_memory_profiles (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            style_notes TEXT NOT NULL DEFAULT '',
            topics TEXT NOT NULL DEFAULT '',
            last_message_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            PRIMARY KEY(chat_id, user_id)
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS summary_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            scope TEXT NOT NULL DEFAULT 'rolling',
            summary TEXT NOT NULL,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS memory_refresh_state (
            chat_id INTEGER PRIMARY KEY,
            last_event_id INTEGER NOT NULL DEFAULT 0,
            last_run_at INTEGER NOT NULL DEFAULT 0,
            last_user_refresh_at INTEGER NOT NULL DEFAULT 0,
            last_summary_refresh_at INTEGER NOT NULL DEFAULT 0
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS chat_participants (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS participant_profiles (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            first_seen_at INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0,
            reply_count INTEGER NOT NULL DEFAULT 0,
            reactions_given INTEGER NOT NULL DEFAULT 0,
            reactions_received INTEGER NOT NULL DEFAULT 0,
            conflict_score INTEGER NOT NULL DEFAULT 0,
            toxicity_score INTEGER NOT NULL DEFAULT 0,
            spam_score INTEGER NOT NULL DEFAULT 0,
            flood_score INTEGER NOT NULL DEFAULT 0,
            instability_score INTEGER NOT NULL DEFAULT 0,
            helpfulness_score INTEGER NOT NULL DEFAULT 0,
            credibility_score INTEGER NOT NULL DEFAULT 0,
            owner_affinity_score INTEGER NOT NULL DEFAULT 0,
            risk_flags_json TEXT NOT NULL DEFAULT '[]',
            notes_summary TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS participant_chat_profiles (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            first_seen_at INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0,
            reply_count INTEGER NOT NULL DEFAULT 0,
            reactions_given INTEGER NOT NULL DEFAULT 0,
            reactions_received INTEGER NOT NULL DEFAULT 0,
            conflict_score INTEGER NOT NULL DEFAULT 0,
            toxicity_score INTEGER NOT NULL DEFAULT 0,
            spam_score INTEGER NOT NULL DEFAULT 0,
            flood_score INTEGER NOT NULL DEFAULT 0,
            instability_score INTEGER NOT NULL DEFAULT 0,
            helpfulness_score INTEGER NOT NULL DEFAULT 0,
            credibility_score INTEGER NOT NULL DEFAULT 0,
            risk_flags_json TEXT NOT NULL DEFAULT '[]',
            notes_summary TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            PRIMARY KEY(chat_id, user_id)
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS participant_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL DEFAULT 0,
            signal_type TEXT NOT NULL,
            score_delta INTEGER NOT NULL DEFAULT 0,
            evidence_text TEXT NOT NULL DEFAULT '',
            source_message_id INTEGER,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS participant_visual_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            file_unique_id TEXT NOT NULL DEFAULT '',
            media_sha256 TEXT NOT NULL DEFAULT '',
            caption TEXT NOT NULL DEFAULT '',
            analysis_text TEXT NOT NULL DEFAULT '',
            risk_flags_json TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(chat_id, message_id)
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS message_subjects (
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT '',
            user_id INTEGER NOT NULL DEFAULT 0,
            summary TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            PRIMARY KEY(chat_id, message_id)
        )"""
    )
    participant_visual_columns = {
        str(row["name"])
        for row in state.db.execute("PRAGMA table_info(participant_visual_signals)").fetchall()
    }
    if "media_sha256" not in participant_visual_columns:
        state.db.execute(
            "ALTER TABLE participant_visual_signals ADD COLUMN media_sha256 TEXT NOT NULL DEFAULT ''"
        )
    state.db.execute(
        "CREATE INDEX IF NOT EXISTS idx_participant_visual_signals_user_chat ON participant_visual_signals(user_id, chat_id, created_at DESC)"
    )
    state.db.execute(
        "CREATE INDEX IF NOT EXISTS idx_participant_visual_signals_sha256 ON participant_visual_signals(media_sha256)"
    )
    stale_visual_rows = state.db.execute(
        """
        SELECT id, analysis_text
        FROM participant_visual_signals
        WHERE analysis_text LIKE 'scene:%'
           OR analysis_text LIKE 'profile_style:%'
           OR analysis_text LIKE '%risk_flags:%'
           OR analysis_text LIKE '%why:%'
        LIMIT 200
        """
    ).fetchall()
    for row in stale_visual_rows:
        normalized_analysis = normalize_visual_analysis_text_func(str(row["analysis_text"] or ""))
        state.db.execute(
            "UPDATE participant_visual_signals SET analysis_text = ? WHERE id = ?",
            (normalized_analysis, int(row["id"] or 0)),
        )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS chat_runtime_cache (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT NOT NULL DEFAULT '',
            member_count INTEGER NOT NULL DEFAULT 0,
            admins_synced_at INTEGER NOT NULL DEFAULT 0,
            member_count_synced_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    runtime_cache_columns = {
        str(row["name"])
        for row in state.db.execute("PRAGMA table_info(chat_runtime_cache)").fetchall()
    }
    if "chat_title" not in runtime_cache_columns:
        state.db.execute("ALTER TABLE chat_runtime_cache ADD COLUMN chat_title TEXT NOT NULL DEFAULT ''")
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS relation_memory (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_model_state (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS autobiographical_memory (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS reflections (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS skill_memory (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS world_state_registry (
            state_key TEXT PRIMARY KEY,
            category TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            value_text TEXT NOT NULL DEFAULT '',
            value_number REAL,
            source TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            ttl_seconds INTEGER NOT NULL DEFAULT 0,
            verification_method TEXT NOT NULL DEFAULT '',
            stale_flag INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS world_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS drive_scores (
            drive_name TEXT PRIMARY KEY,
            score REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chat_events_fts USING fts5(text, content='chat_events', content_rowid='id', tokenize='unicode61')"
    )
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id_id ON chat_history(chat_id, id)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_chat_events_chat_id_id ON chat_events(chat_id, id)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_memory_facts_chat_id_id ON memory_facts(chat_id, id)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_user_memory_profiles_chat_id_user_id ON user_memory_profiles(chat_id, user_id)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_chat_participants_chat_id_last_seen ON chat_participants(chat_id, last_seen_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_participant_chat_profiles_chat_id_updated_at ON participant_chat_profiles(chat_id, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_participant_observations_user_chat_created ON participant_observations(user_id, chat_id, created_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_relation_memory_chat_id_updated ON relation_memory(chat_id, updated_at DESC, last_interaction_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_autobiographical_memory_chat_id_id ON autobiographical_memory(chat_id, id DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_autobiographical_memory_open_state ON autobiographical_memory(open_state, importance DESC, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_reflections_chat_id_id ON reflections(chat_id, id DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_world_state_registry_category ON world_state_registry(category, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_summary_snapshots_chat_id_id ON summary_snapshots(chat_id, id)")
    state.db.execute("CREATE TABLE IF NOT EXISTS bot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS request_diagnostics (
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
            request_kind TEXT NOT NULL DEFAULT '',
            response_mode TEXT NOT NULL DEFAULT '',
            sources TEXT NOT NULL DEFAULT '',
            tools_used TEXT NOT NULL DEFAULT '',
            memory_used TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            freshness TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            query_text TEXT NOT NULL DEFAULT '',
            tools_attempted TEXT NOT NULL DEFAULT '',
            contract_satisfied INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS repair_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_code TEXT NOT NULL DEFAULT '',
            playbook_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            verification_result TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_heal_incidents (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_heal_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            from_state TEXT NOT NULL DEFAULT '',
            to_state TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_heal_attempts (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_heal_verifications (
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
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS self_heal_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            lesson_key TEXT NOT NULL DEFAULT '',
            lesson_text TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS task_runs (
            task_id TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            user_id INTEGER,
            message_id INTEGER,
            delivery_chat_id INTEGER,
            progress_message_id INTEGER,
            request_trace_id TEXT NOT NULL DEFAULT '',
            task_kind TEXT NOT NULL DEFAULT '',
            route_kind TEXT NOT NULL DEFAULT '',
            persona TEXT NOT NULL DEFAULT '',
            request_kind TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            approval_state TEXT NOT NULL DEFAULT '',
            verification_state TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT '',
            evidence_text TEXT NOT NULL DEFAULT '',
            error_text TEXT NOT NULL DEFAULT '',
            tools_used TEXT NOT NULL DEFAULT '',
            memory_used TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            completed_at INTEGER
        )"""
    )
    state.db.execute(
        """CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL DEFAULT '',
            request_trace_id TEXT NOT NULL DEFAULT '',
            chat_id INTEGER NOT NULL DEFAULT 0,
            phase TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            evidence_text TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_chat_updated ON task_runs(chat_id, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_request_trace ON task_runs(request_trace_id, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs(status, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_created ON task_events(task_id, created_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_task_events_chat_created ON task_events(chat_id, created_at DESC)")
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS moderation_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_by_user_id INTEGER, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), expires_at INTEGER, active INTEGER NOT NULL DEFAULT 1, completed_at INTEGER)"
    )
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_active_expires ON moderation_actions(active, expires_at)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_chat_user ON moderation_actions(chat_id, user_id, action, active)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_request_diagnostics_chat_id_id ON request_diagnostics(chat_id, id)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_repair_journal_created_at ON repair_journal(created_at DESC, id DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_incidents_created_at ON self_heal_incidents(created_at DESC, id DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_incidents_problem_state ON self_heal_incidents(problem_type, state, updated_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_transitions_incident ON self_heal_transitions(incident_id, created_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_attempts_incident ON self_heal_attempts(incident_id, created_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_verifications_incident ON self_heal_verifications(incident_id, created_at DESC)")
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_self_heal_lessons_incident ON self_heal_lessons(incident_id, created_at DESC)")
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', created_by_user_id INTEGER, expires_at INTEGER, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    state.db.execute("CREATE INDEX IF NOT EXISTS idx_warnings_chat_user ON warnings(chat_id, user_id, id)")
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS warn_settings (chat_id INTEGER PRIMARY KEY, warn_limit INTEGER NOT NULL DEFAULT 3, warn_mode TEXT NOT NULL DEFAULT 'mute', warn_expire_seconds INTEGER NOT NULL DEFAULT 0)"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS welcome_settings (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, template TEXT NOT NULL DEFAULT 'Добро пожаловать, {full_name}!')"
    )
    state.db.execute(
        "CREATE TABLE IF NOT EXISTS ui_sessions (user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL DEFAULT 0, active_panel TEXT NOT NULL DEFAULT 'home', pending_action TEXT NOT NULL DEFAULT '', pending_payload TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')))"
    )
    ensure_warn_settings_columns(state)
    ensure_warnings_columns(state)
    ensure_chat_events_columns(state)
    ensure_user_memory_profile_columns(state)
    ensure_world_state_registry_columns(state)
    ensure_request_diagnostics_columns(state)
    state._rebuild_chat_events_fts()
    seed_self_model_state(state, self_model_defaults=self_model_defaults)
    seed_skill_memory(state, default_skill_library=default_skill_library)
    seed_drive_scores(state, drive_names=drive_names)


def ensure_warn_settings_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(warn_settings)").fetchall()}
    if "warn_expire_seconds" not in columns:
        state.db.execute("ALTER TABLE warn_settings ADD COLUMN warn_expire_seconds INTEGER NOT NULL DEFAULT 0")


def ensure_warnings_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(warnings)").fetchall()}
    if "expires_at" not in columns:
        state.db.execute("ALTER TABLE warnings ADD COLUMN expires_at INTEGER")


def ensure_chat_events_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(chat_events)").fetchall()}
    required = {
        "message_id": "INTEGER",
        "username": "TEXT",
        "first_name": "TEXT",
        "last_name": "TEXT",
        "chat_type": "TEXT",
        "reply_to_message_id": "INTEGER",
        "reply_to_user_id": "INTEGER",
        "reply_to_username": "TEXT",
        "forward_origin": "TEXT",
        "has_media": "INTEGER",
        "file_kind": "TEXT",
        "is_edited": "INTEGER",
    }
    for name, type_name in required.items():
        if name not in columns:
            state.db.execute(f"ALTER TABLE chat_events ADD COLUMN {name} {type_name}")


def ensure_user_memory_profile_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(user_memory_profiles)").fetchall()}
    if "ai_summary" not in columns:
        state.db.execute("ALTER TABLE user_memory_profiles ADD COLUMN ai_summary TEXT NOT NULL DEFAULT ''")


def ensure_world_state_registry_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(world_state_registry)").fetchall()}
    required = {
        "confidence": "REAL NOT NULL DEFAULT 0.0",
        "ttl_seconds": "INTEGER NOT NULL DEFAULT 0",
        "verification_method": "TEXT NOT NULL DEFAULT ''",
        "stale_flag": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in required.items():
        if name not in columns:
            state.db.execute(f"ALTER TABLE world_state_registry ADD COLUMN {name} {definition}")


def ensure_request_diagnostics_columns(state: "BridgeState") -> None:
    columns = {row[1] for row in state.db.execute("PRAGMA table_info(request_diagnostics)").fetchall()}
    required = {
        "request_kind": "TEXT NOT NULL DEFAULT ''",
        "response_mode": "TEXT NOT NULL DEFAULT ''",
        "sources": "TEXT NOT NULL DEFAULT ''",
        "tools_used": "TEXT NOT NULL DEFAULT ''",
        "memory_used": "TEXT NOT NULL DEFAULT ''",
        "confidence": "REAL NOT NULL DEFAULT 0.0",
        "freshness": "TEXT NOT NULL DEFAULT ''",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "request_trace_id": "TEXT NOT NULL DEFAULT ''",
        "task_id": "TEXT NOT NULL DEFAULT ''",
        "tools_attempted": "TEXT NOT NULL DEFAULT ''",
        "contract_satisfied": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in required.items():
        if name not in columns:
            state.db.execute(f"ALTER TABLE request_diagnostics ADD COLUMN {name} {definition}")


def seed_self_model_state(state: "BridgeState", *, self_model_defaults: dict[str, str]) -> None:
    state.db.execute(
        """INSERT INTO self_model_state(
            state_id, identity, active_mode, capabilities, hard_limitations, trusted_tools,
            confidence_policy, current_goals, active_constraints, honesty_rules,
            jarvis_style_invariants, enterprise_style_invariants, last_route_kind, last_outcome
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(state_id) DO NOTHING""",
        (
            "primary",
            self_model_defaults["identity"],
            state.default_mode,
            self_model_defaults["capabilities"],
            self_model_defaults["hard_limitations"],
            self_model_defaults["trusted_tools"],
            self_model_defaults["confidence_policy"],
            self_model_defaults["current_goals"],
            self_model_defaults["active_constraints"],
            self_model_defaults["honesty_rules"],
            self_model_defaults["jarvis_style_invariants"],
            self_model_defaults["enterprise_style_invariants"],
            "",
            "",
        ),
    )


def seed_skill_memory(
    state: "BridgeState",
    *,
    default_skill_library: Sequence[tuple[str, str, str, str]],
) -> None:
    for skill_key, trigger_tags, procedure, source in default_skill_library:
        state.db.execute(
            """INSERT INTO skill_memory(skill_key, title, trigger_tags, procedure, reliability, use_count, source, notes, last_used_at)
            VALUES(?, ?, ?, ?, ?, 0, ?, '', 0)
            ON CONFLICT(skill_key) DO NOTHING""",
            (skill_key, skill_key.replace("_", " "), trigger_tags, procedure, 0.75, source),
        )


def seed_drive_scores(state: "BridgeState", *, drive_names: Sequence[str]) -> None:
    for drive_name in drive_names:
        state.db.execute(
            "INSERT INTO drive_scores(drive_name, score, reason) VALUES(?, 0, 'not-initialized') ON CONFLICT(drive_name) DO NOTHING",
            (drive_name,),
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
