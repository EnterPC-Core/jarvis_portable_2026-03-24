# Enterprise Core API Required

Документ фиксирует, какой контракт нужен Android-приложению `Enterprise`, что уже подтверждено текущим сервером, а что пока отсутствует и не должно выдумываться.

## Уже подтверждено текущим `enterprise_server.py`

### `GET /health`

Назначение:

- базовый healthcheck сервиса

Формат ответа:

```json
{
  "ok": true,
  "service": "enterprise_server",
  "ts": 1710000000
}
```

### `GET /api/runtime/status`

Назначение:

- статус bridge / supervisor / enterprise server

Подтверждённые поля:

- `supervisor_pid`
- `supervisor_alive`
- `bridge_pid`
- `bridge_alive`
- `enterprise_pid`
- `enterprise_alive`
- `ok`

### `POST /api/jobs`

Назначение:

- создать задачу Enterprise Core

Подтверждённый request:

```json
{
  "chat_id": 123456789,
  "prompt": "Проверь runtime",
  "codex_timeout": 180
}
```

Подтверждённый response:

```json
{
  "ok": true,
  "job_id": "hexid"
}
```

Обязательные поля request:

- `prompt`

Подтверждённо используемые поля request:

- `chat_id`
- `codex_timeout`

### `GET /api/jobs/{job_id}`

Назначение:

- получить snapshot задачи

Подтверждённые поля ответа:

- `id`
- `prompt`
- `started_at`
- `updated_at`
- `done`
- `exit_code`
- `answer`
- `error`
- `events`
- `cwd`
- `output`
- `command`
- `ok`

Использование в приложении:

- polling-based progress UX
- финальный ответ
- error state

### `POST /api/run_sync`

Назначение:

- синхронный вызов job с timeout и итоговым payload

Статус в мобильном приложении:

- не используется как основной runtime route
- может быть использован позже для lightweight diagnostics

### `POST /api/runtime/restart_bridge`

Назначение:

- owner/runtime action

Статус в мобильном приложении:

- не подключён в текущем UI
- потенциальный admin-only TODO

## Требуемые операции приложения

Ниже перечислено, как они покрываются сейчас и что нужно уточнить.

### `createSession()`

Сейчас:

- локально в клиенте

Нужно для полного server contract:

- `POST /api/sessions`

### `listThreads()`

Сейчас:

- локально в клиенте

Нужно для полного server contract:

- `GET /api/threads`

### `getThread()`

Сейчас:

- локально в клиенте

Нужно для полного server contract:

- `GET /api/threads/{thread_id}`

### `renameThread()`

Сейчас:

- локально в клиенте

Нужно для полного server contract:

- `PATCH /api/threads/{thread_id}`

### `deleteThread()`

Сейчас:

- локально в клиенте

Нужно для полного server contract:

- `DELETE /api/threads/{thread_id}`

### `sendMessage()`

Сейчас:

- `POST /api/jobs`

### `streamResponse()`

Сейчас:

- polling `GET /api/jobs/{job_id}`
- progress из `events[]`

Для полноценного streaming protocol желательно:

- `GET /api/jobs/{job_id}/stream` или SSE endpoint
- либо WebSocket channel
- отдельные event types: `progress`, `delta`, `final`, `error`, `done`

### `cancelResponse()`

Сейчас:

- отсутствует

Нужно:

- `POST /api/jobs/{job_id}/cancel`

### `uploadAttachment()`

Сейчас:

- отсутствует

Нужно:

- signed upload flow или multipart endpoint
- size/type policy
- upload token/url
- server attachment id

### `downloadAttachment()`

Сейчас:

- отсутствует

Нужно:

- `GET /api/attachments/{id}` или signed download url

## Ожидаемый streaming protocol

Минимально желателен один из вариантов:

1. SSE
2. WebSocket
3. chunked HTTP stream

События, которые нужны приложению:

- `response.started`
- `response.progress`
- `response.delta`
- `response.completed`
- `response.error`
- `response.cancelled`

## Где сейчас стоят заглушки

- `cancelResponse()`
- `uploadAttachment()`
- `downloadAttachment()`
- server-side thread operations
- widgets / tool calls / transcribe

## Что нужно уточнить для полной интеграции

- существует ли у `Enterprise Core` настоящий thread/session model
- есть ли официальный cancel endpoint
- будет ли stream endpoint кроме polling snapshots
- как должны жить attachments
- будет ли structured/widget output schema
- допустим ли server-side title generation
