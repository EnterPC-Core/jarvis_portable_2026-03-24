# Enterprise Core

Локальный Telegram-бот с двумя режимами поведения:

- `Jarvis` — разговорный и ассистентский слой
- `Enterprise` — режим для реальных проверок среды, кода, файлов и системных задач

Проект работает прямо в текущей Linux/UserLAnd-среде. Отдельный деплой для основной рабочей схемы не нужен. Главная точка входа — [`tg_codex_bridge.py`](./tg_codex_bridge.py), а не Cloudflare Worker-часть.

## Статус Проекта

- текущий режим: локальный runtime в `UserLAnd` / `Termux`
- основной entrypoint: [`tg_codex_bridge.py`](./tg_codex_bridge.py)
- поддерживаемый способ удержания процесса: [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh)
- модель доступа по умолчанию: бот отвечает только владельцу `OWNER_USER_ID`
- storage: локальная SQLite-память + legacy SQLite для рейтингов и апелляций

Это не библиотека и не SaaS-сервис. Это рабочий локальный Telegram runtime со своей памятью, маршрутизацией, live-проверками и owner-ops сценариями.

## Быстрый Старт

### 1. Минимальные зависимости

- `python3`
- `node`
- установленный `codex`
- Python-пакет `requests`

Установка минимального Python-слоя:

```bash
python3 -m pip install -r requirements.txt
```

### 2. Настрой окружение

```bash
cp .env.example .env
```

Минимально нужно заполнить:

```env
BOT_TOKEN=...
OWNER_USER_ID=...
ADMIN_ID=...
OWNER_USERNAME=@...
```

### 3. Проверка синтаксиса

```bash
python3 -m py_compile tg_codex_bridge.py
python3 tools/smoke_check.py
python3 tools/behavioral_check.py
```

### 4. Запуск

Нормальный рабочий запуск:

```bash
sh run_jarvis_supervisor.sh
```

Фоновый запуск для UserLAnd:

```bash
sh start_jarvis_on_userland.sh
```

Фоновый запуск для Termux:

```bash
sh start_jarvis_on_termux.sh
```

## Структура Репозитория

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — runtime entrypoint и coordinator: Telegram polling, orchestration, интеграция router/pipeline/services
- [`handlers/`](./handlers) — Telegram message handlers, command dispatch и command parsers
- [`models/`](./models) — типизированные контракты: `RouteDecision`, `ContextBundle`, `SelfCheckReport`, `AttachmentBundle`, live records
- [`router/`](./router) — deterministic routing policy и request classification без Telegram I/O
- [`pipeline/`](./pipeline) — diagnostics/self-check enrichment и traceable response pipeline
- [`owner/`](./owner) — owner/admin registry и command handlers для owner-ops
- [`services/`](./services) — runtime services, memory services, live providers, discussion context, storage/repair helpers и compatibility layer для controlled migration
- [`presentation/`](./presentation) — presentation contracts и user-facing answer models
- [`utils/`](./utils) — текстовые, файловые, runtime и reporting helper-функции
- [`prompts/`](./prompts) — короткие runtime profiles и prompt loader; prompt layer сведён к `jarvis` и `enterprise`
- [`tools/`](./tools) — smoke/behavioral checks, runtime-backup export, repo refresh
- [`data/runtime_backups/`](./data/runtime_backups) — schema и summary snapshot'ы для синхронизации runtime и GitHub
- [`legacy_jarvis_adapter.py`](./legacy_jarvis_adapter.py) — мост к legacy `jarvis.db`

## Модель Доступа

По умолчанию bridge работает в owner-only режиме:

- владелец с `OWNER_USER_ID` имеет доступ к основному conversational и enterprise flow
- остальные участники не получают полный доступ к runtime-возможностям
- в группах поведение зависит от триггеров, reply-контекста, moderation-политики и текущих guardrails

Если бот "молчит", сначала проверь:

