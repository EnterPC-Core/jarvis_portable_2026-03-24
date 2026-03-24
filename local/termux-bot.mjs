import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ROOT = process.cwd();
const ENV_FILE = path.join(ROOT, '.dev.vars');
const STATE_FILE = path.join(ROOT, 'data', 'local-state.json');

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    if (!(key in process.env)) process.env[key] = value;
  }
}

loadEnvFile(ENV_FILE);

const env = {
  TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN ?? '',
  TELEGRAM_ADMIN_ID: process.env.TELEGRAM_ADMIN_ID ?? '6102780373',
  BOT_PUBLIC_URL: process.env.BOT_PUBLIC_URL ?? 'http://localhost',
  BOT_NAME: process.env.BOT_NAME ?? 'Jarvis AI',
  TELEGRAM_BOT_USERNAME: (process.env.TELEGRAM_BOT_USERNAME ?? '').replace(/^@+/, ''),
  BOT_MODE_DEFAULT: process.env.BOT_MODE_DEFAULT ?? 'selective',
  MEMORY_MODE: 'file',
  SEARCH_MODE: process.env.SEARCH_MODE ?? 'auto',
  ALLOW_PUBLIC_ACCESS: String(process.env.ALLOW_PUBLIC_ACCESS ?? 'false'),
  WORKERS_AI_MODEL: process.env.WORKERS_AI_MODEL ?? '@cf/meta/llama-3.1-8b-instruct-fast',
  SYSTEM_BRAND_NAME: process.env.SYSTEM_BRAND_NAME ?? 'Jarvis AI',
  CREATOR_NAME: process.env.CREATOR_NAME ?? 'Дмитрий',
  OPTIONAL_ALLOWED_USER_IDS: process.env.OPTIONAL_ALLOWED_USER_IDS ?? '',
  OPTIONAL_ALLOWED_CHAT_IDS: process.env.OPTIONAL_ALLOWED_CHAT_IDS ?? '',
  VOICE_MODE: process.env.VOICE_MODE ?? 'disabled',
  DOCUMENT_TEXT_MAX_BYTES: Number(process.env.DOCUMENT_TEXT_MAX_BYTES ?? '262144'),
  AI_PROVIDER: process.env.AI_PROVIDER ?? 'disabled',
  OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? '',
  OPENAI_MODEL: process.env.OPENAI_MODEL ?? 'gpt-4o-mini',
  OPENAI_BASE_URL: process.env.OPENAI_BASE_URL ?? 'https://api.openai.com/v1',
};

if (!env.TELEGRAM_BOT_TOKEN) {
  console.error('TELEGRAM_BOT_TOKEN is missing. Fill .dev.vars or export it in shell.');
  process.exit(1);
}

function parseIdList(raw) {
  return new Set(String(raw || '').split(',').map((item) => item.trim()).filter(Boolean));
}

function isTruthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').toLowerCase());
}

function nowIso() {
  return new Date().toISOString();
}

function defaultState() {
  return {
    offset: 0,
    users: {},
    chats: {},
    messagesHistory: [],
    userMemory: {},
    chatMemory: {},
    botSettings: {
      global_access_mode: env.BOT_MODE_DEFAULT,
      public_responses: false,
      reply_only_admin: false,
    },
    accessRules: [],
    searchPreferences: {},
    personaModes: {},
    logs: [],
  };
}

function loadState() {
  if (!fs.existsSync(STATE_FILE)) return defaultState();
  try {
    return { ...defaultState(), ...JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')) };
  } catch {
    return defaultState();
  }
}

let state = loadState();

function saveState() {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

function logEvent(level, eventType, message, context = {}) {
  const entry = { level, eventType, message, context, created_at: nowIso() };
  state.logs.push(entry);
  state.logs = state.logs.slice(-500);
  console[level === 'debug' ? 'log' : level](`[${eventType}] ${message}`, context);
  saveState();
}

function mainKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: 'Помощь', callback_data: 'help' },
        { text: 'Статус', callback_data: 'status' },
      ],
      [
        { text: 'Сброс памяти', callback_data: 'reset' },
        { text: 'Стиль ответа', callback_data: 'mode' },
      ],
      [
        { text: 'Поиск: auto', callback_data: 'search:auto' },
        { text: 'Поиск: off', callback_data: 'search:off' },
      ],
      [
        { text: 'Публичный доступ: on', callback_data: 'public:on' },
        { text: 'Публичный доступ: off', callback_data: 'public:off' },
      ],
      [
        { text: 'О боте', callback_data: 'about' },
        { text: 'Админ', callback_data: 'admin' },
      ],
    ],
  };
}

