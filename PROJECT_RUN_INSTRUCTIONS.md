# Инструкции По Запуску

## Для чего этот файл

Это актуальная инструкция для текущего проекта в локальной среде. Она описывает реальный рабочий режим: бот запускается здесь, в этой Linux/UserLAnd-среде, через `tg_codex_bridge.py` и supervisor.

## Основные файлы

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной Telegram ↔ Codex bridge
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — supervisor для постоянного процесса
- [`run_jarvis_stack.sh`](./run_jarvis_stack.sh) — единый запуск supervisor + mobile API
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый запуск в UserLAnd
- [`start_jarvis_on_termux.sh`](./start_jarvis_on_termux.sh) — фоновый запуск в Termux
- [`jarvis_memory.db`](./jarvis_memory.db) — память, история, сервисное состояние

## Минимальные требования

- Linux shell, UserLAnd или Termux
- `python3`
- Python-пакет `requests`
- установленный `Codex CLI` как команда `codex`
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
ALLOWED_USER_ID=...
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

## Запуск полного локального стека

Если нужен сразу bot + mobile API:

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24
sh run_jarvis_stack.sh
```

Этот скрипт:

- запускает `run_jarvis_supervisor.sh`
- запускает `run_jarvis_mobile_api.sh`
- завершает оба процесса, если один из них упал

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

- `Jarvis` отвечает всегда
- `Enterprise` для владельца может идти в расширенный локальный режим

### В группах

- ответы только по trigger/reply/упоминанию
- `Enterprise` тоже может работать, если маршрут явно вызван
- reply на чужое сообщение теперь попадает в prompt как отдельный контекст вместе с коротким thread history

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

## Новые служебные команды

- `/digest [YYYY-MM-DD]` — краткая сводка активности за день по чату
- `/chatdigest <chat_id> [YYYY-MM-DD]` — сводка по конкретной группе из owner-лички
- `/ownerreport` — приватный runtime-отчёт для владельца: ресурсы, backup, хвост ошибок
- `/gitstatus` — текущее состояние git-ветки и worktree
- `/gitlast [N]` — последние коммиты
- `/errors [N]` — только реальные ошибки и поломки из `tg_codex_bridge.log`
- `/events [restart|access|system|all] [N]` — служебные события с фильтром по категории
- `/routes [N]` — последние route decisions: persona, intent, live/web/db/reply/workspace layers, source и outcome
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
