CREATE INDEX idx_chat_events_chat_id_id ON chat_events(chat_id, id);

CREATE INDEX idx_chat_history_chat_id_id ON chat_history(chat_id, id);

CREATE INDEX idx_memory_facts_chat_id_id ON memory_facts(chat_id, id);

CREATE INDEX idx_moderation_actions_active_expires ON moderation_actions(active, expires_at);

CREATE INDEX idx_moderation_actions_chat_user ON moderation_actions(chat_id, user_id, action, active);

CREATE INDEX idx_warnings_chat_user ON warnings(chat_id, user_id, id);

CREATE TABLE achievement_catalog (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                badge TEXT NOT NULL,
                rarity TEXT NOT NULL,
                category TEXT NOT NULL,
                metric TEXT NOT NULL,
                target_value INTEGER NOT NULL,
                hidden INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT ''
            );

CREATE TABLE achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement TEXT,
            earned_at REAL,
            badge TEXT
        );

CREATE TABLE actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            user_id INTEGER,
            admin_id INTEGER,
            chat_id INTEGER,
            description TEXT,
            old_value TEXT,
            new_value TEXT,
            timestamp REAL
        );

CREATE TABLE admin_action_state (
            admin_id INTEGER PRIMARY KEY,
            action TEXT,
            data TEXT,
            created_at REAL
        );

CREATE TABLE appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            appeal_text TEXT,
            timestamp REAL,
            status TEXT DEFAULT "pending",
            admin_response TEXT,
            responded_at REAL
        );

CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_user_id INTEGER,
            chat_id INTEGER,
            details TEXT,
            timestamp REAL
        );

CREATE TABLE automation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT,
            task_type TEXT,
            chat_id INTEGER,
            schedule TEXT,
            last_run REAL,
            next_run REAL,
            enabled BOOLEAN DEFAULT 1
        );

CREATE TABLE backup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_name TEXT,
            backup_size INTEGER,
            created_at REAL,
            restored_at REAL
        );

CREATE TABLE behavior_rating (
            user_id INTEGER PRIMARY KEY,
            status TEXT DEFAULT "адекватный",
            violations_count INTEGER DEFAULT 0,
            last_updated REAL DEFAULT 0
        );

CREATE TABLE bot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE bot_settings (
            chat_id INTEGER PRIMARY KEY,
            
            -- 🔧 ОСНОВНЫЕ НАСТРОЙКИ
            moderation_enabled BOOLEAN DEFAULT 1,
            ai_model_selected TEXT DEFAULT 'x-ai/grok-4.1-fast',
            ai_temperature REAL DEFAULT 0.5,
            
            -- 📊 СПАМ ДЕТЕКТОР
            spam_detection_enabled BOOLEAN DEFAULT 1,
            spam_threshold INTEGER DEFAULT 10,
            spam_window_minutes INTEGER DEFAULT 5,
            spam_auto_action TEXT DEFAULT 'mute',
            
            -- 🔍 ФАКТЧЕК И ЛОЖЬ
            factcheck_enabled BOOLEAN DEFAULT 1,
            factcheck_min_level INTEGER DEFAULT 11,
            factcheck_sensitivity REAL DEFAULT 0.7,
            
            -- 🚫 ПРОФАНИТИ И ОСКОРБЛЕНИЯ
            profanity_enabled BOOLEAN DEFAULT 1,
            profanity_threshold REAL DEFAULT 0.8,
            profanity_auto_action TEXT DEFAULT 'warn',
            
            -- ☠️ ТОКСИЧНОСТЬ
            toxicity_enabled BOOLEAN DEFAULT 1,
            toxicity_threshold REAL DEFAULT 0.7,
            toxicity_auto_action TEXT DEFAULT 'warn',
            
            -- 🔨 БАН И МУТ
            auto_ban_threshold INTEGER DEFAULT 5,
            auto_mute_threshold INTEGER DEFAULT 3,
            auto_mute_duration INTEGER DEFAULT 3600,
            
            -- ⭐ РЕЙТИНГ И РЕПУТАЦИЯ
            reputation_system_enabled BOOLEAN DEFAULT 1,
            reputation_per_positive_msg INTEGER DEFAULT 1,
            reputation_per_help INTEGER DEFAULT 5,
            reputation_per_answer INTEGER DEFAULT 3,
            
            -- 📢 УВЕДОМЛЕНИЯ
            notify_violations BOOLEAN DEFAULT 1,
            notify_achievements BOOLEAN DEFAULT 1,
            notify_bans BOOLEAN DEFAULT 1,
            notify_appeals BOOLEAN DEFAULT 1,
            
            -- 💾 ИСТОРИЯ И ЛОГИ
            message_history_days INTEGER DEFAULT 30,
            keep_violation_history BOOLEAN DEFAULT 1,
            keep_moderation_log BOOLEAN DEFAULT 1,
            
            -- 🎯 РАСШИРЕННЫЕ ОПЦИИ
            whitelist_mode BOOLEAN DEFAULT 1,
            require_acceptance BOOLEAN DEFAULT 1,
            auto_reply_enabled BOOLEAN DEFAULT 0,
            
            created_at REAL DEFAULT 0,
            updated_at REAL DEFAULT 0
        , max_messages_per_minute INTEGER DEFAULT 10, max_warnings_before_mute INTEGER DEFAULT 3, mute_duration_minutes INTEGER DEFAULT 30, allow_links BOOLEAN DEFAULT 1, allow_invites BOOLEAN DEFAULT 0, log_all_messages BOOLEAN DEFAULT 1, log_deletions BOOLEAN DEFAULT 1, auto_welcome BOOLEAN DEFAULT 0, welcome_message TEXT DEFAULT '', require_captcha BOOLEAN DEFAULT 0, captcha_level INTEGER DEFAULT 1, inactivity_timeout_days INTEGER DEFAULT 90, min_message_length INTEGER DEFAULT 1, max_message_length INTEGER DEFAULT 4096, allow_non_russian BOOLEAN DEFAULT 1);