async function telegram(method, payload = {}) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(`Telegram ${method} failed: ${response.status} ${JSON.stringify(data)}`);
  }
  return data.result;
}

async function sendMessage(chatId, text, options = {}) {
  return telegram('sendMessage', {
    chat_id: chatId,
    text,
    disable_web_page_preview: true,
    ...options,
  });
}

async function answerCallbackQuery(id, text) {
  return telegram('answerCallbackQuery', { callback_query_id: id, text });
}

async function getFile(fileId) {
  return telegram('getFile', { file_id: fileId });
}

function getFileUrl(filePath) {
  return `https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${filePath}`;
}

function upsertUser(user) {
  if (!user) return;
  state.users[String(user.id)] = {
    id: user.id,
    username: user.username ?? null,
    first_name: user.first_name ?? '',
    last_name: user.last_name ?? null,
    language_code: user.language_code ?? null,
    updated_at: nowIso(),
  };
}

function upsertChat(chat) {
  const existing = state.chats[String(chat.id)] || {};
  state.chats[String(chat.id)] = {
    id: chat.id,
    type: chat.type,
    title: chat.title ?? null,
    username: chat.username ?? null,
    active_reply_mode: existing.active_reply_mode ?? (chat.type === 'private' ? 'always' : 'smart'),
    updated_at: nowIso(),
  };
}

function saveMessageRecord({ chatId, userId, role, messageText, messageKind = 'text', telegramMessageId }) {
  state.messagesHistory.push({
    id: Date.now() + Math.random(),
    chat_id: chatId,
    user_id: userId ?? null,
    role,
    message_text: messageText,
    message_kind: messageKind,
    telegram_message_id: telegramMessageId ?? null,
    created_at: nowIso(),
  });
  state.messagesHistory = state.messagesHistory.slice(-1000);
}

function getRecentHistory(chatId, limit = 12) {
  return state.messagesHistory.filter((item) => item.chat_id === chatId).slice(-limit);
}

function appendMemory(store, key, line, maxLines = 12) {
  const lines = String(store[key] ?? '').split('\n').map((x) => x.trim()).filter(Boolean);
  if (line && lines[lines.length - 1] !== line) lines.push(line);
  store[key] = lines.slice(-maxLines).join('\n').slice(-4000);
}

function getPersonaMode(scopeType, scopeId) {
  return state.personaModes[`${scopeType}:${scopeId}`] ?? null;
}

function setPersonaMode(scopeType, scopeId, style) {
  state.personaModes[`${scopeType}:${scopeId}`] = style;
}

function getSearchPreference(scopeType, scopeId) {
  return state.searchPreferences[`${scopeType}:${scopeId}`] ?? null;
}

function setSearchPreference(scopeType, scopeId, enabled, mode) {
  state.searchPreferences[`${scopeType}:${scopeId}`] = { enabled, mode };
}

function upsertAccessRule(rule_type, target_id, action) {
  if (!state.accessRules.find((item) => item.rule_type === rule_type && item.target_id === target_id && item.action === action)) {
    state.accessRules.push({ rule_type, target_id, action });
  }
}

function deleteAccessRule(rule_type, target_id, action) {
  state.accessRules = state.accessRules.filter((item) => !(item.rule_type === rule_type && item.target_id === target_id && item.action === action));
}

function hasAccessRule(rule_type, target_id, action) {
  return state.accessRules.some((item) => item.rule_type === rule_type && item.target_id === target_id && item.action === action);
}

function listAccessRules(action) {
  return state.accessRules.filter((item) => !action || item.action === action);
}

function isAdmin(userId) {
  return String(userId ?? '') === env.TELEGRAM_ADMIN_ID;
}

function getText(message) {
  return (message.text || message.caption || '').trim();
}

function isCommand(message) {
  return Boolean(message.text && message.text.startsWith('/'));
}

