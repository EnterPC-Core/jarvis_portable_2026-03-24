import type { Env } from '../types';
import { getStats } from '../memory/store';
import { getMe, getWebhookInfo } from '../telegram/api';
import { text } from '../utils/http';
import { handleTelegramWebhook } from '../telegram/webhook';

export async function routeRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'GET' && url.pathname === '/') {
    return text('Jarvis AI worker is running');
  }

  if (request.method === 'GET' && url.pathname === '/health') {
    return Response.json({
      ok: true,
      service: env.BOT_NAME,
      url: env.BOT_PUBLIC_URL,
      now: new Date().toISOString(),
    });
  }

  if (request.method === 'GET' && url.pathname === '/admin/status') {
    const [stats, webhook, me] = await Promise.all([
      getStats(env),
      getWebhookInfo(env).catch(() => null),
      getMe(env).catch(() => null),
    ]);

    return Response.json({
      ok: true,
      service: env.BOT_NAME,
      bot_public_url: env.BOT_PUBLIC_URL,
      workers_ai_model: env.WORKERS_AI_MODEL,
      default_mode: env.BOT_MODE_DEFAULT,
      memory_mode: env.MEMORY_MODE,
      search_mode: env.SEARCH_MODE,
      stats,
      telegram: {
        bot: me,
        webhook,
      },
    });
  }

  if (request.method === 'POST' && url.pathname === '/webhook/telegram') {
    return handleTelegramWebhook(request, env);
  }

  return text('Not found', 404);
}
