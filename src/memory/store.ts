import type { BotAccessMode, Env, ResponseStyle } from '../types';
import type { TelegramChat, TelegramUser } from '../telegram/types';

function buildMemorySnapshot(existing: string, nextLine: string, maxLines = 12): string {
  const lines = existing
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const normalizedLine = nextLine.trim();
  if (!normalizedLine) {
    return lines.join('\n');
  }

  if (lines[lines.length - 1] === normalizedLine) {
    return lines.join('\n');
  }

  lines.push(normalizedLine);
  return lines.slice(-maxLines).join('\n').slice(-4000);
}

export async function upsertUser(env: Env, user?: TelegramUser): Promise<void> {
  if (!user) return;
  await env.DB.prepare(
    `INSERT INTO users (id, username, first_name, last_name, language_code, updated_at)
     VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET
       username = excluded.username,
       first_name = excluded.first_name,
       last_name = excluded.last_name,
       language_code = excluded.language_code,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(user.id, user.username ?? null, user.first_name, user.last_name ?? null, user.language_code ?? null)
    .run();
}

export async function upsertChat(env: Env, chat: TelegramChat): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO chats (id, type, title, username, updated_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET
       type = excluded.type,
       title = excluded.title,
       username = excluded.username,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(chat.id, chat.type, chat.title ?? null, chat.username ?? null)
    .run();
}

export async function saveMessage(args: {
  env: Env;
  chatId: number;
  userId?: number;
  role: 'user' | 'assistant';
  messageText: string;
  messageKind?: string;
  telegramMessageId?: number;
}): Promise<void> {
  await args.env.DB.prepare(
    `INSERT INTO messages_history
      (chat_id, user_id, role, message_text, message_kind, telegram_message_id)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      args.chatId,
      args.userId ?? null,
      args.role,
      args.messageText,
      args.messageKind ?? 'text',
      args.telegramMessageId ?? null,
    )
    .run();
}

export async function getRecentHistory(env: Env, chatId: number, limit = 12) {
  const result = await env.DB.prepare(
    `SELECT role, message_text
     FROM messages_history
     WHERE chat_id = ?
     ORDER BY created_at DESC, id DESC
     LIMIT ?`,
  )
    .bind(chatId, limit)
    .all<{ role: 'user' | 'assistant'; message_text: string }>();

  return (result.results ?? []).reverse();
}

export async function getUserMemory(env: Env, userId?: number): Promise<string> {
  if (!userId) return '';
  const row = await env.DB.prepare('SELECT memory_summary FROM user_memory WHERE user_id = ?')
    .bind(userId)
    .first<{ memory_summary: string }>();
  return row?.memory_summary ?? '';
}

export async function getChatMemory(env: Env, chatId: number): Promise<string> {
  const row = await env.DB.prepare('SELECT memory_summary FROM chat_memory WHERE chat_id = ?')
    .bind(chatId)
    .first<{ memory_summary: string }>();
  return row?.memory_summary ?? '';
}

export async function appendUserMemory(env: Env, userId: number, fact: string): Promise<void> {
  const existing = await getUserMemory(env, userId);
  const next = buildMemorySnapshot(existing, fact);
  await env.DB.prepare(
    `INSERT INTO user_memory (user_id, memory_summary, updated_at)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(user_id) DO UPDATE SET
       memory_summary = excluded.memory_summary,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(userId, next)
    .run();
}

export async function appendChatMemory(env: Env, chatId: number, fact: string): Promise<void> {
  const existing = await getChatMemory(env, chatId);
  const next = buildMemorySnapshot(existing, fact);
  await env.DB.prepare(
    `INSERT INTO chat_memory (chat_id, memory_summary, updated_at)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(chat_id) DO UPDATE SET
       memory_summary = excluded.memory_summary,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(chatId, next)
    .run();
}

export async function clearChatHistory(env: Env, chatId: number): Promise<void> {
  await env.DB.prepare('DELETE FROM messages_history WHERE chat_id = ?').bind(chatId).run();
}

export async function clearUserMemory(env: Env, userId: number): Promise<void> {
  await env.DB.prepare('DELETE FROM user_memory WHERE user_id = ?').bind(userId).run();
}

export async function clearChatMemory(env: Env, chatId: number): Promise<void> {
  await env.DB.prepare('DELETE FROM chat_memory WHERE chat_id = ?').bind(chatId).run();
}

export async function getChatReplyMode(env: Env, chatId: number): Promise<string | null> {
  const row = await env.DB.prepare('SELECT active_reply_mode FROM chats WHERE id = ?')
    .bind(chatId)
    .first<{ active_reply_mode: string }>();
  return row?.active_reply_mode ?? null;
}

export async function setChatReplyMode(env: Env, chatId: number, mode: 'smart' | 'always' | 'silent'): Promise<void> {
  await env.DB.prepare(
    `UPDATE chats
     SET active_reply_mode = ?, updated_at = CURRENT_TIMESTAMP
     WHERE id = ?`,
  )
    .bind(mode, chatId)
    .run();
}

export async function setBotSetting(env: Env, key: string, value: string): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO bot_settings (key, value, updated_at)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(key, value)
    .run();
}

