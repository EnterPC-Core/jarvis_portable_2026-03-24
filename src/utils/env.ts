import type { BotAccessMode, Env, ResponseStyle } from '../types';

function parseIdList(raw: string | undefined): Set<string> {
  return new Set(
    (raw ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

export function getDefaultAccessMode(env: Env): BotAccessMode {
  const value = env.BOT_MODE_DEFAULT.trim() as BotAccessMode;
  return ['public', 'selective', 'admin_only', 'off', 'test'].includes(value)
    ? value
    : 'selective';
}

export function getDefaultStyle(): ResponseStyle {
  return 'normal';
}

export function getBotUsername(env: Env): string {
  return (env.TELEGRAM_BOT_USERNAME ?? '').trim().replace(/^@+/, '');
}

export function getAllowedUsersFromEnv(env: Env): Set<string> {
  return parseIdList(env.OPTIONAL_ALLOWED_USER_IDS);
}

export function getAllowedChatsFromEnv(env: Env): Set<string> {
  return parseIdList(env.OPTIONAL_ALLOWED_CHAT_IDS);
}

export function isTruthy(value: string | undefined): boolean {
  return ['1', 'true', 'yes', 'on'].includes((value ?? '').toLowerCase());
}

export function getDocumentTextMaxBytes(env: Env): number {
  const parsed = Number(env.DOCUMENT_TEXT_MAX_BYTES ?? '262144');
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 262144;
}
