# Инструкции По Запуску

## Для чего этот файл

Это актуальная инструкция для текущего проекта `Enterprise Core` в локальной среде. Она описывает реальный рабочий режим: здесь постоянно живут два процесса, `tg_codex_bridge.py` и `enterprise_server.py`, каждый под своим supervisor.

## Основные файлы

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной Telegram ↔ Enterprise Core bridge
- [`enterprise_server.py`](./enterprise_server.py) — отдельный локальный сервер Enterprise
- [`enterprise_worker.py`](./enterprise_worker.py) — отдельный worker для конкретной Enterprise-задачи
- [`services/bridge_state_schema.py`](./services/bridge_state_schema.py) — schema/bootstrap `BridgeState`
- [`services/bridge_chat_state.py`](./services/bridge_chat_state.py) — history/facts/summary/events
- [`services/bridge_memory_profiles.py`](./services/bridge_memory_profiles.py) — participant memory, visual signals, active subject
- [`services/bridge_moderation_state.py`](./services/bridge_moderation_state.py) — moderation/warn/welcome/task locks
- [`services/bridge_diagnostics_state.py`](./services/bridge_diagnostics_state.py) — diagnostics, repair journal, self-heal state
- [`services/bridge_task_state.py`](./services/bridge_task_state.py) — persistent task lifecycle and continuity rendering
- [`services/bridge_context_state.py`](./services/bridge_context_state.py) — event/database retrieval helpers extracted from `BridgeState`
- [`services/text_task_service.py`](./services/text_task_service.py) — text-task execution
- [`services/media_task_service.py`](./services/media_task_service.py) — photo/document/voice task flow
- [`services/ask_codex_service.py`](./services/ask_codex_service.py) — codex orchestration wrapper
- [`services/reply_context_service.py`](./services/reply_context_service.py) — reply-context and subject resolver
- [`handlers/update_dispatcher.py`](./handlers/update_dispatcher.py) — Telegram ingress/update dispatch
- [`handlers/owner_panel_sections.py`](./handlers/owner_panel_sections.py) — owner panel sections extracted from renderer
- [`handlers/control_panel_aux.py`](./handlers/control_panel_aux.py) — helper builders extracted from `control_panel_renderer.py`
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — supervisor для постоянного процесса
- [`run_enterprise_supervisor.sh`](./run_enterprise_supervisor.sh) — supervisor для `enterprise_server.py`
- [`restart_jarvis_supervisor.sh`](./restart_jarvis_supervisor.sh) — безопасный single-flight рестарт bridge-supervisor
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый запуск в UserLAnd
- [`start_enterprise_on_userland.sh`](./start_enterprise_on_userland.sh) — фоновый запуск `enterprise_server` в UserLAnd
- [`start_jarvis_on_termux.sh`](./start_jarvis_on_termux.sh) — фоновый запуск в Termux
- [`jarvis_memory.db`](./jarvis_memory.db) — память, история, сервисное состояние

## Слои памяти

В текущей архитектуре память разделена на несколько уровней:

- `chat_history` — короткая рабочая история недавнего диалога
- `chat_events` — архив событий и сообщений для поиска, reply-context и digest
- `memory_facts` — вручную сохранённые факты через `/remember`
- `chat_summaries` — rolling summary по чату
- `user_memory_profiles` — user memory по участникам в рамках конкретного чата
- `relation_memory` — relation memory по парам участников: reply-направления, co-presence, тональные маркеры, краткая summary связки
- `summary_snapshots` — summary memory, то есть накопленные snapshot-сводки по ходу жизни чата
- `self_model_state` — текущее self-state агента: identity, mode, capabilities, limitations, trusted tools, goals, constraints и style invariants
- `autobiographical_memory` — значимые operational события, owner-действия, ошибки, решения, открытые и закрытые задачи
- `reflections` — post-task reflections с observed outcome, uncertainty, lesson и recommended updates
- `skill_memory` — procedural memory/playbooks
- `world_state_registry` и `world_state_snapshots` — актуальное состояние runtime/project/live/sync и его snapshot-история
- `drive_scores` — текущие pressure-сигналы приоритизации

