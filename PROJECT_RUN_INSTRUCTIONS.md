# Инструкции По Запуску

## Для чего этот файл

Это актуальная инструкция для текущего проекта `Enterprise Core` в локальной среде. Она описывает реальный рабочий режим: бот запускается здесь, в этой Linux/UserLAnd-среде, через `tg_codex_bridge.py` и supervisor.

## Основные файлы

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной Telegram ↔ Enterprise Core bridge
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — supervisor для постоянного процесса
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый запуск в UserLAnd
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

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
python3 tg_codex_bridge.py
```

Когда это использовать:

- для быстрой отладки
- когда нужен foreground-режим
- когда нужно видеть поведение процесса напрямую

## Нормальный запуск через supervisor

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh run_jarvis_supervisor.sh
```

Supervisor:

- стартует `tg_codex_bridge.py`
- следит за heartbeat
- перезапускает процесс после падения
- выставляет `RUNNING_UNDER_SUPERVISOR=1`

## Фоновый запуск

### UserLAnd

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh start_jarvis_on_userland.sh
```

### Termux

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh start_jarvis_on_termux.sh
```

## Остановка

```bash
pkill -f 'python3 tg_codex_bridge.py'
pkill -f 'run_jarvis_supervisor.sh'
```

## Проверки

### Синтаксис

```bash
python3 -m py_compile tg_codex_bridge.py
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
ps -ef | grep -E 'tg_codex_bridge.py|run_jarvis_supervisor.sh' | grep -v grep
```

### Логи

- [`tg_codex_bridge.log`](./tg_codex_bridge.log)
- [`supervisor_boot.log`](./supervisor_boot.log)
- [`tg_supervisor.out`](./tg_supervisor.out)

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
- если после `/restart` бот зацикливается, надо проверять `last_update_id` и `bot_meta`
- если `codex` не стартует, первым делом проверяется версия `node`
- перед коммитом желательно обновлять runtime-backups и документацию

## Текущее поведение бота

### В личке

- `Jarvis` отвечает только владельцу
- `Enterprise` для владельца может идти в расширенный локальный режим
- для runtime/system вопросов `Enterprise` использует прямой local probe вместо свободного ответа модели

### В группах

- ответы только на обращения владельца через trigger/reply/упоминание
- `Enterprise` тоже может работать, если маршрут явно вызван
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
- `/restart` — одно сообщение: сначала статус перезапуска, после нового старта это же сообщение обновляется в подтверждение

## Owner Panel

- у владельца в главной inline-панели есть кнопка `Owner Panel`
- внутри вынесены разделы: runtime, git/logs, memory/chat, files/media, live-data, moderation, all commands
- команды без параметров доступны как живые экраны панели
- команды с параметрами лежат в панели как готовые шаблоны и usage-подсказки

## Автоматические owner-отчёты

- daily digest владельцу отправляется автоматически после часа `OWNER_DAILY_DIGEST_HOUR_UTC`
- weekly owner-report отправляется в день `OWNER_WEEKLY_DIGEST_WEEKDAY_UTC`
- оба расписания работают по `UTC`, потому что сам runtime живёт в UTC-среде