CREATE TABLE chat_context (
            chat_id INTEGER,
            message_text TEXT,
            user_name TEXT,
            timestamp REAL
        );

CREATE TABLE chat_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER,
        role TEXT NOT NULL,
        message_type TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        message_id INTEGER,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        chat_type TEXT,
        reply_to_message_id INTEGER,
        reply_to_user_id INTEGER,
        reply_to_username TEXT,
        forward_origin TEXT,
        has_media INTEGER,
        file_kind TEXT,
        is_edited INTEGER
    );

CREATE VIRTUAL TABLE chat_events_fts USING fts5(text, content='chat_events', content_rowid='id', tokenize='unicode61');

CREATE TABLE 'chat_events_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'chat_events_fts_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'chat_events_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'chat_events_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TABLE chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    );

CREATE TABLE chat_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            date_start REAL,
            total_messages INTEGER DEFAULT 0,
            total_violations INTEGER DEFAULT 0,
            total_deletes INTEGER DEFAULT 0,
            total_warns INTEGER DEFAULT 0,
            total_bans INTEGER DEFAULT 0,
            spam_detected INTEGER DEFAULT 0,
            toxicity_score REAL DEFAULT 0.0,
            health_score REAL DEFAULT 100.0
        );

CREATE TABLE chat_modes (chat_id INTEGER PRIMARY KEY, mode TEXT NOT NULL);

CREATE TABLE chat_summaries (chat_id INTEGER PRIMARY KEY, summary TEXT NOT NULL, updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')));

CREATE TABLE custom_moderation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            rule_name TEXT,
            pattern TEXT,
            action TEXT DEFAULT 'warn',
            severity INTEGER DEFAULT 1,
            enabled BOOLEAN DEFAULT 1,
            created_at REAL
        );

CREATE TABLE greetings (
            user_id INTEGER PRIMARY KEY,
            greeted_at REAL
        );

CREATE TABLE memory_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        created_by_user_id INTEGER,
        fact TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    );

CREATE TABLE message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            first_name TEXT,
            message_text TEXT,
            timestamp REAL,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at REAL
        );

CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            message_text TEXT,
            timestamp REAL,
            was_deleted BOOLEAN DEFAULT FALSE,
            violation_reason TEXT
        );

CREATE TABLE moderation_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_by_user_id INTEGER,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        expires_at INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        completed_at INTEGER
    );

CREATE TABLE moderation_config (
            chat_id INTEGER PRIMARY KEY,
            spam_threshold INTEGER DEFAULT 5,
            spam_window_minutes INTEGER DEFAULT 5,
            auto_delete_spam BOOLEAN DEFAULT 1,
            auto_warn_spam BOOLEAN DEFAULT 1,
            flood_threshold INTEGER DEFAULT 10,
            flood_action TEXT DEFAULT 'mute'
        , ai_temperature REAL DEFAULT 0.5, factcheck_enabled BOOLEAN DEFAULT 1, factcheck_min_level INTEGER DEFAULT 11, moderation_enabled BOOLEAN DEFAULT 1, spam_detection_enabled BOOLEAN DEFAULT 1, profanity_enabled BOOLEAN DEFAULT 1, toxicity_threshold REAL DEFAULT 0.7, auto_ban_threshold INTEGER DEFAULT 5);

CREATE TABLE moderation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            user_id INTEGER,
            target_user_id INTEGER,
            chat_id INTEGER,
            reason TEXT,
            action_details TEXT,
            timestamp REAL,
            executed_by TEXT DEFAULT 'SYSTEM'
        );

CREATE TABLE owner_settings (
            owner_id INTEGER PRIMARY KEY,
            selected_model TEXT DEFAULT 'meta-llama/llama-4-maverick:free',
            updated_at REAL
        );