function extractCommand(text) {
  const parts = String(text || '').trim().split(/\s+/);
  const raw = parts.shift() || '';
  return { command: raw.split('@')[0].toLowerCase(), args: parts };
}

function isMentioned(message) {
  const text = getText(message).toLowerCase();
  if (env.TELEGRAM_BOT_USERNAME && text.includes(`@${env.TELEGRAM_BOT_USERNAME.toLowerCase()}`)) return true;
  return text.includes(env.BOT_NAME.toLowerCase());
}

function shouldReplyInChat(message) {
  if (message.chat.type === 'private') return true;
  const chat = state.chats[String(message.chat.id)] || {};
  const replyMode = chat.active_reply_mode || 'smart';
  if (replyMode === 'silent') return false;
  if (isCommand(message)) return true;
  if (message.reply_to_message?.from?.username && env.TELEGRAM_BOT_USERNAME && message.reply_to_message.from.username === env.TELEGRAM_BOT_USERNAME) return true;
  if (isMentioned(message)) return true;
  return replyMode === 'always';
}

function decideAccess(message) {
  const userId = String(message.from?.id ?? '');
  const chatId = String(message.chat.id);
  const mode = state.botSettings.global_access_mode || env.BOT_MODE_DEFAULT;

  if (mode === 'off') return { allowed: false, reason: 'bot_off' };
  if (hasAccessRule('chat', chatId, 'mute')) return { allowed: false, reason: 'chat_muted' };
  if (isAdmin(message.from?.id)) return { allowed: true, reason: 'admin' };
  if (state.botSettings.reply_only_admin) return { allowed: false, reason: 'admin_only_replies' };
  if (mode === 'admin_only') return { allowed: false, reason: 'admin_only_mode' };
  if (mode === 'public' || isTruthy(env.ALLOW_PUBLIC_ACCESS) || state.botSettings.public_responses) return { allowed: true, reason: 'public_mode' };
  if (parseIdList(env.OPTIONAL_ALLOWED_USER_IDS).has(userId) || parseIdList(env.OPTIONAL_ALLOWED_CHAT_IDS).has(chatId)) return { allowed: true, reason: 'env_whitelist' };
  if (hasAccessRule('user', userId, 'allow') || hasAccessRule('chat', chatId, 'allow')) return { allowed: true, reason: 'rule_whitelist' };
  return { allowed: false, reason: 'not_whitelisted' };
}

function decideSearch(text, mode) {
  if (mode === 'off') return { shouldSearch: false, reason: 'search_disabled' };
  if (mode === 'on') return { shouldSearch: true, reason: 'forced_by_user' };
  const normalized = text.toLowerCase();
  const hints = ['сегодня', 'вчера', 'новост', 'цена', 'релиз', 'версия', 'последн', 'актуальн', 'свеж', 'сейчас', '2025', '2026'];
  const shouldSearch = hints.some((hint) => normalized.includes(hint));
  return { shouldSearch, reason: shouldSearch ? 'freshness_detected' : 'context_sufficient' };
}

function buildPrompt({ style, userText, userMemory, chatMemory, searchContext, shouldStayShort }) {
  const styles = {
    concise: 'Отвечай кратко, плотно и по делу.',
    normal: 'Отвечай естественно, уверенно и компактно.',
    technical: 'Отвечай как сильный технический специалист.',
    deep: 'Давай развёрнутый, но собранный ответ.',
    admin: 'Отвечай коротко и операционно.',
  };
  return [
    `Ты ${env.BOT_NAME} - русскоязычный интеллектуальный ассистент Jarvis AI.`,
    `Тебя создал разработчик ${env.CREATOR_NAME}.`,
    'Пиши спокойно, уверенно, без пафоса и без шаблонных фраз нейросетей.',
    'Сначала смысл, потом детали. Не пиши мусор и не выдумывай факты.',
    styles[style] || styles.normal,
    shouldStayShort ? 'Если запрос простой, отвечай коротко.' : 'Если запрос сложный, можно отвечать подробно, но без воды.',
    `Память пользователя:\n${userMemory || 'Пока нет устойчивых наблюдений.'}`,
    `Память чата:\n${chatMemory || 'Специальный контекст чата пока не накоплен.'}`,
    `Свежие данные:\n${searchContext || 'Свежий поиск не выполнялся.'}`,
    `Запрос пользователя:\n${userText}`,
  ].join('\n\n');
}

