import { isAdmin, setAccessMode } from '../admin/access';
import { getRecentLogs } from '../logger';
import {
  clearChatHistory,
  clearChatMemory,
  clearUserMemory,
  deleteAccessRule,
  getBotSetting,
  getChatMemory,
  getChatReplyMode,
  getPersonaMode,
  getSearchPreference,
  getStats,
  getUserMemory,
  listAccessRules,
  setBotSetting,
  setChatReplyMode,
  setPersonaMode,
  setSearchPreference,
  upsertAccessRule,
} from '../memory/store';
import type { BotAccessMode, Env, ResponseStyle } from '../types';
import type { CallbackQuery, TelegramMessage } from '../telegram/types';
import { mainKeyboard } from '../telegram/ui';
import { extractCommand } from '../telegram/updates';

const styleValues: ResponseStyle[] = ['concise', 'normal', 'technical', 'deep', 'admin'];
const modeValues: BotAccessMode[] = ['public', 'selective', 'admin_only', 'off', 'test'];
const replyModeValues = ['smart', 'always', 'silent'] as const;

type ReplyMode = (typeof replyModeValues)[number];

type CommandResult = { text: string; options?: Record<string, unknown>; handled: boolean };

function formatLines(lines: string[]): string {
  return lines.join('\n');
}

function keyboardOptions(): Record<string, unknown> {
  return { reply_markup: mainKeyboard() };
}

function formatPreview(label: string, text: string, emptyText: string): string {
  if (!text.trim()) {
    return `${label}: ${emptyText}`;
  }
  return `${label}:\n${text.slice(0, 900)}`;
}

async function formatAdminSnapshot(env: Env): Promise<string> {
  const [globalMode, publicResponses, replyOnlyAdmin, allowRules, muteRules, stats] = await Promise.all([
    getBotSetting(env, 'global_access_mode'),
    getBotSetting(env, 'public_responses'),
    getBotSetting(env, 'reply_only_admin'),
    listAccessRules(env, 'allow'),
    listAccessRules(env, 'mute'),
    getStats(env),
  ]);

  return formatLines([
    `Глобальный режим: ${globalMode ?? env.BOT_MODE_DEFAULT}`,
    `Публичные ответы: ${publicResponses ?? 'false'}`,
    `Только админ: ${replyOnlyAdmin ?? 'false'}`,
    `Whitelist правил: ${allowRules.length}`,
    `Mute правил: ${muteRules.length}`,
    `Пользователей: ${stats.users}`,
    `Чатов: ${stats.chats}`,
    `Сообщений: ${stats.messages}`,
    `Логов: ${stats.logs}`,
  ]);
}

