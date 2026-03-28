# OpenAI Dependencies Audit

## Найденные OpenAI-specific зависимости в reference-базе

### `openai-chatkit-starter-app`

- `OPENAI_API_KEY` в backend env/examples
- `@openai/chatkit-react`
- `@openai/chatkit`
- `ChatKitServer`
- `domainKey`

### `openai-chatkit-advanced-samples`

- `OPENAI_API_KEY`
- `@openai/chatkit-react`
- `@openai/chatkit`
- ChatKit Python backend / ChatKit server abstractions
- managed thread titles, dictation, attachments, widgets через ChatKit contracts

### `openai-apps-sdk-examples`

- `@openai/apps-sdk-ui`
- `window.openai`
- MCP Apps SDK examples and host widget APIs

## Где они используются

Reference-only usage:

- `_references/repos/openai-chatkit-starter-app/...`
- `_references/repos/openai-chatkit-advanced-samples/...`
- `_references/repos/openai-apps-sdk-examples/...`

## Что заменено в активном Enterprise приложении

В активном коде `Enterprise`:

- удалена зависимость от `@openai/chatkit-react`
- удалена зависимость от `@openai/chatkit`
- удалена зависимость от `OPENAI_API_KEY`
- нет `domainKey`
- нет OpenAI backend session/token exchange

Заменено на:

- собственный `enterpriseCoreClient`
- polling `POST /api/jobs` + `GET /api/jobs/{id}`
- `GET /health`
- `GET /api/runtime/status`

## Что удалено

Из runtime app tree полностью исключены:

- ChatKit runtime packages
- Apps SDK runtime packages
- OpenAI-specific branding
- OpenAI backend credentials

## Что ещё требует отвязки

Активное приложение уже не тянет OpenAI runtime dependencies. Оставшиеся OpenAI-specific следы находятся только в `_references/` и используются исключительно для аудита/каркаса.

## Какие места адаптированы под Enterprise Core

- chat shell: перенесён по structure/layout, но backend transport полностью заменён
- progress UX: вместо ChatKit stream events используется polling snapshot `events`
- thread metadata: вместо server-managed thread model используется локальное client-side persistence
- attachments/widgets/dictation: отключены, пока не появится подтверждённый Enterprise Core API