- что сообщение отправлено владельцем
- что есть триггер `Jarvis` / `Enterprise` или корректный reply/mention
- что живы `run_jarvis_supervisor.sh` и `tg_codex_bridge.py`
- что `BOT_TOKEN` и локальный `codex` реально доступны в этой среде

## Что Проверять Перед Пушем

Базовый локальный чек:

```bash
python3 -m py_compile tg_codex_bridge.py
python3 tools/smoke_check.py
python3 tools/behavioral_check.py
sh tools/refresh_repo_state.sh
```

Это минимальный набор, который стоит прогонять до коммита, чтобы GitHub не расходился с локальным runtime.

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
- для владельца есть `Панель владельца` в inline UI: все команды проекта разложены по категориям в админ-панели и описаны по-русски
- есть bounded auto self-healing loop: detect -> classify -> safe repair -> verify -> Telegram report владельцу

### Live-данные

Сейчас в bridge есть отдельные live-маршруты без общего “поискового промпта”:

- погода через `Open-Meteo`
- валютные курсы через `Frankfurter`
- крипта через `CoinGecko`
- акции через `Yahoo Finance`
- новости и свежие упоминания через `Google News RSS`
- быстрые current-fact запросы вроде “кто сейчас CEO / президент / глава” через отдельный live-route по внешним источникам

### Автовосстановление

Сейчас в проекте уже есть ограниченный safe self-healing слой:

- используются существующие `failure_detectors`, `repair_playbooks`, `runtime diagnostics` и owner-команды
- auto-loop запускается внутри runtime по интервалу и на runtime-error hooks
- автоматически выполняются только allowlisted сценарии
- после каждого repair идёт обязательная before/after verification
- владельцу уходит Telegram ЛС-отчёт по результату
- есть защита от циклов:
  - cooldown
  - max retries = 2
  - dedup одинаковых incident/report
  - stop-after-failure

Текущие safe auto-repair сценарии:

- refresh runtime/world-state
- bounded health recheck
- recovery degraded live providers
- recovery temporary SQLite lock
- reinitialize missing runtime heartbeat artifact
- auto-restart как escalation path только с post-restart verification на новом startup

Что сознательно не чинится автоматически:

- destructive SQLite/schema repair
- config drift
- dependency install/upgrade
- environment rewrite
- любые shell-действия вне allowlist

## Архитектура

### Three Contours

Теперь проект явнее разделён на три контура:

- `assistant / jarvis`:
  ответы пользователю, chat-facing логика, Telegram presentation
- `enterprise / runtime`:
  owner ops, runtime diagnostics, файлы, код, среда, self-heal
- `moderation`:
  anti-abuse, sanctions, warns, appeals, modlog, group guardrails

Moderation enforcement не смешивается с search pipeline и prompt synthesis.

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

### Owner / Admin UI

Текущая inline-панель владельца разбита на русские разделы:

- `Среда и runtime`
- `Git и логи`
- `Память и чаты`
- `Файлы и медиа`
- `Live-данные`
- `Автовосстановление`
- `Модерация`
- `Все команды`

Внутри `Автовосстановления` есть:

- список последних инцидентов
- экран инцидента с причинами и evidence
- очередь согласования
- inline-кнопки `Одобрить` / `Отклонить`

### Moderation Layer

Поверх legacy moderation-сервисов теперь есть отдельный слой `moderation/`:

- `moderation/moderation_models.py` — строгие moderation contracts
- `moderation/anti_abuse.py` — adapter над `AntiAbuseService`
- `moderation/sanctions.py` — adapter над `SanctionsService`
- `moderation/warnings.py` — warn adapter над bridge state
- `moderation/appeals.py` — adapter над `AppealsService`
- `moderation/modlog.py` — summary/reader для `moderation_journal`
- `moderation/moderation_orchestrator.py` — compatibility facade для auto-moderation path
- `moderation/policy.py` — короткие формальные moderator-facing notices

