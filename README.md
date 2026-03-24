# Jarvis AI

`Jarvis AI` - production-ready foundation Telegram AI-бота на Cloudflare Workers для адреса `jarvis-ai.enterservicepc.workers.dev`.

Проект собран как реальная база под поддержку и развитие, а не как демо-обёртка:

- Telegram webhook на Cloudflare Worker
- inference через Workers AI
- память, история, режимы и настройки через D1
- KV binding под быстрый кэш и будущие флаги
- умное молчание в группах
- режимы доступа для администратора
- персональная и чат-память
- адаптер поиска с честным fallback
- поддержка документов и голосовых с graceful fallback
- конфигурация через Cloudflare Dashboard Variables and Secrets

Для локального Telegram runtime основной entrypoint здесь не Worker-часть, а `tg_codex_bridge.py`.
Именно он покрывает ручное администрирование, модерацию, warn/welcome-команды и bridge к Codex.
Старая `jarvis.db` нужна только как legacy-источник пользовательской статистики: рейтинг, достижения, топы и апелляции.

Для отдельного mobile-клиента добавлен локальный API entrypoint:

- `jarvis_mobile_api.py`
- `run_jarvis_mobile_api.sh`

Важно:

- токены и секреты не хардкодятся
- проект не требует `wrangler secret put` как обязательный шаг
- секреты можно добавить вручную через Cloudflare Dashboard
- внешний web search в этом проекте не имитируется
- голосовая транскрипция не подделывается
- если провайдер не подключён, бот честно сообщает об ограничении

## Что умеет foundation

### Каналы общения

- личные сообщения: бот отвечает всегда
- группы: отвечает только на команды, reply, упоминание или активный режим чата
- режим `silent`: можно полностью заглушить обычные ответы в конкретном чате
- mobile API: отдельный текстовый chat-клиент поверх того же Jarvis/Codex ядра

## Mobile API

Новый слой нужен для Flutter-клиента `jarvis_mobile`, чтобы не завязывать приложение на Telegram transport.

Поддерживаемые endpoints:

- `GET /health`
- `GET /v1/conversations`
- `GET /v1/conversations/<chat_id>`
- `POST /v1/conversations`
- `GET /v1/conversations/<chat_id>/messages`
- `POST /v1/chat/send`
- `GET /v1/memory/<chat_id>`

Запуск локально:

```bash
sh run_jarvis_mobile_api.sh
```

По умолчанию API слушает:

- `127.0.0.1:8787`

Переопределение через env:

- `JARVIS_MOBILE_API_HOST`
- `JARVIS_MOBILE_API_PORT`
- `JARVIS_MOBILE_DEFAULT_CHAT_ID`

### Интеллектуальная логика

- persona Jarvis AI на русском языке
- стили ответа: `concise`, `normal`, `technical`, `deep`, `admin`
- краткие ответы по умолчанию, подробные по сложным вопросам
- автоматическое решение, нужен ли свежий поиск
- честный fallback, если search provider не подключён

### Память

- краткосрочная история диалога
- долговременная память пользователя
- долговременная память чата
- свёрнутое накопление контекста без бесконечного роста
- команды очистки истории и памяти

### Форматы

- обычный текст
- документы с извлечением текста из поддерживаемых текстовых форматов
- голосовые сообщения с честным сообщением о состоянии транскрипции

## Структура проекта

```text
jarvis-ai-worker/
├── .dev.vars.example
├── README.md
├── package.json
├── sql/
│   └── schema.sql
├── src/
│   ├── admin/
│   │   └── access.ts
│   ├── ai/
│   │   └── generate.ts
│   ├── commands/
│   │   └── handlers.ts
│   ├── logger/
│   │   └── index.ts
│   ├── memory/
│   │   └── store.ts
│   ├── persona/
│   │   └── systemPrompt.ts
│   ├── router/
│   │   └── index.ts
│   ├── search/
│   │   ├── index.ts
│   │   └── provider.ts
│   ├── telegram/
│   │   ├── api.ts
│   │   ├── media.ts
│   │   ├── types.ts
│   │   ├── ui.ts
│   │   ├── updates.ts
│   │   └── webhook.ts
│   ├── utils/
│   │   ├── env.ts
│   │   ├── http.ts
│   │   └── strings.ts
│   ├── index.ts
│   └── types.ts
├── tsconfig.json
└── wrangler.jsonc
```