export async function handleCommand(
  env: Env,
  message: TelegramMessage,
): Promise<CommandResult> {
  const text = message.text ?? '';
  const { command, args } = extractCommand(text);
  const userId = String(message.from?.id ?? '');
  const chatId = String(message.chat.id);
  const isBotAdmin = isAdmin(env, message.from?.id);

  switch (command) {
    case '/start':
      return {
        handled: true,
        options: keyboardOptions(),
        text: formatLines([
          `Я ${env.BOT_NAME}.`,
          '',
          'Это production-ready foundation Telegram AI-ассистента на Cloudflare Workers: webhook, Workers AI, память в D1, доступ, логирование и управляемый режим ответа в группах.',
          '',
          'В личных сообщениях отвечаю всегда. В группах работаю через умное молчание: реагирую на команды, reply, упоминания и активный режим чата.',
          '',
          'Начать лучше с /help и /status.',
        ]),
      };
    case '/help':
      return {
        handled: true,
        options: keyboardOptions(),
        text: formatLines([
          'Базовые команды:',
          '/start',
          '/help',
          '/reset',
          '/mode [concise|normal|technical|deep|admin]',
          '/status',
          '/memory [show|reset_user|reset_chat|reset_all]',
          '/search [auto|on|off|status]',
          '/whoami',
          '/about',
          '',
          'Команды управления чатом:',
          '/chatmode [smart|always|silent]',
          '',
          'Админ-команды:',
          '/admin',
          '/public_on, /public_off',
          '/reply_only_me',
          '/allow_user <id>, /deny_user <id>',
          '/allow_chat <id>, /deny_chat <id>',
          '/mute_chat [chat_id], /unmute_chat [chat_id]',
          '/set_mode <public|selective|admin_only|off|test>',
          '/logs, /stats',
        ]),
      };
    case '/reset':
      await clearChatHistory(env, Number(chatId));
      await clearChatMemory(env, Number(chatId));
      if (message.chat.type === 'private' && userId) {
        await clearUserMemory(env, Number(userId));
      }
      return {
        handled: true,
        options: keyboardOptions(),
        text: 'История текущего диалога очищена. Память чата сброшена. В личном чате также очищена персональная память.',
      };
    case '/mode': {
      if (!args[0]) {
        const current = await getPersonaMode(env, 'user', userId);
        return {
          handled: true,
          options: keyboardOptions(),
          text: `Текущий стиль ответа: ${current ?? 'normal'}. Доступно: ${styleValues.join(', ')}`,
        };
      }
      const nextStyle = args[0] as ResponseStyle;
      if (!styleValues.includes(nextStyle)) {
        return { handled: true, text: `Неизвестный режим. Доступно: ${styleValues.join(', ')}` };
      }
      await setPersonaMode(env, 'user', userId, nextStyle);
      return { handled: true, options: keyboardOptions(), text: `Стиль ответа переключён на: ${nextStyle}` };
    }
    case '/chatmode': {
      if (!args[0]) {
        const current = await getChatReplyMode(env, Number(chatId));
        return {
          handled: true,
          options: keyboardOptions(),
          text: `Режим ответов для этого чата: ${current ?? 'smart'}. Доступно: ${replyModeValues.join(', ')}`,
        };
      }
      const nextMode = args[0] as ReplyMode;
      if (!replyModeValues.includes(nextMode)) {
        return { handled: true, text: `Неизвестный chat mode. Доступно: ${replyModeValues.join(', ')}` };
      }
      if (message.chat.type !== 'private' && !isBotAdmin) {
        return { handled: true, text: 'Менять chat mode в группе может только администратор бота.' };
      }
      await setChatReplyMode(env, Number(chatId), nextMode);
      return { handled: true, options: keyboardOptions(), text: `Режим ответов в чате переключён на: ${nextMode}` };
    }
    case '/status': {
      const [persona, globalMode, replyOnlyAdmin, userMemory, chatMemory, searchPref, chatReplyMode] = await Promise.all([
        getPersonaMode(env, 'user', userId),
        getBotSetting(env, 'global_access_mode'),
        getBotSetting(env, 'reply_only_admin'),
        getUserMemory(env, Number(userId)),
        getChatMemory(env, Number(chatId)),
        getSearchPreference(env, message.chat.type === 'private' ? 'user' : 'chat', message.chat.type === 'private' ? userId : chatId),
        getChatReplyMode(env, Number(chatId)),
      ]);
      return {
        handled: true,
        options: keyboardOptions(),
        text: formatLines([
          `Бот: ${env.BOT_NAME}`,
          `Тип чата: ${message.chat.type}`,
          `Глобальный режим доступа: ${globalMode ?? env.BOT_MODE_DEFAULT}`,
          `Режим ответов чата: ${chatReplyMode ?? (message.chat.type === 'private' ? 'always' : 'smart')}`,
          `Стиль ответа: ${persona ?? 'normal'}`,
          `Поиск: ${searchPref ? (searchPref.enabled ? searchPref.mode : 'off') : env.SEARCH_MODE}`,
          `Только админ: ${replyOnlyAdmin ?? 'false'}`,
          `Память: ${env.MEMORY_MODE}`,
          `Память пользователя: ${userMemory ? 'есть' : 'пусто'}`,
          `Память чата: ${chatMemory ? 'есть' : 'пусто'}`,
          `Workers AI model: ${env.WORKERS_AI_MODEL}`,
        ]),
      };
    }
    case '/memory': {
      const action = args[0] ?? 'show';
      if (action === 'show') {
        const [userMemory, chatMemory] = await Promise.all([
          getUserMemory(env, Number(userId)),
          getChatMemory(env, Number(chatId)),
        ]);
        return {
          handled: true,
          options: keyboardOptions(),
          text: formatLines([
            formatPreview('Память пользователя', userMemory, 'пока пусто'),
            '',
            formatPreview('Память чата', chatMemory, 'пока пусто'),
          ]),
        };
      }
      if (action === 'reset_user') {
        await clearUserMemory(env, Number(userId));
        return { handled: true, options: keyboardOptions(), text: 'Персональная память пользователя очищена.' };
      }
      if (action === 'reset_chat') {
        await clearChatMemory(env, Number(chatId));
        await clearChatHistory(env, Number(chatId));
        return { handled: true, options: keyboardOptions(), text: 'Память и история текущего чата очищены.' };
      }
      if (action === 'reset_all') {
        await clearUserMemory(env, Number(userId));
        await clearChatMemory(env, Number(chatId));
        await clearChatHistory(env, Number(chatId));
        return { handled: true, options: keyboardOptions(), text: 'История и вся доступная память для этого контекста очищены.' };
      }
      return { handled: true, text: 'Доступно: /memory show, /memory reset_user, /memory reset_chat, /memory reset_all' };
    }
    case '/search': {
      const scopeType = message.chat.type === 'private' ? 'user' : 'chat';
      const scopeId = message.chat.type === 'private' ? userId : chatId;
      const action = args[0] ?? 'status';
      if (action === 'status') {
        const pref = await getSearchPreference(env, scopeType, scopeId);
        return {
          handled: true,
          options: keyboardOptions(),
          text: `Поиск для текущего контекста: ${pref ? (pref.enabled ? pref.mode : 'off') : env.SEARCH_MODE}`,
        };
      }
      if (!['auto', 'on', 'off'].includes(action)) {
        return { handled: true, text: 'Доступно: /search auto, /search on, /search off, /search status' };
      }
      await setSearchPreference(env, scopeType, scopeId, action !== 'off', action === 'off' ? 'auto' : action);
      return {
        handled: true,
        options: keyboardOptions(),
        text: `Поиск для текущего контекста переключён на: ${action}`,
      };
    }
    case '/whoami':
      return {
        handled: true,
        options: keyboardOptions(),
        text: formatLines([
          `Ваш user id: ${userId || 'unknown'}`,
          `Чат id: ${chatId}`,
          `Username: ${message.from?.username ? `@${message.from.username}` : 'не указан'}`,
          `Имя: ${message.from?.first_name ?? 'unknown'}`,
          `Тип чата: ${message.chat.type}`,
        ]),
      };
    case '/about':
      return {
        handled: true,
        options: keyboardOptions(),
        text: formatLines([
          `${env.BOT_NAME} - русскоязычный интеллектуальный ассистент на Cloudflare Workers.`,
          'Стек: Telegram webhook, Workers AI, D1-память, KV-кэш, режимы доступа и умное молчание в группах.',
          `Проектовая идентичность: ${env.SYSTEM_BRAND_NAME}. Создатель: ${env.CREATOR_NAME}.`,
        ]),
      };
    case '/admin': {
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      return { handled: true, options: keyboardOptions(), text: await formatAdminSnapshot(env) };
    }
    case '/public_on':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      await setBotSetting(env, 'public_responses', 'true');
      await setBotSetting(env, 'reply_only_admin', 'false');
      await setAccessMode(env, 'public');
      return { handled: true, options: keyboardOptions(), text: 'Публичные ответы включены.' };
    case '/public_off':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      await setBotSetting(env, 'public_responses', 'false');
      await setBotSetting(env, 'reply_only_admin', 'false');
      await setAccessMode(env, 'selective');
      return { handled: true, options: keyboardOptions(), text: 'Публичные ответы выключены. Активен выборочный режим.' };
    case '/reply_only_me':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      await setBotSetting(env, 'reply_only_admin', 'true');
      return { handled: true, options: keyboardOptions(), text: 'Теперь бот отвечает только администратору.' };
    case '/allow_user':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи user id: /allow_user <id>' };
      await upsertAccessRule(env, 'user', args[0], 'allow');
      return { handled: true, options: keyboardOptions(), text: `Пользователь ${args[0]} добавлен в whitelist.` };
    case '/deny_user':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи user id: /deny_user <id>' };
      await deleteAccessRule(env, 'user', args[0], 'allow');
      return { handled: true, options: keyboardOptions(), text: `Пользователь ${args[0]} удалён из whitelist.` };
    case '/allow_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи chat id: /allow_chat <id>' };
      await upsertAccessRule(env, 'chat', args[0], 'allow');
      return { handled: true, options: keyboardOptions(), text: `Чат ${args[0]} добавлен в whitelist.` };
    case '/deny_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи chat id: /deny_chat <id>' };
      await deleteAccessRule(env, 'chat', args[0], 'allow');
      return { handled: true, options: keyboardOptions(), text: `Чат ${args[0]} удалён из whitelist.` };
    case '/mute_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      await upsertAccessRule(env, 'chat', args[0] ?? chatId, 'mute');
      return { handled: true, options: keyboardOptions(), text: `Чат ${args[0] ?? chatId} заглушён.` };
    case '/unmute_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      await deleteAccessRule(env, 'chat', args[0] ?? chatId, 'mute');
      return { handled: true, options: keyboardOptions(), text: `Чат ${args[0] ?? chatId} выведен из mute.` };
    case '/set_mode':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0] || !modeValues.includes(args[0] as BotAccessMode)) {
        return { handled: true, text: `Доступно: ${modeValues.join(', ')}` };
      }
      await setBotSetting(env, 'reply_only_admin', 'false');
      await setAccessMode(env, args[0] as BotAccessMode);
      return { handled: true, options: keyboardOptions(), text: `Глобальный режим переключён на ${args[0]}.` };
    case '/logs': {
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      const logs = await getRecentLogs(env, 10);
      return {
        handled: true,
        text: logs.length
          ? logs.map((log) => `[${String(log.created_at)}] ${String(log.level).toUpperCase()} ${String(log.event_type)}: ${String(log.message)}`).join('\n')
          : 'Логи пока пусты.',
      };
    }
    case '/stats': {
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      const stats = await getStats(env);
      return {
        handled: true,
        text: Object.entries(stats).map(([key, value]) => `${key}: ${value}`).join('\n'),
      };
    }
    default:
      return { handled: false, text: '' };
  }
}