Это не ломает существующие `/ban`, `/mute`, `/kick`, warn flow, `/modlog`, `/appeal` и owner/admin review path, а даёт отдельную архитектурную границу для дальнейшего выноса логики из bridge.

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

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной Telegram ↔ Enterprise Core coordinator
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — supervisor, который держит один живой процесс бота
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый запуск под UserLAnd
- [`start_jarvis_on_termux.sh`](./start_jarvis_on_termux.sh) — фоновый запуск под Termux

Критичные runtime-domain модули:

- [`models/contracts.py`](./models/contracts.py) — единые data contracts для route/context/self-check/live
- [`router/request_router.py`](./router/request_router.py) — строгий router и request-kind classification
- [`pipeline/diagnostics.py`](./pipeline/diagnostics.py) — response contract enrichment и persisted diagnostics shaping
- [`pipeline/context_pipeline.py`](./pipeline/context_pipeline.py) — context-bundle orchestration и discussion-context assembly
- [`owner/admin_registry.py`](./owner/admin_registry.py) — owner/admin command catalog
- [`owner/handlers.py`](./owner/handlers.py) — owner/admin command handlers и owner-report rendering
- [`handlers/telegram_handlers.py`](./handlers/telegram_handlers.py) — text/photo/document/voice Telegram handlers
- [`handlers/command_dispatch.py`](./handlers/command_dispatch.py) — command dispatcher без смешивания с polling/runtime кодом
- [`handlers/ui_handlers.py`](./handlers/ui_handlers.py) — inline UI, callback flow и pending-input сценарии
- [`handlers/control_panel_renderer.py`](./handlers/control_panel_renderer.py) — owner/public control-panel rendering без UI transport-логики
- [`services/live_gateway.py`](./services/live_gateway.py) — live provider gateway и normalized live records
- [`services/runtime_service.py`](./services/runtime_service.py) — world-state refresh, drive recompute и runtime health rollups
- [`services/memory_service.py`](./services/memory_service.py) — AI summary refresh для chat/user memory
- [`services/bridge_runtime_text.py`](./services/bridge_runtime_text.py) — stateless runtime text/access/help/group-trigger helper layer для bridge wrappers
- [`services/bridge_file_helpers.py`](./services/bridge_file_helpers.py) — stateless file/sdcard/media helper layer для bridge wrappers
- [`services/bridge_ops_helpers.py`](./services/bridge_ops_helpers.py) — stateless git/log/runtime ops helper layer для bridge wrappers
- [`services/failure_detectors.py`](./services/failure_detectors.py) — incident/failure detection
- [`services/repair_playbooks.py`](./services/repair_playbooks.py) — repair playbook registry без ложных auto-fix claims

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
- у владельца есть `/qualityreport` для отдельного среза по `verified/inferred/insufficient`, degraded routes, stale live и memory/tool usage
- у владельца есть `/selfhealstatus` и `/selfhealrun` для bounded self-healing: status/history и dry-run/guarded playbook execution
- у владельца есть `/selfhealapprove` и `/selfhealdeny` для approval gate по queued self-heal incidents
- ежедневный digest и еженедельный owner-report могут отправляться автоматически владельцу по UTC-расписанию
- есть отдельные owner-команды `/gitstatus`, `/gitlast`, `/errors`, `/events`, `/routes`, `/chatdigest`
- есть отдельные owner memory-inspection команды `/memorychat`, `/memoryuser`, `/memorysummary`
- есть owner-introspection по persistent entity слоям: `/selfstate`, `/worldstate`, `/drives`, `/autobio`, `/skills`, `/reflections`

Health-слой:

- `runtime_health` опирается на severe runtime-ошибки, restart-pressure и heartbeat-kill, а не на каждый штатный `SIGTERM`
- `live_source_health` считает dedicated `live_*` маршруты отдельно от web-неопределённости; web-сбои показываются как отдельный внешний сигнал внутри отчётов

## Prompt Architecture