async function generateReply({ message, userText }) {
  const userId = String(message.from?.id ?? '');
  const chatId = String(message.chat.id);
  const userMemory = state.userMemory[userId] ?? '';
  const chatMemory = state.chatMemory[chatId] ?? '';
  const style = getPersonaMode('user', userId) ?? getPersonaMode('chat', chatId) ?? 'normal';
  const searchPref = getSearchPreference(message.chat.type === 'private' ? 'user' : 'chat', message.chat.type === 'private' ? userId : chatId);
  const searchMode = searchPref ? (searchPref.enabled ? searchPref.mode : 'off') : env.SEARCH_MODE;
  const searchDecision = decideSearch(userText, searchMode);
  const searchContext = searchDecision.shouldSearch
    ? 'Запрос требует свежих данных, но реальный внешний search provider в локальном режиме не подключён. Не имитируй интернет-поиск.'
    : '';

  if (env.AI_PROVIDER === 'disabled' || !env.OPENAI_API_KEY) {
    return 'Локальный AI-провайдер не настроен. Для полноценных ответов добавь в `.dev.vars` `AI_PROVIDER=openai`, `OPENAI_API_KEY` и при необходимости `OPENAI_MODEL`. Команды, память и маршрутизация уже работают.';
  }

  const system = buildPrompt({
    style,
    userText,
    userMemory,
    chatMemory,
    searchContext,
    shouldStayShort: userText.length < 220,
  });

  const history = getRecentHistory(message.chat.id, 10).map((item) => ({ role: item.role, content: String(item.message_text).slice(0, 2000) }));
  const payload = {
    model: env.OPENAI_MODEL,
    messages: [
      { role: 'system', content: system },
      ...history,
      { role: 'user', content: userText.slice(0, 4000) },
    ],
    temperature: 0.35,
  };

  const response = await fetch(`${env.OPENAI_BASE_URL.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`AI provider failed: ${response.status} ${text}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content?.trim() || 'Сейчас не удалось сформировать ответ.';
}

async function extractDocumentText(document) {
  const supported = ['text/', 'application/json', 'application/xml'];
  const fileName = document.file_name || '';
  const mime = document.mime_type || '';
  const supportedByExt = ['.txt', '.md', '.json', '.csv', '.log', '.xml'].some((ext) => fileName.toLowerCase().endsWith(ext));
  const supportedByMime = supported.some((prefix) => mime.startsWith(prefix));
  if (!supportedByExt && !supportedByMime) {
    return { ok: false, reason: 'Этот тип документа пока не поддерживается в локальном режиме. Поддерживаются в основном текстовые файлы.' };
  }
  const file = await getFile(document.file_id);
  const response = await fetch(getFileUrl(file.file_path));
  if (!response.ok) return { ok: false, reason: 'Не удалось скачать документ из Telegram.' };
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > env.DOCUMENT_TEXT_MAX_BYTES) {
    return { ok: false, reason: `Документ слишком большой для текущего лимита (${env.DOCUMENT_TEXT_MAX_BYTES} байт).` };
  }
  return { ok: true, text: new TextDecoder().decode(buffer) };
}