function mapCallbackToCommand(callbackData: string, callback: CallbackQuery): string | null {
  switch (callbackData) {
    case 'help':
      return '/help';
    case 'status':
      return '/status';
    case 'reset':
      return '/reset';
    case 'mode':
      return '/mode';
    case 'about':
      return '/about';
    case 'admin':
      return '/admin';
    case 'search:auto':
      return '/search auto';
    case 'search:off':
      return '/search off';
    case 'public:on':
      return '/public_on';
    case 'public:off':
      return '/public_off';
    default:
      if (callbackData.startsWith('search:')) {
        return `/search ${callbackData.split(':')[1]}`;
      }
      if (callbackData.startsWith('public:')) {
        return callbackData.endsWith('on') ? '/public_on' : '/public_off';
      }
      if (callback.message?.chat.type === 'private') {
        return '/status';
      }
      return null;
  }
}

export async function handleCallback(
  env: Env,
  callback: CallbackQuery,
): Promise<{ toast: string; messageText?: string; options?: Record<string, unknown> }> {
  const mapped = mapCallbackToCommand(callback.data ?? '', callback);
  if (!mapped || !callback.message) {
    return { toast: 'Действие недоступно в этом контексте.' };
  }

  const commandMessage: TelegramMessage = {
    ...callback.message,
    from: callback.from,
    text: mapped,
  };
  const result = await handleCommand(env, commandMessage);
  if (!result.handled) {
    return { toast: 'Команда не обработана.' };
  }

  return {
    toast: 'Готово',
    messageText: result.text,
    options: result.options,
  };
}
