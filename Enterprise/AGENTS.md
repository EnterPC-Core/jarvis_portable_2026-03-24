# AGENTS

## Цель проекта

Сделать Android-приложение `Enterprise`, которое:

- живёт только в `projects/bots/jarvis_portable_2026-03-24/Enterprise`
- повторяет только подтверждённые официальными открытыми исходниками UI и behavior patterns
- использует только `Enterprise Core` как runtime backend для ИИ
- собирает APK только через GitLab CI/CD

## Жёсткий рабочий путь

Единственная разрешённая зона изменений:

`/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise`

## Прямой запрет

- не редактировать соседние файлы
- не создавать новый `Enterprise` вне этой папки
- не переносить файлы наружу
- не использовать соседние проекты как рабочую область

Чтение соседних файлов для анализа допустимо. Запись наружу запрещена.

## Официальные источники

- `https://github.com/openai/openai-chatkit-starter-app`
- `https://github.com/openai/openai-chatkit-advanced-samples`
- `https://github.com/openai/openai-apps-sdk-examples`
- `https://developers.openai.com/api/docs/guides/chatkit/`
- `https://developers.openai.com/api/docs/guides/chatkit-widgets/`
- `https://developers.openai.com/apps-sdk/build/examples/`
- `https://developers.openai.com/apps-sdk/concepts/ui-guidelines/`

Локальные копии лежат в `_references/`.

## Правило "если нет в исходниках — TODO"

Если фича, endpoint или pattern не подтверждены официальной базой:

- не выдумывать реализацию
- оставить `TODO`
- описать разрыв в документации

## Правило "не фантазировать"

- не улучшать UI от себя
- не придумывать новые экраны
- не добавлять неподтверждённые widgets/tools/backend methods
- не оставлять OpenAI runtime backend

## Backend rule

Только `Enterprise Core` как runtime backend.

OpenAI-пакеты и OpenAI backend разрешены только как reference внутри `_references/`, но не в активном runtime коде приложения.

## Adapter layer

- UI не ходит напрямую в OpenAI SDK
- UI работает через isolated adapter layer
- adapter честно отражает текущий контракт `Enterprise Core`
- неподтверждённые операции возвращают `TODO/unsupported`, а не fake endpoint

## Команды локальной работы

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js install
```

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run typecheck
```

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run build
```

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run android:sync
```

## Правила проверок

- сначала `typecheck`
- потом `vite build`
- потом `cap sync android`
- тяжёлую APK-сборку считать GitLab-задачей, а не обязательным локальным шагом

## Правила коммитов

Делать этапные коммиты:

- `chore: initialize Enterprise workspace`
- `docs: add source map and dependency audit`
- `feat: scaffold Enterprise app shell and adapter`
- `ci: add GitLab APK pipelines`

Не смешивать несвязанные изменения.

## Правила GitLab CI/CD

- только GitLab pipeline
- не добавлять GitHub Actions
- debug APK как artifact
- release APK как artifact, либо явный blocker artifact при отсутствии signing variables

## Правила работы с reference-кодом

- reference-код лежит только в `_references/`
- не запускать runtime проекта на OpenAI backend
- переносить только подтверждённые layout/interaction patterns
- брендировать только как `Enterprise`