async function handleCommand(message) {
  const { command, args } = extractCommand(message.text || '');
  const userId = String(message.from?.id ?? '');
  const chatId = String(message.chat.id);
  const isBotAdmin = isAdmin(message.from?.id);
  const keyboard = { reply_markup: mainKeyboard() };

  switch (command) {
    case '/start':
      return { handled: true, text: `Я ${env.BOT_NAME}. Локальный runtime в Termux запущен. В личных сообщениях отвечаю всегда, в группах работаю через умное молчание.`, options: keyboard };
    case '/help':
      return { handled: true, text: ['/start','/help','/reset','/mode [concise|normal|technical|deep|admin]','/status','/memory [show|reset_user|reset_chat|reset_all]','/search [auto|on|off|status]','/whoami','/about','/chatmode [smart|always|silent]','','Админ: /admin /public_on /public_off /reply_only_me /allow_user /deny_user /allow_chat /deny_chat /mute_chat /unmute_chat /set_mode /logs /stats'].join('\n'), options: keyboard };
    case '/reset':
      state.messagesHistory = state.messagesHistory.filter((item) => item.chat_id !== message.chat.id);
      delete state.chatMemory[chatId];
      if (message.chat.type === 'private') delete state.userMemory[userId];
      saveState();
      return { handled: true, text: 'История текущего диалога и память сброшены.', options: keyboard };
    case '/mode':
      if (!args[0]) return { handled: true, text: `Текущий стиль ответа: ${getPersonaMode('user', userId) ?? 'normal'}`, options: keyboard };
      if (!['concise','normal','technical','deep','admin'].includes(args[0])) return { handled: true, text: 'Доступно: concise, normal, technical, deep, admin' };
      setPersonaMode('user', userId, args[0]); saveState();
      return { handled: true, text: `Стиль ответа переключён на: ${args[0]}`, options: keyboard };
    case '/chatmode':
      if (!args[0]) return { handled: true, text: `Режим ответов чата: ${state.chats[chatId]?.active_reply_mode ?? 'smart'}`, options: keyboard };
      if (!['smart','always','silent'].includes(args[0])) return { handled: true, text: 'Доступно: smart, always, silent' };
      if (message.chat.type !== 'private' && !isBotAdmin) return { handled: true, text: 'Менять chat mode в группе может только администратор бота.' };
      state.chats[chatId].active_reply_mode = args[0]; saveState();
      return { handled: true, text: `Режим ответов в чате переключён на: ${args[0]}`, options: keyboard };
    case '/status': {
      const searchPref = getSearchPreference(message.chat.type === 'private' ? 'user' : 'chat', message.chat.type === 'private' ? userId : chatId);
      return { handled: true, text: [`Бот: ${env.BOT_NAME}`,`Runtime: termux-local`,`Тип чата: ${message.chat.type}`,`Глобальный режим доступа: ${state.botSettings.global_access_mode}`,`Режим ответов чата: ${state.chats[chatId]?.active_reply_mode ?? (message.chat.type === 'private' ? 'always' : 'smart')}`,`Стиль ответа: ${getPersonaMode('user', userId) ?? 'normal'}`,`Поиск: ${searchPref ? (searchPref.enabled ? searchPref.mode : 'off') : env.SEARCH_MODE}`,`Память: file`,`AI provider: ${env.AI_PROVIDER}`,`Память пользователя: ${state.userMemory[userId] ? 'есть' : 'пусто'}`,`Память чата: ${state.chatMemory[chatId] ? 'есть' : 'пусто'}`].join('\n'), options: keyboard };
    }
    case '/memory': {
      const action = args[0] ?? 'show';
      if (action === 'show') return { handled: true, text: [`Память пользователя:`,`${state.userMemory[userId] ?? 'пока пусто'}`,'',`Память чата:`,`${state.chatMemory[chatId] ?? 'пока пусто'}`].join('\n'), options: keyboard };
      if (action === 'reset_user') delete state.userMemory[userId];
      else if (action === 'reset_chat') { delete state.chatMemory[chatId]; state.messagesHistory = state.messagesHistory.filter((item) => item.chat_id !== message.chat.id); }
      else if (action === 'reset_all') { delete state.userMemory[userId]; delete state.chatMemory[chatId]; state.messagesHistory = state.messagesHistory.filter((item) => item.chat_id !== message.chat.id); }
      else return { handled: true, text: 'Доступно: /memory show, /memory reset_user, /memory reset_chat, /memory reset_all' };
      saveState();
      return { handled: true, text: 'Память обновлена.', options: keyboard };
    }
    case '/search': {
      const scopeType = message.chat.type === 'private' ? 'user' : 'chat';
      const scopeId = message.chat.type === 'private' ? userId : chatId;
      const action = args[0] ?? 'status';
      if (action === 'status') {
        const pref = getSearchPreference(scopeType, scopeId);
        return { handled: true, text: `Поиск для текущего контекста: ${pref ? (pref.enabled ? pref.mode : 'off') : env.SEARCH_MODE}`, options: keyboard };
      }
      if (!['auto','on','off'].includes(action)) return { handled: true, text: 'Доступно: /search auto, /search on, /search off, /search status' };
      setSearchPreference(scopeType, scopeId, action !== 'off', action === 'off' ? 'auto' : action); saveState();
      return { handled: true, text: `Поиск для текущего контекста переключён на: ${action}`, options: keyboard };
    }
    case '/whoami':
      return { handled: true, text: [`Ваш user id: ${userId}`,`Чат id: ${chatId}`,`Username: ${message.from?.username ? `@${message.from.username}` : 'не указан'}`,`Имя: ${message.from?.first_name ?? 'unknown'}`,`Тип чата: ${message.chat.type}`].join('\n'), options: keyboard };
    case '/about':
      return { handled: true, text: `${env.BOT_NAME} - локально запущенный интеллектуальный Telegram-ассистент в Termux. Создатель: ${env.CREATOR_NAME}.`, options: keyboard };
    case '/admin':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      return { handled: true, text: [`Глобальный режим: ${state.botSettings.global_access_mode}`,`Публичные ответы: ${state.botSettings.public_responses}`,`Только админ: ${state.botSettings.reply_only_admin}`,`Whitelist правил: ${listAccessRules('allow').length}`,`Mute правил: ${listAccessRules('mute').length}`,`Пользователей: ${Object.keys(state.users).length}`,`Чатов: ${Object.keys(state.chats).length}`,`Сообщений: ${state.messagesHistory.length}`,`Логов: ${state.logs.length}`].join('\n'), options: keyboard };
    case '/public_on':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      state.botSettings.public_responses = true; state.botSettings.reply_only_admin = false; state.botSettings.global_access_mode = 'public'; saveState();
      return { handled: true, text: 'Публичные ответы включены.', options: keyboard };
    case '/public_off':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      state.botSettings.public_responses = false; state.botSettings.reply_only_admin = false; state.botSettings.global_access_mode = 'selective'; saveState();
      return { handled: true, text: 'Публичные ответы выключены. Активен выборочный режим.', options: keyboard };
    case '/reply_only_me':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      state.botSettings.reply_only_admin = true; saveState();
      return { handled: true, text: 'Теперь бот отвечает только администратору.', options: keyboard };
    case '/allow_user':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи user id: /allow_user <id>' };
      upsertAccessRule('user', args[0], 'allow'); saveState(); return { handled: true, text: `Пользователь ${args[0]} добавлен в whitelist.`, options: keyboard };
    case '/deny_user':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи user id: /deny_user <id>' };
      deleteAccessRule('user', args[0], 'allow'); saveState(); return { handled: true, text: `Пользователь ${args[0]} удалён из whitelist.`, options: keyboard };
    case '/allow_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи chat id: /allow_chat <id>' };
      upsertAccessRule('chat', args[0], 'allow'); saveState(); return { handled: true, text: `Чат ${args[0]} добавлен в whitelist.`, options: keyboard };
    case '/deny_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!args[0]) return { handled: true, text: 'Укажи chat id: /deny_chat <id>' };
      deleteAccessRule('chat', args[0], 'allow'); saveState(); return { handled: true, text: `Чат ${args[0]} удалён из whitelist.`, options: keyboard };
    case '/mute_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      upsertAccessRule('chat', args[0] ?? chatId, 'mute'); saveState(); return { handled: true, text: `Чат ${args[0] ?? chatId} заглушён.`, options: keyboard };
    case '/unmute_chat':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      deleteAccessRule('chat', args[0] ?? chatId, 'mute'); saveState(); return { handled: true, text: `Чат ${args[0] ?? chatId} выведен из mute.`, options: keyboard };
    case '/set_mode':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      if (!['public','selective','admin_only','off','test'].includes(args[0])) return { handled: true, text: 'Доступно: public, selective, admin_only, off, test' };
      state.botSettings.reply_only_admin = false; state.botSettings.global_access_mode = args[0]; saveState(); return { handled: true, text: `Глобальный режим переключён на ${args[0]}.`, options: keyboard };
    case '/logs':
      if (!isBotAdmin) return { handled: true, text: 'Только для администратора.' };
      return { handled: true, text: state.logs.length ? state.logs.slice(-10).map((log) => `[${log.created_at}] ${String(log.level).toUpperCase()} ${log.eventType}: ${log.message}`).join('\n') : 'Логи пока пусты.' };
    case '/stats':
      if (!isBotAdmin) return { handled: true, text: [`users: ${Object.keys(state.users).length}`,`chats: ${Object.keys(state.chats).length}`,`messages: ${state.messagesHistory.length}`,`userMemory: ${Object.keys(state.userMemory).length}`,`chatMemory: ${Object.keys(state.chatMemory).length}`,`logs: ${state.logs.length}`].join('\n') };
    default:
      return { handled: false, text: '' };
  }
}

