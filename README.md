# Enterprise Core

Локальный Telegram-бот с двумя режимами поведения:

- `Jarvis` — разговорный и ассистентский слой
- `Enterprise` — режим для реальных проверок среды, кода, файлов и системных задач

Проект работает прямо в текущей Linux/UserLAnd-среде. Отдельный деплой для основной рабочей схемы не нужен. Главная точка входа — [`tg_codex_bridge.py`](./tg_codex_bridge.py), а не Cloudflare Worker-часть.

## Идея проекта

Проект задуман как единая рабочая оболочка `Enterprise Core` в Telegram:

- отвечать в личке и в группах
- уметь переключаться между более мягким режимом `Jarvis` и более исполнительным режимом `Enterprise`
- использовать локальную среду, файлы, логи и базу данных проекта
- не притворяться поиском или системой мониторинга, а реально брать данные из среды или из подключённых live-источников
- хранить память, историю, события, модерацию и служебное состояние в SQLite

Смысл проекта не в “ещё одном чат-боте”, а в переносе агентного режима работы в Telegram-интерфейс без потери практичности.

## Что уже умеет

### Основное

- Telegram long polling через локальный Python bridge
- память диалога и служебное состояние в SQLite
- четыре слоя памяти: `user memory`, `relation memory`, `chat memory`, `summary memory`
- persistent entity-слои: `self-model`, `autobiographical memory`, `reflection loop`, `skill memory`, `world-state registry`, `drive pressures`
- рейтинги, достижения, топы и апелляции через legacy-базу `jarvis.db`
- команды модерации, warn/welcome, история, поиск по событиям
- reply-aware контекст: bot понимает reply на сообщение, медиа и короткий тред вокруг него
- локальный participant registry: bot копит известных участников чата, отдельно знает админов и общее число участников через Bot API
- голосовые сообщения сейчас отключены; поддерживаются текст, фото и документы
- фото и документы идут в реальный анализ, а текстовые файлы дают excerpt в prompt
- режимы `Jarvis` и `Enterprise`
- живой progress-статус в одном сообщении во время долгих задач
- запуск `Enterprise Core` из локальной среды
- у владельца есть project-ops команды: `git status`, последние коммиты, хвост ошибок, digest по конкретной группе
- у владельца разделены `errors` и `events`: реальные поломки отдельно от рестартов и блокировок, у `events` есть фильтр по категориям
- для владельца есть `Owner Panel` в inline UI: все команды проекта разложены по категориям в админ-панели

### Live-данные

Сейчас в bridge есть отдельные live-маршруты без общего “поискового промпта”:

- погода через `Open-Meteo`
- валютные курсы через `Frankfurter`
- крипта через `CoinGecko`
- акции через `Yahoo Finance`
- новости и свежие упоминания через `Google News RSS`
- быстрые current-fact запросы вроде “кто сейчас CEO / президент / глава” через отдельный live-route по внешним источникам

Это нужно для того, чтобы вопросы вида “погода”, “курс доллара”, “цена BTC”, “последние новости”, “кто сейчас президент/CEO” не шли через слабый HTML-поиск.

## Архитектура

### Memory Layers

- `user memory`:
  компактные профили участников по чату, которые собираются из реальных сообщений, форматов общения, стиля и частых тем
- `relation memory`:
  наблюдаемая память о связях между участниками: reply-направления, частые пересечения, тон связки и повторяющиеся общие маркеры
- `chat memory`:
  rolling summary чата, remembered facts и краткий срез самых активных участников
- `summary memory`:
  snapshot-слой кратких сводок, чтобы контекст не схлопывался только в последние несколько сообщений

Поверх этого теперь есть фоновый AI-refresh pass:

- периодически выбираются чаты с новой активностью
- bot обновляет `summary memory` через короткий AI-rollup
- bot пересобирает `relation memory` из реальных `chat_events`, reply-связей и co-presence паттернов
- bot дожимает верхние `user memory` профили для самых активных участников
- user memory и локальный chat-grounding теперь могут опираться не только на summary, но и на `participant registry`, `relation memory` и reply-связи между участниками

### Routing And Contracts

Теперь orchestration держится на стандартизированных контрактах:

- `RouteDecision` — жёсткое решение роутера: `live_*`, `codex_chat`, `codex_workspace`
- `ContextBundle` — единая сборка контекста для prompt layer
- `SelfCheckReport` — post-response self-check перед финальной диагностикой и выдачей

Это нужно, чтобы routing, prompt-building, diagnostics и guardrails жили по одному контракту, а не по разрозненным dict-эвристикам.

Эти слои не заменяют `chat_history`, а дополняют его и подаются в prompt отдельно.

Поверх контрактов зафиксированы lessons из реального feedback и operational logs:

- runtime-запросы вроде `RAM/CPU/disk/uptime` не должны маскироваться под “общий ответ”; им нужен workspace/runtime verification или честное ограничение
- live-data запросы (`погода`, `новости`, `курс`, `current fact`) должны оставлять явный маркер источника и свежести
- запросы про `этот чат`, `тут`, `в чате`, `контекст`, `участников` не должны улетать в live/news; им нужен локальный route через chat memory, relation memory, events и participant registry
- явный вызов `Enterprise` должен удерживать инженерный режим ответа и не сваливаться в общий `Jarvis`-тон
- bot не должен заявлять о выполненных действиях без route/tool-подтверждения

### Persistent Entity Layer

Поверх обычной памяти теперь есть ещё один системный слой непрерывности:

- `self-model`:
  текущее self-state агента как данные в SQLite, а не как временный prompt: identity, active mode, capabilities, limitations, trusted tools, confidence policy, goals, constraints и style invariants