CREATE TABLE permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_name TEXT UNIQUE NOT NULL,
            category TEXT,
            description TEXT
        );

CREATE TABLE private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            message_text TEXT,
            timestamp REAL,
            forwarded_to_admin BOOLEAN DEFAULT FALSE
        );

CREATE TABLE role_permissions (
            role_id INTEGER,
            permission_id INTEGER,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (permission_id) REFERENCES permissions(id)
        );

CREATE TABLE roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT UNIQUE NOT NULL,
            description TEXT,
            color TEXT,
            created_at REAL
        );

CREATE TABLE sent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            notification_type TEXT,
            ban_id INTEGER,
            sent_at REAL,
            UNIQUE(user_id, notification_type, ban_id)
        );

CREATE TABLE tracked_chats (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            chat_type TEXT,
            members_count INTEGER DEFAULT 0,
            joined_at REAL,
            last_message REAL,
            is_whitelisted INTEGER DEFAULT 0
        );

CREATE TABLE user_achievement_progress (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                progress_value INTEGER NOT NULL DEFAULT 0,
                unlocked_at REAL,
                PRIMARY KEY (user_id, code)
            );

CREATE TABLE user_adequacy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            violations_count INTEGER DEFAULT 0,
            bans_count INTEGER DEFAULT 0,
            adequacy_score REAL DEFAULT 100.0,
            last_violation REAL,
            updated_at REAL
        );

CREATE TABLE user_game_stats (
                user_id INTEGER PRIMARY KEY,
                total_score INTEGER NOT NULL DEFAULT 0,
                social_score INTEGER NOT NULL DEFAULT 0,
                quality_score INTEGER NOT NULL DEFAULT 0,
                consistency_score INTEGER NOT NULL DEFAULT 0,
                behavior_score INTEGER NOT NULL DEFAULT 100,
                prestige INTEGER NOT NULL DEFAULT 0,
                streak_days INTEGER NOT NULL DEFAULT 0,
                best_streak INTEGER NOT NULL DEFAULT 0,
                unique_days INTEGER NOT NULL DEFAULT 0,
                helpful_messages INTEGER NOT NULL DEFAULT 0,
                long_messages INTEGER NOT NULL DEFAULT 0,
                night_messages INTEGER NOT NULL DEFAULT 0,
                weekend_messages INTEGER NOT NULL DEFAULT 0,
                clean_messages INTEGER NOT NULL DEFAULT 0,
                last_message_at REAL NOT NULL DEFAULT 0,
                last_day_key TEXT NOT NULL DEFAULT '',
                duplicate_hits INTEGER NOT NULL DEFAULT 0,
                season_id TEXT NOT NULL DEFAULT '',
                season_points INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0
            );

CREATE TABLE user_message_rate (
            user_id INTEGER,
            chat_id INTEGER,
            timestamp REAL,
            PRIMARY KEY (user_id, chat_id, timestamp)
        );

CREATE TABLE user_role_assignment (
            user_id INTEGER PRIMARY KEY,
            role_id INTEGER,
            assigned_at REAL,
            assigned_by INTEGER,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        );

CREATE TABLE user_roles (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'user',
            permissions TEXT,
            created_at REAL
        );

CREATE TABLE user_season_stats (
                user_id INTEGER NOT NULL,
                season_id TEXT NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                messages INTEGER NOT NULL DEFAULT 0,
                helpful_messages INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, season_id)
            );

CREATE TABLE user_stats_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            day_start REAL,
            msg_count INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0
        );

CREATE TABLE user_stats_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            hour_start REAL,
            msg_count INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0
        );

CREATE TABLE user_stats_monthly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            month_start REAL,
            msg_count INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0
        );

CREATE TABLE user_stats_weekly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            week_start REAL,
            msg_count INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0
        );

CREATE TABLE user_stats_yearly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            year_start REAL,
            msg_count INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0
        );

CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            msg_count INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 0,
            experience INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            banned_until REAL DEFAULT 0,
            muted_until REAL DEFAULT 0,
            spam_offense_count INTEGER DEFAULT 0,
            joined_at REAL DEFAULT 0
        );

CREATE TABLE violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            violation_type TEXT,
            message_text TEXT,
            timestamp REAL,
            handled BOOLEAN DEFAULT FALSE,
            action_taken TEXT,
            explained BOOLEAN DEFAULT FALSE
        );

CREATE TABLE warn_settings (chat_id INTEGER PRIMARY KEY, warn_limit INTEGER NOT NULL DEFAULT 3, warn_mode TEXT NOT NULL DEFAULT 'mute', warn_expire_seconds INTEGER NOT NULL DEFAULT 0);

CREATE TABLE warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_by_user_id INTEGER,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        expires_at INTEGER
    );

CREATE TABLE welcome_settings (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, template TEXT NOT NULL DEFAULT 'Добро пожаловать, {full_name}!');
