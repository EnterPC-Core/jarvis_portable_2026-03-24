CREATE INDEX idx_achievement_state_user_unlock ON user_achievement_state(user_id, unlocked_at DESC);

CREATE INDEX idx_appeal_events_appeal_created_at ON appeal_events(appeal_id, created_at ASC);

CREATE INDEX idx_appeals_status_created_at ON appeals(status, created_at DESC);

CREATE INDEX idx_appeals_user_created_at ON appeals(user_id, created_at DESC);

CREATE INDEX idx_chat_events_chat_id_id ON chat_events(chat_id, id);

CREATE INDEX idx_chat_history_chat_id_id ON chat_history(chat_id, id);

CREATE INDEX idx_memory_facts_chat_id_id ON memory_facts(chat_id, id);

CREATE INDEX idx_moderation_actions_active_expires ON moderation_actions(active, expires_at);

CREATE INDEX idx_moderation_actions_chat_user ON moderation_actions(chat_id, user_id, action, active);

CREATE INDEX idx_moderation_journal_user_created_at ON moderation_journal(user_id, created_at DESC);

CREATE INDEX idx_score_events_type_created_at ON score_events(event_type, created_at DESC);

CREATE INDEX idx_score_events_user_created_at ON score_events(user_id, created_at DESC);

CREATE INDEX idx_warnings_chat_user ON warnings(chat_id, user_id, id);

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

CREATE TABLE bot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE chat_events (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER, role TEXT NOT NULL, message_type TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), message_id INTEGER, username TEXT, first_name TEXT, last_name TEXT, chat_type TEXT, reply_to_message_id INTEGER, reply_to_user_id INTEGER, reply_to_username TEXT, forward_origin TEXT, has_media INTEGER, file_kind TEXT, is_edited INTEGER);

CREATE VIRTUAL TABLE chat_events_fts USING fts5(text, content='chat_events', content_rowid='id', tokenize='unicode61');

CREATE TABLE 'chat_events_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'chat_events_fts_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'chat_events_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'chat_events_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TABLE chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE chat_modes (chat_id INTEGER PRIMARY KEY, mode TEXT NOT NULL);

CREATE TABLE chat_summaries (chat_id INTEGER PRIMARY KEY, summary TEXT NOT NULL, updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE memory_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, created_by_user_id INTEGER, fact TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

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

CREATE TABLE warn_settings (chat_id INTEGER PRIMARY KEY, warn_limit INTEGER NOT NULL DEFAULT 3, warn_mode TEXT NOT NULL DEFAULT 'mute', warn_expire_seconds INTEGER NOT NULL DEFAULT 0);

CREATE TABLE warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', created_by_user_id INTEGER, created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), expires_at INTEGER);

CREATE TABLE welcome_settings (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, template TEXT NOT NULL DEFAULT 'Добро пожаловать, {full_name}!');