- `autobiographical memory`:
  значимые operational события, owner-действия, runtime-переходы, уроки, открытые и закрытые задачи
- `reflection loop`:
  post-task записи о том, что агент пытался сделать, что реально получилось, где была неопределённость и какой урок зафиксирован
- `skill memory`:
  procedural memory с устойчивыми playbooks для runtime triage, doc sync, chat grounding, live verification и safe restart
- `world-state registry`:
  текущее состояние runtime/project/live/sync/owner priority как обновляемый registry, а не как случайная текстовая сводка
- `drive pressures`:
  функциональные сигналы приоритизации: uncertainty, inconsistency, stale memory, unresolved tasks, doc sync, runtime risk

Это не попытка симулировать сознание. Субъектность здесь выражается через continuity, накопление опыта, self-consistency и честную operational agency.

### Локальный runtime

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной Telegram ↔ Enterprise Core bridge
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — supervisor, который держит один живой процесс бота
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый запуск под UserLAnd
- [`start_jarvis_on_termux.sh`](./start_jarvis_on_termux.sh) — фоновый запуск под Termux

### Данные

- `jarvis_memory.db` — основная SQLite-база
- `jarvis_memory.db-wal`, `jarvis_memory.db-shm` — служебные файлы SQLite
- `../jarvis_legacy_data/jarvis.db` — legacy-источник для рейтинга, достижений, топов и апелляций
- внутри основной базы теперь есть `chat_participants` и `chat_runtime_cache` для локального знания об участниках, админах и `member_count`

## Как это работает сейчас

### Jarvis

- отвечает только владельцу
- более мягкий стиль
- обычные ответы, помощь, объяснения, web/live-вопросы
- если вопрос явно про текущий чат, сначала опирается на локальный chat context, а не на внешний live/web
- красивый progress-статус и замена статуса финальным ответом в том же сообщении

### Enterprise

- более инженерный стиль
- реальная работа по среде, файлам, логам и коду
- для владельца может использовать расширенный локальный режим и прямой вызов `Enterprise Core`
- runtime-вопросы владельца (`RAM/CPU/disk/processes/network`, наличие monitoring tools, доступность `/proc`) теперь сначала идут в прямой local runtime probe, а не в свободный prompt-ответ
- также работает через один обновляемый статусный message flow
- у владельца есть `/ownerreport` для быстрой сводки по runtime и ошибкам: CPU/RAM/disk, heartbeat, bot/supervisor process, рестарты за 24ч, backup и хвосты `tg_codex_bridge.log` / `supervisor_boot.log`
- ежедневный digest и еженедельный owner-report могут отправляться автоматически владельцу по UTC-расписанию
- есть отдельные owner-команды `/gitstatus`, `/gitlast`, `/errors`, `/events`, `/routes`, `/chatdigest`
- есть отдельные owner memory-inspection команды `/memorychat`, `/memoryuser`, `/memorysummary`
- есть owner-introspection по persistent entity слоям: `/selfstate`, `/worldstate`, `/drives`, `/autobio`, `/skills`, `/reflections`

Health-слой:

- `runtime_health` опирается на severe runtime-ошибки, restart-pressure и heartbeat-kill, а не на каждый штатный `SIGTERM`
- `live_source_health` считает dedicated `live_*` маршруты отдельно от web-неопределённости; web-сбои показываются как отдельный внешний сигнал внутри отчётов

## Где смотреть дальше

- [Инструкции по запуску](./PROJECT_RUN_INSTRUCTIONS.md)
- [Portable-пакет и перенос на другое устройство](./PORTABLE_RUN_INSTRUCTIONS.md)
- [Инструкция по боту и панелям](./BOT_UI_GUIDE.md)
- [Полный список команд](./COMMANDS.md)
- [Runtime backups](./data/runtime_backups/README.md)

## Что важно понимать

- основной рабочий режим — локальный, а не cloud/webhook
- деплой не обязателен для текущего сценария
- проект живёт в этой среде и использует локальные процессы
- `Enterprise` не получает “магический root”; он видит только то, что реально доступно текущему UserLAnd/Termux runtime, но runtime-метрики теперь читает напрямую локальными командами и `/proc`, а не через пересказ модели
- документация ниже должна отражать именно это, без старой облачной/worker-схемы и альтернативных launchers

## Жёсткие правила проекта

- всегда говорить только правду по реально выполненному маршруту, инструменту, памяти и внешнему источнику
- не маскировать отсутствие данных, сбой маршрута или слабый контекст “красивым” ответом
- не делать затычки под отдельный запрос, пользователя или кейс
- не подменять архитектурный фикс промптом, ручной эвристикой-ответом или спец-веткой, которая имитирует нормальную работу системы
- если данных не хватает, это должно решаться через routing, context-building, tool/runtime verification или честное ограничение, а не через выдумку
- если поведение сломано, исправлять причину в архитектуре маршрута или источника данных, а не рисовать правдоподобный ответ поверх поломки

## Правило синхронизации проекта

Чтобы не было расхождения между рабочей средой и GitHub:

- код меняется локально
- затем обновляются runtime-backups
- затем обновляется документация, если поменялось поведение
- затем изменения коммитятся и пушатся

Быстрый служебный шаг:

```bash
sh tools/refresh_repo_state.sh
```

## Ближайший roadmap

- усилить live-routing для свежих данных и current-fact запросов дальше
- добавить более строгий router для ролей, должностей и “последний / current / latest”
- улучшить обработку file/image context сверх reply-aware слоя
- расширить диагностику отказов инструментов и live-источников
- довести все служебные скрипты и runtime-сценарии до полного соответствия GitHub-репозиторию