## Архитектура

### 1. Cloudflare Worker

Основной backend. Обрабатывает:

- `GET /`
- `GET /health`
- `GET /admin/status`
- `POST /webhook/telegram`

### 2. Telegram слой

Модули в `src/telegram/` отвечают за:

- webhook updates
- Telegram Bot API
- callback buttons
- групповую логику ответа
- документы и voice fallback

### 3. AI слой

`src/ai/generate.ts`:

- собирает system prompt
- подмешивает краткосрочную историю
- добавляет user/chat memory
- учитывает результат поиска
- отправляет inference в Workers AI

### 4. Память

`src/memory/store.ts` реализует:

- историю диалога
- память пользователя
- память чата
- настройки и режимы
- whitelist/mute/access rules
- статистику
- поисковые и persona preferences

### 5. Поиск

`src/search/provider.ts` делает две вещи:

- решает, нужен ли свежий поиск
- честно сообщает, что search provider не подключён, если он реально не сконфигурирован

Это не фейковый интернет-поиск. Позже можно подключить внешний провайдер через текущий адаптер.

### 6. Admin/control

`src/admin/access.ts` и `src/commands/handlers.ts` покрывают:

- проверку администратора
- глобальные режимы доступа
- выборочный режим
- mute/whitelist логику
- просмотр логов и статистики
- управление режимом поиска, памяти и ответов по чату

## Переменные окружения

Обязательные значения, которые можно добавить через **Cloudflare Dashboard -> Workers & Pages -> jarvis-ai -> Settings -> Variables and Secrets**.

Рекомендуемый набор:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_ID=6102780373`
- `BOT_PUBLIC_URL=https://jarvis-ai.enterservicepc.workers.dev`
- `BOT_NAME=Jarvis AI`
- `BOT_MODE_DEFAULT=selective`
- `MEMORY_MODE=d1`
- `SEARCH_MODE=auto`
- `ALLOW_PUBLIC_ACCESS=false`
- `WORKERS_AI_MODEL=@cf/meta/llama-3.1-8b-instruct-fast`
- `SYSTEM_BRAND_NAME=Jarvis AI`
- `CREATOR_NAME=Дмитрий`
- `OPTIONAL_ALLOWED_USER_IDS=`
- `OPTIONAL_ALLOWED_CHAT_IDS=`

Дополнительно:

- `TELEGRAM_BOT_USERNAME=`
- `VOICE_MODE=disabled`
- `DOCUMENT_TEXT_MAX_BYTES=262144`

Что лучше держать как Secret в Dashboard:

- `TELEGRAM_BOT_TOKEN`
- при желании `TELEGRAM_ADMIN_ID`
- при желании `BOT_PUBLIC_URL`

Что можно держать как обычные Variables:

- `BOT_NAME`
- `BOT_MODE_DEFAULT`
- `MEMORY_MODE`
- `SEARCH_MODE`
- `ALLOW_PUBLIC_ACCESS`
- `WORKERS_AI_MODEL`
- `SYSTEM_BRAND_NAME`
- `CREATOR_NAME`
- `OPTIONAL_ALLOWED_USER_IDS`
- `OPTIONAL_ALLOWED_CHAT_IDS`
- `VOICE_MODE`
- `DOCUMENT_TEXT_MAX_BYTES`

## D1 и KV

### Создать D1

```bash
wrangler d1 create jarvis_ai_db
```

После этого подставьте `database_id` в `wrangler.jsonc`.

### Создать KV

```bash
wrangler kv namespace create CACHE
```

Подставьте `id` в `wrangler.jsonc`.

### Применить схему

Локально:

```bash
npm install
npm run db:migrate:local
```

Удалённо:

```bash
npm run db:migrate:remote
```

## Локальная разработка

```bash
cd /data/data/com.termux/files/home/jarvis-ai-worker
npm install
cp .dev.vars.example .dev.vars
npm run dev
```

Для локальной разработки заполните `.dev.vars` тестовыми значениями.

## Деплой

```bash
npm install
npm run check
npm run deploy
```

Перед деплоем проверьте:

1. В `wrangler.jsonc` уже указан корректный `database_id` для D1.
2. В `wrangler.jsonc` уже указан корректный `id` для KV.
3. В Cloudflare Dashboard добавлены нужные Variables и Secrets.
4. У Worker включён binding `AI`.

