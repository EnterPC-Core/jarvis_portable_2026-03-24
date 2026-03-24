import { getAllowedChatsFromEnv, getAllowedUsersFromEnv, isTruthy } from '../utils/env';
import { getBotSetting, hasAccessRule, setBotSetting } from '../memory/store';
import type { AccessDecision, BotAccessMode, Env } from '../types';
import type { TelegramMessage } from '../telegram/types';

export function isAdmin(env: Env, userId?: number): boolean {
  return String(userId ?? '') === env.TELEGRAM_ADMIN_ID;
}

export async function decideAccess(
  env: Env,
  message: TelegramMessage,
  mode: BotAccessMode,
): Promise<AccessDecision> {
  const userId = String(message.from?.id ?? '');
  const chatId = String(message.chat.id);

  if (mode === 'off') {
    return { allowed: false, reason: 'bot_off' };
  }

  if (await hasAccessRule(env, 'chat', chatId, 'mute')) {
    return { allowed: false, reason: 'chat_muted' };
  }

  if (isAdmin(env, message.from?.id)) {
    return { allowed: true, reason: 'admin' };
  }

  if (isTruthy((await getBotSetting(env, 'reply_only_admin')) ?? 'false')) {
    return { allowed: false, reason: 'admin_only_replies' };
  }

  if (mode === 'admin_only') {
    return { allowed: false, reason: 'admin_only_mode' };
  }

  if (
    mode === 'public' ||
    isTruthy(env.ALLOW_PUBLIC_ACCESS) ||
    isTruthy((await getBotSetting(env, 'public_responses')) ?? 'false')
  ) {
    return { allowed: true, reason: 'public_mode' };
  }

  const allowedUsers = getAllowedUsersFromEnv(env);
  const allowedChats = getAllowedChatsFromEnv(env);

  if (allowedUsers.has(userId) || allowedChats.has(chatId)) {
    return { allowed: true, reason: 'env_whitelist' };
  }

  if (await hasAccessRule(env, 'user', userId, 'allow')) {
    return { allowed: true, reason: 'user_whitelist' };
  }

  if (await hasAccessRule(env, 'chat', chatId, 'allow')) {
    return { allowed: true, reason: 'chat_whitelist' };
  }

  if (mode === 'test') {
    return { allowed: false, reason: 'test_mode_block' };
  }

  return { allowed: false, reason: 'not_whitelisted' };
}

export async function setAccessMode(env: Env, mode: BotAccessMode): Promise<void> {
  await setBotSetting(env, 'global_access_mode', mode);
}
