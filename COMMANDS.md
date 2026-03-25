# Команды Проекта

Это полный справочник по командам локального Telegram-бота `Jarvis Portable`.

## Базовые

- `/start`
- `/help`
- `/commands`
- `/ping`
- `/reset`

## Доступ

- `/password <пароль>`

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

## Owner / Runtime

- `/status`
- `/ownerreport`
- `/resources`
- `/topproc`
- `/disk`
- `/net`
- `/restart` — после подъёма bot присылает отдельное подтверждение, что сервер перезапущен
- `/ownerautofix on|off|status`

## Owner / Git И Логи

- `/gitstatus`
- `/gitlast [количество]`
- `/errors [количество]`
- `/events [restart|access|system|all] [количество]`
- `/chatdigest <chat_id> [YYYY-MM-DD]`

## Owner / Файлы

- `/sdls [/sdcard/путь]`
- `/sdsend /sdcard/путь/к/файлу`
- `/sdsave /sdcard/папка/или/файл`

## Owner / Изменения Кода

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

В `Owner Panel` внутри inline UI команды разложены по разделам:

- `Runtime`
- `Git и логи`
- `Память и чаты`
- `Файлы и медиа`
- `Live-data`
- `Модерация`
- `Все команды`

Команды без параметров вынесены в живые экраны панели. Команды с параметрами описаны там как готовые шаблоны использования.
