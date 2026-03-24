import type { Env, JsonObject } from '../types';

export async function logEvent(
  env: Env,
  level: 'debug' | 'info' | 'warn' | 'error',
  eventType: string,
  message: string,
  context: JsonObject = {},
): Promise<void> {
  console[level === 'debug' ? 'log' : level](`[${eventType}] ${message}`, context);
  try {
    await env.DB.prepare(
      'INSERT INTO logs (level, event_type, message, context_json) VALUES (?, ?, ?, ?)',
    )
      .bind(level, eventType, message, JSON.stringify(context))
      .run();
  } catch (error) {
    console.error('Failed to persist log', error);
  }
}

export async function getRecentLogs(env: Env, limit = 20): Promise<Array<Record<string, unknown>>> {
  const result = await env.DB.prepare(
    'SELECT level, event_type, message, context_json, created_at FROM logs ORDER BY created_at DESC LIMIT ?',
  )
    .bind(limit)
    .all<Record<string, unknown>>();

  return result.results ?? [];
}