После деплоя Worker будет доступен по адресу:

```text
https://jarvis-ai.enterservicepc.workers.dev
```

## Настройка Telegram webhook

Webhook endpoint у проекта:

```text
https://jarvis-ai.enterservicepc.workers.dev/webhook/telegram
```

Установить webhook можно напрямую через Telegram API в браузере или `curl`:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://jarvis-ai.enterservicepc.workers.dev/webhook/telegram"
```

Проверить состояние webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

Также у Worker есть runtime-статус:

```text
GET https://jarvis-ai.enterservicepc.workers.dev/admin/status
```

## Команды

### Пользовательские

- `/start`
- `/help`
- `/reset`
- `/mode [concise|normal|technical|deep|admin]`
- `/status`
- `/memory [show|reset_user|reset_chat|reset_all]`
- `/search [auto|on|off|status]`
- `/whoami`
- `/about`
- `/chatmode [smart|always|silent]`

### Админские

- `/admin`
- `/public_on`
- `/public_off`
- `/reply_only_me`
- `/allow_user <id>`
- `/deny_user <id>`
- `/allow_chat <id>`
- `/deny_chat <id>`
- `/mute_chat [chat_id]`
- `/unmute_chat [chat_id]`
- `/set_mode <public|selective|admin_only|off|test>`
- `/logs`
- `/stats`

## Как управлять доступом

### Глобальные режимы

- `public` - бот отвечает всем
- `selective` - бот отвечает только whitelisted user/chat
- `admin_only` - отвечает только администратору
- `off` - бот выключен
- `test` - закрытый тестовый режим

### Умное молчание

В группах бот не вмешивается в обычную болтовню. Он отвечает только если:

- это команда
- это reply на его сообщение
- его явно упомянули
- для чата включён режим `always`

## Поиск по интернету

Сейчас реализован честный foundation:

- роутер решает, нужны ли свежие данные
- если реальный search provider не подключён, бот не имитирует поиск
- вместо этого он сообщает, что свежий внешний поиск в текущей конфигурации недоступен

Для реального production search дальше можно подключить внешний провайдер через текущий адаптер `src/search/provider.ts`.

## Безопасность

- не храните токены в репозитории
- не записывайте реальные секреты в `wrangler.jsonc`
- секреты лучше задавать через Cloudflare Dashboard Secrets
- если токен Telegram уже где-то светился, отзовите его через `@BotFather` и создайте новый

## Что можно улучшить дальше

- подключить реальный search provider
- добавить speech-to-text для голосовых
- добавить OCR и PDF/DOCX extraction
- вынести более сильную summarization memory в отдельный background pipeline
- добавить rate limiting и антиспам-слой
- расширить admin status авторизацией и audit trail

## Локальный запуск в Termux

Для этой среды добавлен отдельный runtime без `wrangler`: `local/termux-bot.mjs`. Он работает через Telegram long polling, хранит память в `data/local-state.json` и может использовать OpenAI-совместимый API, если задать `AI_PROVIDER=openai` и `OPENAI_API_KEY` в `.dev.vars`.

Быстрый старт:

```bash
cp .dev.vars.example .dev.vars
npm run local:check
npm run local:bot
```

Важно:

- для реального запуска в Termux нужен локально доступный `TELEGRAM_BOT_TOKEN` в `.dev.vars`
- Cloudflare Dashboard secrets не читаются локальным Node-процессом автоматически
- если `AI_PROVIDER=disabled`, будут работать команды, память, доступ и маршрутизация, но не полноценные AI-ответы
- для реальных AI-ответов в локальном режиме добавь `OPENAI_API_KEY` и при необходимости `OPENAI_MODEL`

## Python Bot Variant

Если нужен максимально простой локальный Telegram-бот по схеме `pyrogram + openai`, используй [local/pyrogram_bot.py](/data/data/com.termux/files/home/jarvis-ai-worker/local/pyrogram_bot.py).

Установка:

```bash
pip install -r local/requirements-pyrogram.txt
```

Запуск:

```bash
export API_ID=123456
export API_HASH=...
export BOT_TOKEN=...
export OPENAI_API_KEY=...
python local/pyrogram_bot.py
```

Или возьми шаблон из `local/.env.pyrogram.example`.