function callbackToCommand(data, callback) {
  const map = { help: '/help', status: '/status', reset: '/reset', mode: '/mode', about: '/about', admin: '/admin', 'search:auto': '/search auto', 'search:off': '/search off', 'public:on': '/public_on', 'public:off': '/public_off' };
  return map[data] || (callback.message?.chat.type === 'private' ? '/status' : null);
}

async function handleCallback(callback) {
  const mapped = callbackToCommand(callback.data ?? '', callback);
  if (!mapped || !callback.message) return { toast: 'Действие недоступно в этом контексте.' };
  const commandMessage = { ...callback.message, from: callback.from, text: mapped };
  const result = await handleCommand(commandMessage);
  return { toast: result.handled ? 'Готово' : 'Команда не обработана.', messageText: result.text, options: result.options };
}

async function processText(message, textInput, messageKind = 'text') {
  const access = decideAccess(message);
  if (!access.allowed) return;

  if (isCommand(message)) {
    const result = await handleCommand(message);
    if (result.handled) await sendMessage(message.chat.id, result.text, result.options ?? {});
    return;
  }

  if (!shouldReplyInChat(message)) return;

  saveMessageRecord({ chatId: message.chat.id, userId: message.from?.id, role: 'user', messageText: textInput, messageKind, telegramMessageId: message.message_id });
  if (message.from?.id) appendMemory(state.userMemory, String(message.from.id), `Пользователь недавно писал: ${textInput.slice(0, 220)}`);
  appendMemory(state.chatMemory, String(message.chat.id), `${message.from?.first_name ?? message.from?.username ?? 'Пользователь'}: ${textInput.slice(0, 220)}`);
  saveState();

  const reply = await generateReply({ message, userText: textInput });
  await sendMessage(message.chat.id, reply);
  saveMessageRecord({ chatId: message.chat.id, userId: message.from?.id, role: 'assistant', messageText: reply });
  saveState();
}

