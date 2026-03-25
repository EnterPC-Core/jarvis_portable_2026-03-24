# Portable Режим И Перенос

## Что это за пакет

Это переносимая сборка локального Telegram-бота, который работает не через удалённый деплой, а прямо на устройстве или в локальной Linux-среде.

Сборка включает:

- локальный bridge к `Codex`
- SQLite-память
- supervisor для живого процесса
- вспомогательные скрипты запуска
- legacy-адаптер для старой базы `Jarvis`

## Что внутри

- [`tg_codex_bridge.py`](./tg_codex_bridge.py) — основной runtime
- [`run_jarvis_supervisor.sh`](./run_jarvis_supervisor.sh) — удержание процесса
- [`run_jarvis_stack.sh`](./run_jarvis_stack.sh) — единый запуск bot + mobile API
- [`start_jarvis_on_termux.sh`](./start_jarvis_on_termux.sh) — фоновый старт в Termux
- [`start_jarvis_on_userland.sh`](./start_jarvis_on_userland.sh) — фоновый старт в UserLAnd
- [`jarvis_memory.db`](./jarvis_memory.db) — текущая память
- [`legacy_jarvis_adapter.py`](./legacy_jarvis_adapter.py) — мост к старой базе
- [`src/`](./src), [`sql/`](./sql), [`package.json`](./package.json) — облачная/worker-часть проекта

## Что нужно на новом устройстве

### Обязательное

- `python3`
- `requests`
- рабочий `codex`
- рабочий `node` подходящей версии
- `BOT_TOKEN`

### Для полного функционала

- `ffmpeg`
- whisper backend
- legacy `jarvis.db`, если нужны рейтинг, достижения, топы и апелляции

## Быстрый сценарий переноса

1. Скопировать проект на новое устройство
2. Создать `.env`
3. Проверить `python3`
4. Проверить `codex`
5. Проверить `node`
6. Подключить `jarvis.db`, если нужен legacy-функционал
7. Запустить supervisor

## Минимальная установка

```bash
python3 -m pip install requests
cp .env.example .env
```

Потом проверить:

```bash
codex --help
node -v
python3 -m py_compile tg_codex_bridge.py
```

## Запуск

```bash
sh run_jarvis_supervisor.sh
```

Для UserLAnd:

```bash
sh start_jarvis_on_userland.sh
```

## Что не входит в “магический автозапуск”

Portable-сборка не делает за тебя:

- установку `node`
- установку `codex`
- установку whisper backend
- настройку системных прав

Это нужно готовить отдельно под целевую среду.

## Ограничения portable-режима

- поведение зависит от локального `node`
- поведение зависит от доступности `codex`
- если среда режет sandbox или процессы, `Enterprise` будет ограничен
- качество live-данных зависит от доступности публичных внешних API

## Что считать актуальной точкой входа

Правильный локальный runtime:

- [`tg_codex_bridge.py`](./tg_codex_bridge.py)

Не нужно путать его со старым legacy launcher или только с Worker-частью.

## Когда portable-сборка считается исправной

Минимальный чек-лист:

- бот стартует без traceback
- heartbeat обновляется
- `/restart` не зацикливается
- `Jarvis` отвечает в личке
- `Enterprise` отвечает в личке и в группах по триггеру
- progress идёт в одном сообщении
- live-запросы на погоду/курс/новости/цену/current-facts не выдумываются
- reply-aware контекст работает для обычных текстовых запросов
- `/digest` и `/ownerreport` доступны как служебные инструменты
- документы тоже разбираются, а текстовые файлы дают excerpt в анализ
- runtime-backups обновлены и лежат в [`data/runtime_backups`](./data/runtime_backups)