Поверх этого в runtime работает фоновый memory-refresh:

- по таймеру выбираются чаты, где накопилась новая пользовательская активность
- для них обновляется `summary memory` через короткий AI-rollup
- для них же пересобирается `relation memory` из свежих `chat_events`
- для самых активных участников обновляется верхний `user memory` слой
- локальный `participant registry` копит известных участников, статусы админов, join/leave и `member_count`

Это важно: бот теперь строит prompt не только из последних сообщений, а из нескольких memory layers сразу.

Новая часть архитектуры принципиально инженерная:

- self-model хранится как данные, а не как roleplay prompt
- autobiography отделена от chat history и summary memory
- reflection loop пишет уроки после значимых execution flow
- world-state и drive-scores влияют на guardrails и routing refinement
- честность задаётся через observed / inferred / uncertain contract, а не через fake consciousness

## Routing Contract

В текущей версии orchestration стандартизирован:

- `RouteDecision` — определяет, идёт ли запрос в `live_*`, `codex_chat` или `codex_workspace`
- `ContextBundle` — собирает memory/context слои для prompt
- `SelfCheckReport` — финальный self-check после ответа
- `task_runs` / `task_events` — persistent task lifecycle и causal trace для long-running flow
- event/database retrieval больше не привязан к одному большому entrypoint-классу и идёт через отдельный context-state helper layer

Это упрощает отладку, делает `/routes` полезнее и снижает риск случайных route-расхождений между модулями.

Дополнительно в decision-layer зафиксированы lessons из feedback:

- runtime/system вопросы должны либо идти в `codex_workspace`, либо явно сообщать, что метрика не подтверждена
- live-data ответы должны маркировать источник и свежесть
- запросы про текущий чат, участников и локальную динамику должны сначала идти в локальный chat-context, а не в `live_news` или web-search
- `Enterprise` не должен терять инженерный режим из-за слабого роутинга
- self-check не должен пропускать заявления о выполненных действиях без route/tool-подтверждения

### Непереопределяемые правила

- всегда только правда по observed route, tool output, memory state и внешнему источнику
- никакие затычки под отдельный запрос, никакие fake fallback-ответы и никакая подмена архитектурной проблемы одним промптом недопустимы
- если ответ слабый из-за плохого routing/context/tooling, исправляется именно routing/context/tooling
- если данных нет или они не подтверждены, бот обязан это прямо сказать
- нельзя имитировать рабочую live/web/runtime логику там, где она реально не сработала

Отдельно для owner `Enterprise`-маршрута:

- runtime-запросы про `RAM/CPU/disk/processes/network`, наличие monitoring tools и видимость `/proc` теперь идут через прямой local runtime probe
- этот probe читает локальную среду командами вроде `free`, `df`, `ps`, `ip`, `ss`, `apt-cache policy` и проверкой доступности `/proc`
- `Jarvis`-режим при этом не меняется и остаётся обычным prompt-driven слоем

## Минимальные требования

- Linux shell, UserLAnd или Termux
- `python3`
- Python-пакет `requests`
- установленный runtime `Enterprise Core` через локальную команду `codex`
- рабочий `node` для `codex`

В этой сборке supervisor принудительно подхватывает:

- `node v18.20.8` из `~/.nvm/versions/node/v18.20.8/bin`

Это важно, потому что системный `node v12` ломает запуск современного `codex`.

## Настройка окружения

Создай `.env` на основе примера:

```bash
cp .env.example .env
```

Минимально нужны:

```env
BOT_TOKEN=...
OWNER_USER_ID=...
ADMIN_ID=...
OWNER_USERNAME=@...
DB_PATH=/home/userland/projects/bots/jarvis_portable_2026-03-24/jarvis_memory.db
LOCK_PATH=/home/userland/projects/bots/jarvis_portable_2026-03-24/tg_codex_bridge.lock
LEGACY_JARVIS_DB_PATH=/home/userland/projects/bots/jarvis_legacy_data/jarvis.db
```

## Ручной запуск

