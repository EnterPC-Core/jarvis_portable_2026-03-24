# Команды Проекта

Это полный справочник по командам локального Telegram-бота `Enterprise Core`.

## Базовые

- `/start`
- `/help`
- `/commands`
- `/ping`
- `/reset`

## Доступ

- Свободный диалог и runtime-команды доступны только владельцу
- Публичные пользовательские команды доступны всем: `/start`, `/rating`, `/top`, `/topweek`, `/topday`, `/appeal`, `/appeals`

## Режимы ответа

- `/mode jarvis`
- `/mode code`
- `/mode strict`

## Профиль И Рейтинг

- `/rating`
- `/top`
- `/topweek`
- `/topday`
- `/stats`
- `/achievements`

## Апелляции Пользователя

- `/appeal <текст>`
- `/appeals`

## Память И Поиск

- `/remember <факт>`
- `/recall [запрос]`
- `/search <запрос>`
- `/who_said <запрос>`
- `/history [@username|user_id]`
- `/daily [YYYY-MM-DD]`
- `/digest [YYYY-MM-DD]`
- `/export [chat|today|@username|user_id]`
- `/portrait [@username]`
- `/memorychat [запрос]`
- `/memoryuser [@username|user_id]`
- `/memorysummary`

## Владелец / Среда И Runtime

- `/status`
- `/ownerreport`
- `/qualityreport`
- `/selfhealstatus`
- `/selfhealrun <playbook|incident_id> [dry-run|execute]`
- `/selfhealapprove <incident_id>`
- `/selfhealdeny <incident_id>`
- `/resources`
- `/topproc`
- `/disk`
- `/net`
- `/restart` — self-restart отключён; команда сообщает, что runtime остаётся в сети, а реальный перезапуск делается только внешним supervisor
- `/ownerautofix on|off|status`

## Владелец / Git И Логи

- `/gitstatus`
- `/gitlast [количество]`
- `/errors [количество]`
- `/events [restart|access|system|all] [количество]`
- `/routes [количество]`
- `/chatdigest <chat_id> [YYYY-MM-DD]`

## Владелец / Файлы

- `/sdls [/sdcard/путь]`
- `/sdsend /sdcard/путь/к/файлу`
- `/sdsave /sdcard/папка/или/файл`

## Владелец / Изменения Кода

- `/upgrade <что изменить>`

## Модерация

- `/ban <цель> [причина]`
- `/unban <цель>`
- `/mute <цель> [причина]`
- `/unmute <цель>`
- `/kick <цель> [причина]`
- `/tban 1d <цель> [причина]`
- `/tmute 1h <цель> [причина]`

Цель можно указывать:

- reply на сообщение
- `@username`
- `user_id`

## Warn System

- `/warn <цель> [причина]`
- `/dwarn <цель> [причина]`
- `/swarn <цель> [причина]`
- `/warns <цель>`
- `/warnreasons <цель>`
- `/rmwarn <цель>`
- `/resetwarn <цель>`
- `/setwarnlimit <число>`
- `/setwarnmode mute|tmute 1h|ban|tban 1d|kick`
- `/warntime 7d|off`
- `/modlog`

## Welcome

- `/welcome on|off|status`
- `/setwelcome <текст>`
- `/resetwelcome`

Переменные шаблона:

- `{first_name}`
- `{last_name}`
- `{full_name}`
- `{username}`
- `{chat_title}`

## Админ-Апелляции

- `/appeals`
- `/appeal_review <id>`
- `/appeal_approve <id> [решение]`
- `/appeal_reject <id> [решение]`

## Что Есть В Панели

В `Панели владельца` внутри inline UI команды разложены по разделам:

- `Среда и runtime`
- `Git и логи`
- `Память и чаты`
- `Файлы и медиа`
- `Live-данные`
- `Автовосстановление`
- `Модерация`
- `Все команды`

Команды без параметров вынесены в живые экраны панели. Команды с параметрами описаны там как готовые шаблоны использования.

## Автовосстановление

Что уже есть в проекте:

- bounded auto self-healing loop
- cooldown по типу ошибки
- максимум `2` попытки на один incident
- dedup одинаковых auto-report
- post-repair verification до claim-а об успехе
- owner ЛС-отчёт после каждого auto-repair

Безопасные сценарии auto-repair:

- `refresh_runtime_state`
- `recheck_health`
- `recover_failed_live_provider_config`
- `recover_sqlite_lock`
- `reinitialize_missing_runtime_artifact`
- `restart_runtime` сохраняется только как диагностическая escalation-ветка; внутри runtime не исполняется и помечается как blocked, потому что self-restart отключён

Команды owner для self-heal:

- `/selfhealstatus` — список последних self-heal incidents
- `/selfhealrun <playbook|incident_id> [dry-run|execute]` — ручной dry-run или bounded execute
- `/selfhealapprove <incident_id>` — одобрить ожидающий incident
- `/selfhealdeny <incident_id>` — отклонить auto-repair и перевести кейс в manual follow-up