Теперь prompt layer упрощён и держит только два коротких personality/profile режима без бизнес-логики проекта.

- [`prompts/jarvis.py`](./prompts/jarvis.py) — короткий chat-facing профиль Jarvis
- [`prompts/enterprise.py`](./prompts/enterprise.py) — короткий owner/system-facing профиль Enterprise
- [`prompts/runtime_profiles.py`](./prompts/runtime_profiles.py) — реестр профилей и legacy aliases
- [`prompts/profile_loader.py`](./prompts/profile_loader.py) — loader/resolver профиля
- [`prompts/builders.py`](./prompts/builders.py) — сборка prompt из выбранного профиля и контекстных блоков
- [`prompts/task_prompts.py`](./prompts/task_prompts.py) — отдельные минимальные service prompts для voice/grammar/memory/upgrade, вынесенные из bridge

Что вынесено из prompt layer в код:

- routing и provider selection
- search / follow-up rewrite / freshness guard
- self-check и final answer gating
- moderation enforcement
- Telegram presentation, chunking и rendering

Что сокращено или убрано:

- giant base system prompt в `tg_codex_bridge.py`
- service prompt blobs и локальные prompt wrappers в `tg_codex_bridge.py`
- legacy режимы `code` и `strict` как отдельные runtime profiles
- prompt sections `Intent`, `Response shape`, `Route summary`, `Self-check and guardrails`

Сейчас в runtime есть только 2 профиля:

- `jarvis`
- `enterprise`

Legacy значения режима (`chat`, `code`, `strict`) нормализуются в `jarvis` ради совместимости, но отдельными prompt-профилями больше не считаются.

Смысл профилей:

- `jarvis` — личный ассистент Дмитрия для обычного чата; не рассказывает внутреннюю архитектуру и не превращает ответ в служебный лог
- `enterprise` — инженерный режим Дмитрия для среды, кода, рантайма, диагностики и операционных задач

## Где смотреть дальше

- [Инструкции по запуску](./PROJECT_RUN_INSTRUCTIONS.md)
- [Portable-пакет и перенос на другое устройство](./PORTABLE_RUN_INSTRUCTIONS.md)
- [Инструкция по боту и панелям](./BOT_UI_GUIDE.md)
- [Полный список команд](./COMMANDS.md)
- [Architecture blueprint](./ARCHITECTURE_BLUEPRINT.md)
- [Runtime backups](./data/runtime_backups/README.md)

## Что важно понимать

- основной рабочий режим — локальный, а не cloud/webhook
- деплой не обязателен для текущего сценария
- проект живёт в этой среде и использует локальные процессы
- `Enterprise` не получает “магический root”; он видит только то, что реально доступно текущему UserLAnd/Termux runtime, но runtime-метрики теперь читает напрямую локальными командами и `/proc`, а не через пересказ модели
- документация ниже должна отражать именно это, без старой облачной/worker-схемы и альтернативных launchers

## Ограничения И Операционные Замечания

- live-источники зависят от сети и внешних API; при сбое бот должен честно это показывать
- `Enterprise` не равен unrestricted shell; доступ ограничен текущим runtime и guardrails
- локальные проектные/meta-запросы не должны уходить во внешний web/live-маршрут
- reply-aware сценарии чувствительны к качеству контекста: если Telegram не дал нужный `reply_to_message`, ответ будет уже по усечённому основанию
- long-running ответы опираются на supervisor, heartbeat и состояние локального `codex`

## Для GitHub

Если репозиторий используется как публичная точка входа, в нём уже есть главное:

- актуальный локальный entrypoint
- инструкции по запуску
- список команд
- runtime backup snapshot'ы
- smoke/behavioral checks

Чего здесь намеренно нет:

- cloud deployment как основной сценарий
- fake demo-mode без реального runtime
- обещаний "автоматически работает везде" без проверки `node`, `codex`, `BOT_TOKEN` и локальной среды

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