### Bridge

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
python3 tg_codex_bridge.py
```

Когда это использовать:

- для быстрой отладки
- когда нужен foreground-режим
- когда нужно видеть поведение процесса напрямую

### Enterprise server

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
python3 enterprise_server.py
```

## Нормальный запуск через supervisor

### Bridge

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh run_jarvis_supervisor.sh
```

Supervisor:

- стартует `tg_codex_bridge.py`
- следит за heartbeat
- умеет распознать уже живой healthy bridge и в этом случае не пытается поднимать второй экземпляр
- перезапускает процесс после падения
- выставляет `RUNNING_UNDER_SUPERVISOR=1`
- является единственным допустимым механизмом реального перезапуска; runtime сам себя не `exec`/`exit`-рестартит

### Enterprise server

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh run_enterprise_supervisor.sh
```

Этот supervisor держит `enterprise_server.py` отдельно от bridge и не должен падать вместе с рестартом `tg_codex_bridge.py`.

## Фоновый запуск

### UserLAnd

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh start_jarvis_on_userland.sh
sh start_enterprise_on_userland.sh
```

### Termux

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh start_jarvis_on_termux.sh
```

## Безопасный рестарт bridge

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh restart_jarvis_supervisor.sh
```

Нужно использовать именно этот helper, а не запускать `run_jarvis_supervisor.sh` поверх живого supervisor.

## Остановка

```bash
pkill -f 'python3 tg_codex_bridge.py'
pkill -f 'run_jarvis_supervisor.sh'
pkill -f 'python3 enterprise_server.py'
pkill -f 'run_enterprise_supervisor.sh'
```

## Проверки

### Синтаксис

```bash
python3 -m py_compile tg_codex_bridge.py enterprise_server.py services/*.py handlers/*.py
```

### Обновить runtime-backups для GitHub

```bash
python3 tools/export_runtime_backups.py
```

Или одним шагом:

```bash
sh tools/refresh_repo_state.sh
```

### Жив ли процесс

```bash
ps -ef | grep -E 'tg_codex_bridge.py|run_jarvis_supervisor.sh|enterprise_server.py|run_enterprise_supervisor.sh' | grep -v grep
```

### Логи

- [`tg_codex_bridge.log`](./tg_codex_bridge.log)
- [`supervisor_boot.log`](./supervisor_boot.log)
- [`tg_supervisor.out`](./tg_supervisor.out)
- [`enterprise_server.log`](./enterprise_server.log)
- [`enterprise_supervisor.out`](./enterprise_supervisor.out)

## Что хранится в базе

В `jarvis_memory.db` лежат:

- история диалогов
- режимы чатов
- события чата
- summaries
- memory facts
- настройки предупреждений
- welcome-настройки
- runtime-метаданные бота

Отдельно legacy-база даёт:

- рейтинг
- достижения
- топы
- апелляции

## Что важно для поддержки

- проект рассчитывает на один активный инстанс
- lock-файл: `tg_codex_bridge.lock`
- heartbeat-файл: `tg_codex_bridge.heartbeat`
- server-side jobs и session-memory хранятся отдельно в `enterprise_jobs/` и `enterprise_sessions/`
- `/restart` больше не выполняет self-restart; если нужен реальный перезапуск, перезапускается supervisor
- если `codex` не стартует, первым делом проверяется версия `node`
- перед коммитом желательно обновлять runtime-backups и документацию

## Текущее поведение бота

### В личке

- `Jarvis` отвечает только владельцу
- `Enterprise` для владельца может идти в расширенный локальный режим
- для runtime/system вопросов `Enterprise` использует прямой local probe вместо свободного ответа модели

### В группах

- owner-сценарий разделён по явному имени:
- `Enterprise ...` — инженерный `enterprise`-контур
- `Jarvis ...` — разговорный `jarvis`-контур
- без явного имени owner-сообщение в группе игнорируется
- reply на чужое сообщение теперь попадает в prompt как отдельный контекст вместе с коротким thread history
- вопросы вида `что тут происходит`, `кто в чате`, `изучи этот чат`, `что между ними` теперь должны опираться на локальные `chat_events`, `user memory`, `relation memory`, `participant registry` и chat-dynamics слой

### Progress-статус

Для обычных запросов:

- создаётся одно статусное сообщение
- оно обновляется во время ожидания
- затем оно же превращается в финальный ответ

## Live-routing

Сейчас отдельными маршрутами идут:

- погода
- курсы валют
- крипта
- акции
- новости
- current-fact запросы: “кто сейчас президент”, “кто CEO”, “кто руководит”

Если live-источник не ответил, бот должен честно сообщать об этом, а не фантазировать.
Для live/web lookup теперь допускаются короткие retry-повторы перед окончательным graceful fallback.

## Новые служебные команды

- `/digest [YYYY-MM-DD]` — краткая сводка активности за день по чату
- `/chatdigest <chat_id> [YYYY-MM-DD]` — сводка по конкретной группе из owner-лички
- `/ownerreport` — приватный runtime-отчёт для владельца: CPU/RAM/disk, heartbeat, bot/supervisor process, рестарты за 24ч, backup, хвост ошибок и `supervisor_boot.log`
- `/qualityreport` — приватный diagnostics-срез по `verified/inferred/insufficient`, stale live и degraded routes
- `/selfhealstatus` — приватный статус self-healing incidents/state machine
- `/selfhealrun <playbook|incident_id> [dry-run|execute]` — bounded dry-run/guarded execute для self-healing playbook
- `/selfhealapprove <incident_id>` — owner approval для incident, который ждёт разрешения
- `/selfhealdeny <incident_id>` — перевести incident в manual follow-up / deny
- `/gitstatus` — текущее состояние git-ветки и worktree
- `/gitlast [N]` — последние коммиты
- `/errors [N]` — только реальные ошибки и поломки из `tg_codex_bridge.log`
- `/events [restart|access|system|all] [N]` — служебные события с фильтром по категории
- `/routes [N]` — последние route decisions: persona, intent, live/web/db/reply/workspace layers, source и outcome
- `/memorychat [запрос]` — текущий chat memory слой
- `/memoryuser [@username|user_id]` — текущий user memory слой по участнику
- relation memory отдельной команды пока не имеет; он автоматически подтягивается в prompt для локальных chat/participant запросов

Task truth markers:

- `pending` — задача стартовала, но не закончила execution/diagnostics
- `tool_observed` — tool/job реально завершился и это зафиксировано, но truth claim ещё не усилен diagnostics-слоем
- `verified` / `inferred` / `insufficient` — финальная response truthfulness после `SelfCheckReport` и persisted diagnostics

Отдельно:

- `runtime_health` теперь считается по severe-ошибкам, restart-pressure и heartbeat-kill, а не по каждому штатному `SIGTERM`
- `recent_live_failures` теперь считает только dedicated `live_*` маршруты; web-неопределённость показывается отдельно как `recent_web_failures`
- `/memorysummary` — summary memory snapshots по чату
- `/selfstate` — текущее self-state агента
- `/worldstate` — текущий world-state registry
- `/drives` — pressure-сигналы приоритизации
- `/autobio [запрос]` — autobiographical memory
- `/skills [запрос]` — procedural/skill memory
- `/reflections [N]` — последние reflection entries
- `/restart` — только сервисное уведомление, что self-restart отключён; процесс продолжает жить, а реальный restart делается только supervisor

## Owner Panel

- у владельца в главной inline-панели есть кнопка `Owner Panel`
- внутри вынесены разделы: runtime, git/logs, memory/chat, files/media, live-data, moderation, all commands
- команды без параметров доступны как живые экраны панели
- команды с параметрами лежат в панели как готовые шаблоны и usage-подсказки

## Автоматические owner-отчёты

- daily digest владельцу отправляется автоматически после часа `OWNER_DAILY_DIGEST_HOUR_UTC`
- weekly owner-report отправляется в день `OWNER_WEEKLY_DIGEST_WEEKDAY_UTC`
- оба расписания работают по `UTC`, потому что сам runtime живёт в UTC-среде