async function handleMessage(message) {
  upsertUser(message.from);
  upsertChat(message.chat);
  saveState();

  const text = getText(message);
  if (text) return processText(message, text, 'text');

  if (message.document) {
    const extracted = await extractDocumentText(message.document);
    if (!extracted.ok) return sendMessage(message.chat.id, extracted.reason);
    const prompt = [`Пользователь прислал документ${message.document.file_name ? ` ${message.document.file_name}` : ''}.`, message.caption ? `Комментарий пользователя: ${message.caption}` : '', 'Нужно изучить текст документа, кратко понять суть и ответить по делу.', '', extracted.text.slice(0, 12000)].filter(Boolean).join('\n');
    return processText(message, prompt, 'document');
  }

  if (message.voice) {
    return sendMessage(message.chat.id, 'Распознавание голосовых в локальном Termux-режиме пока не подключено. Можно добавить внешний speech-to-text provider.');
  }
}

async function processUpdate(update) {
  try {
    if (update.callback_query) {
      const result = await handleCallback(update.callback_query);
      await answerCallbackQuery(update.callback_query.id, result.toast);
      if (update.callback_query.message && result.messageText) {
        await sendMessage(update.callback_query.message.chat.id, result.messageText, result.options ?? {});
      }
      return;
    }
    const message = update.message ?? update.edited_message;
    if (message) await handleMessage(message);
  } catch (error) {
    logEvent('error', 'update_error', error instanceof Error ? error.message : String(error), { update_id: update.update_id });
  }
}

async function run() {
  logEvent('info', 'startup', 'Jarvis AI local runtime started', { ai_provider: env.AI_PROVIDER, memory_mode: env.MEMORY_MODE });
  while (true) {
    try {
      const updates = await telegram('getUpdates', { offset: state.offset, timeout: 30, allowed_updates: ['message', 'edited_message', 'callback_query', 'my_chat_member'] });
      for (const update of updates) {
        state.offset = update.update_id + 1;
        saveState();
        await processUpdate(update);
      }
    } catch (error) {
      logEvent('error', 'polling_error', error instanceof Error ? error.message : String(error));
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
