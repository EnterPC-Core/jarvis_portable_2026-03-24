# Source Map

## Скачанные официальные источники

Репозитории сохранены в:

- `Enterprise/_references/repos/openai-chatkit-starter-app`
- `Enterprise/_references/repos/openai-chatkit-advanced-samples`
- `Enterprise/_references/repos/openai-apps-sdk-examples`

HTML-копии официальной документации сохранены в:

- `Enterprise/_references/docs/chatkit.html`
- `Enterprise/_references/docs/chatkit-widgets.html`
- `Enterprise/_references/docs/apps-sdk-examples.html`
- `Enterprise/_references/docs/ui-guidelines.html`

## Что стало основой для структуры Enterprise

### `openai-chatkit-starter-app`

Использовано как базовый минимальный shell:

- `chatkit/frontend/src/App.tsx`
- `chatkit/frontend/src/components/ChatKitPanel.tsx`
- `chatkit/frontend/src/index.css`
- `chatkit/frontend/package.json`

Что перенесено наиболее близко:

- Vite + React структура
- крупный chat panel в центре экрана
- минимальный shell без лишних экранов
- composer attachments disabled pattern в базовом starter

### `openai-chatkit-advanced-samples`

Использовано как источник подтверждённых расширенных chat patterns:

- `examples/customer-support/frontend/src/components/Home.tsx`
- `examples/customer-support/frontend/src/components/ChatKitPanel.tsx`
- `examples/metro-map/frontend/src/components/ChatKitPanel.tsx`
- `README.md` feature index

Что взято:

- panel/sidebar layout
- response lifecycle hooks (`onResponseStart` / `onResponseEnd`) как reference для busy-state
- progress update pattern
- side context panel pattern
- attachments/dictation/widgets/tool choice как подтверждённые, но отдельно отмеченные как недоступные для текущего Enterprise Core контракта

### `openai-apps-sdk-examples`

Использовано как source of truth для widget/panel/structured UI references:

- `src/pizzaz/Sidebar.jsx`
- `src/kitchen-sink-lite/kitchen-sink-lite.tsx`
- `README.md`

Что использовано:

- композиция sidebar как отдельной самостоятельной панели
- карточные блоки состояния и structured sections
- подход "не выдумывать host capability, если её нет"

### Official docs

Использованы как подтверждение:

- ChatKit guide
- ChatKit widgets guide
- Apps SDK examples
- Apps SDK UI guidelines

Что ими подтверждено:

- chat shell patterns
- widgets / actions / structured content как официальные паттерны
- panel/sidebar usage как допустимый UI pattern
- правило держать UI-capability связанной с реальным backend contract

## Вынужденные отклонения

1. В официальных ChatKit examples runtime зависит от OpenAI ChatKit backend. В Enterprise это заменено на собственный adapter поверх `Enterprise Core`.
2. В `Enterprise Core` нет server-side thread API, поэтому список сессий хранится локально в клиенте.
3. В `Enterprise Core` нет attachments/widgets/cancel endpoints, поэтому эти части не эмулируются, а честно отключены и задокументированы.
4. Android APK получается через Capacitor wrapper. Это минимальная адаптация web-carкасa в Android без переписывания UI в Kotlin/Compose.