export async function getBotSetting(env: Env, key: string): Promise<string | null> {
  const row = await env.DB.prepare('SELECT value FROM bot_settings WHERE key = ?')
    .bind(key)
    .first<{ value: string }>();
  return row?.value ?? null;
}

export async function upsertAccessRule(env: Env, ruleType: string, targetId: string, action: string): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO access_rules (rule_type, target_id, action) VALUES (?, ?, ?)
     ON CONFLICT(rule_type, target_id, action) DO NOTHING`,
  )
    .bind(ruleType, targetId, action)
    .run();
}

export async function deleteAccessRule(env: Env, ruleType: string, targetId: string, action: string): Promise<void> {
  await env.DB.prepare('DELETE FROM access_rules WHERE rule_type = ? AND target_id = ? AND action = ?')
    .bind(ruleType, targetId, action)
    .run();
}

export async function hasAccessRule(env: Env, ruleType: string, targetId: string, action: string): Promise<boolean> {
  const row = await env.DB.prepare(
    'SELECT 1 as ok FROM access_rules WHERE rule_type = ? AND target_id = ? AND action = ? LIMIT 1',
  )
    .bind(ruleType, targetId, action)
    .first<{ ok: number }>();
  return Boolean(row?.ok);
}

export async function listAccessRules(env: Env, action?: string): Promise<Array<{ rule_type: string; target_id: string; action: string }>> {
  const baseSql = 'SELECT rule_type, target_id, action FROM access_rules';
  const sql = action ? `${baseSql} WHERE action = ? ORDER BY rule_type, target_id` : `${baseSql} ORDER BY action, rule_type, target_id`;
  const statement = env.DB.prepare(sql);
  const result = action
    ? await statement.bind(action).all<{ rule_type: string; target_id: string; action: string }>()
    : await statement.all<{ rule_type: string; target_id: string; action: string }>();
  return result.results ?? [];
}

export async function setSearchPreference(
  env: Env,
  scopeType: 'user' | 'chat',
  scopeId: string,
  enabled: boolean,
  mode = 'auto',
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO search_preferences (scope_type, scope_id, enabled, mode, updated_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(scope_type, scope_id) DO UPDATE SET
       enabled = excluded.enabled,
       mode = excluded.mode,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(scopeType, scopeId, enabled ? 1 : 0, mode)
    .run();
}

export async function getSearchPreference(
  env: Env,
  scopeType: 'user' | 'chat',
  scopeId: string,
): Promise<{ enabled: boolean; mode: string } | null> {
  const row = await env.DB.prepare('SELECT enabled, mode FROM search_preferences WHERE scope_type = ? AND scope_id = ?')
    .bind(scopeType, scopeId)
    .first<{ enabled: number; mode: string }>();
  if (!row) return null;
  return { enabled: Boolean(row.enabled), mode: row.mode };
}

export async function setPersonaMode(
  env: Env,
  scopeType: 'user' | 'chat',
  scopeId: string,
  responseStyle: ResponseStyle,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO persona_modes (scope_type, scope_id, response_style, updated_at)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(scope_type, scope_id) DO UPDATE SET
       response_style = excluded.response_style,
       updated_at = CURRENT_TIMESTAMP`,
  )
    .bind(scopeType, scopeId, responseStyle)
    .run();
}

export async function getPersonaMode(
  env: Env,
  scopeType: 'user' | 'chat',
  scopeId: string,
): Promise<ResponseStyle | null> {
  const row = await env.DB.prepare('SELECT response_style FROM persona_modes WHERE scope_type = ? AND scope_id = ?')
    .bind(scopeType, scopeId)
    .first<{ response_style: ResponseStyle }>();
  return row?.response_style ?? null;
}

export async function getStats(env: Env): Promise<Record<string, number>> {
  const queries = {
    users: 'SELECT COUNT(*) as count FROM users',
    chats: 'SELECT COUNT(*) as count FROM chats',
    messages: 'SELECT COUNT(*) as count FROM messages_history',
    userMemory: 'SELECT COUNT(*) as count FROM user_memory',
    chatMemory: 'SELECT COUNT(*) as count FROM chat_memory',
    logs: 'SELECT COUNT(*) as count FROM logs',
  };

  const entries = await Promise.all(
    Object.entries(queries).map(async ([key, sql]) => {
      const row = await env.DB.prepare(sql).first<{ count: number }>();
      return [key, row?.count ?? 0] as const;
    }),
  );

  return Object.fromEntries(entries);
}

export async function getResolvedAccessMode(env: Env, fallbackMode: BotAccessMode): Promise<BotAccessMode> {
  const mode = await getBotSetting(env, 'global_access_mode');
  return (mode as BotAccessMode) ?? fallbackMode;
}
