import type { Env } from '../types';

function telegramUrl(env: Env, method: string): string {
  return `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`;
}

export async function telegramRequest<T>(env: Env, method: string, payload: unknown): Promise<T> {
  const response = await fetch(telegramUrl(env, method), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Telegram API ${method} failed: ${response.status} ${text}`);
  }

  const data = await response.json<{ ok: boolean; result: T; description?: string }>();
  if (!data.ok) {
    throw new Error(`Telegram API ${method} failed: ${data.description ?? 'unknown_error'}`);
  }

  return data.result;
}

export async function sendMessage(
  env: Env,
  chatId: number | string,
  text: string,
  options: Record<string, unknown> = {},
): Promise<void> {
  await telegramRequest(env, 'sendMessage', {
    chat_id: chatId,
    text,
    parse_mode: 'HTML',
    disable_web_page_preview: true,
    ...options,
  });
}

export async function answerCallbackQuery(env: Env, callbackQueryId: string, text?: string): Promise<void> {
  await telegramRequest(env, 'answerCallbackQuery', {
    callback_query_id: callbackQueryId,
    text,
  });
}

export async function getFile(env: Env, fileId: string): Promise<{ file_path: string }> {
  return telegramRequest(env, 'getFile', { file_id: fileId });
}

export async function setWebhook(env: Env, url: string): Promise<boolean> {
  return telegramRequest(env, 'setWebhook', { url });
}

export async function getWebhookInfo(env: Env): Promise<Record<string, unknown>> {
  return telegramRequest(env, 'getWebhookInfo', {});
}

export async function getMe(env: Env): Promise<Record<string, unknown>> {
  return telegramRequest(env, 'getMe', {});
}

export function buildTelegramFileUrl(env: Env, filePath: string): string {
  return `https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${filePath}`;
}
