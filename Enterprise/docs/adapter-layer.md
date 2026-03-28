# Adapter Layer

## Цель

Изолировать UI от OpenAI-specific runtime и от transport details.

UI должен знать только про adapter operations, а не про сырой HTTP-контракт сервера.

## Структура integration layer

- `src/lib/enterpriseCoreClient.ts`
  - confirmed HTTP operations against `Enterprise Core`
  - local session creation helper
  - polling-based response streaming
- `src/lib/threadRepository.ts`
  - local persistence of thread metadata and messages
- `src/hooks/useEnterpriseWorkspace.ts`
  - orchestration layer between UI and adapter
  - optimistic UI updates
  - message lifecycle

## Какие сервисы созданы

### `enterpriseCoreClient`

Поддерживает:

- `createSession()`
- `healthcheck()`
- `sendMessage()`
- `streamResponse()`
- `cancelResponse()` -> `unsupported`
- `uploadAttachment()` -> `unsupported`
- `downloadAttachment()` -> `unsupported`

### `threadRepository`

Хранит локально:

- список тредов
- active thread id
- thread titles
- message history

## Как UI вызывает adapter

1. `App.tsx` использует `useEnterpriseWorkspace()`
2. hook вызывает `enterpriseCoreClient` и `threadRepository`
3. components получают только готовое state/actions

UI-компоненты не знают:

- endpoint paths
- request payload details
- polling cadence
- localStorage keys

## Как идёт streaming

Текущий `Enterprise Core` не подтверждает SSE/WebSocket/stream endpoint.

Поэтому реализован честный `polling stream`:

1. `sendMessage()` -> `POST /api/jobs`
2. сохраняется `jobId`
3. `streamResponse()` опрашивает `GET /api/jobs/{id}`
4. `events[]` показываются как progress state
5. при `done=true` финальный `answer` попадает в assistant message

Это не masquerade под настоящий token stream. В UI прямо отражено, что это polling.

## Как обрабатываются ошибки

- HTTP errors пробрасываются как error state assistant message
- `snapshot.error` маппится в красный error block
- runtime health errors показываются отдельно в sidebar runtime card

## Как работает cancel

Server-side cancel endpoint не подтверждён.

Поэтому текущая реализация:

- abort локального polling
- помечает assistant message как `cancelled`
- честно пишет пользователю, что server-side cancel отсутствует

## Какие части зависят от неуточнённого API-контракта

- attachments upload/download
- widgets / structured tool payloads
- dictation/transcribe
- server-side thread list/get/rename/delete
- server-side title generation
- server-side cancellation
