# Enterprise Android

Android-приложение `Enterprise`, целиком расположенное в `projects/bots/jarvis_portable_2026-03-24/Enterprise`.

Проект опирается только на официальные открытые источники OpenAI как reference для каркаса, layout-паттернов, loading/error/progress states и panel/sidebar поведения, но не использует OpenAI backend как runtime backend. Рабочий ИИ-поток идёт только через текущий `Enterprise Core` сервер.

## Границы проекта

- Все изменения живут только в этой папке.
- `_references/` хранит скачанные официальные репозитории и HTML-копии официальной документации.
- Android tree находится в `android/`, сгенерирован через Capacitor внутри этой же директории.
- Соседние файлы и каталоги не являются рабочей зоной.

## Выбранный стек

- `React + Vite + TypeScript`
- `Capacitor Android`
- `GitHub Actions` и `GitLab CI/CD` для APK

Это минимальное отклонение от официальных web reference-проектов `openai-chatkit-starter-app` и `openai-chatkit-advanced-samples`: UI остаётся максимально близким к подтверждённым React/Vite паттернам, а Android APK получается через стандартный Capacitor wrapper.

## Что уже реализовано

- chat shell с layout, близким к официальным ChatKit примерам
- локальный thread list и локальные thread metadata
- composer / empty state / loading-progress state / error state
- Enterprise Core adapter с реальным `POST /api/jobs` и polling `GET /api/jobs/{id}`
- runtime health panel поверх `/health` и `/api/runtime/status`
- настраиваемый в UI `Enterprise Core URL`, сохраняемый локально для APK
- Android wrapper в `android/`
- GitHub Actions workflow для debug APK и release APK/signing flow
- GitLab pipeline для того же Android tree

## Что намеренно не выдумывается

Сервер `Enterprise Core` сейчас не подтверждает:

- server-side thread list/get/rename/delete
- server-side cancel endpoint
- attachment upload/download endpoints
- widget/structured output endpoints
- dictation/transcribe endpoint

Поэтому:

- thread list временно хранится локально в клиенте
- cancel останавливает только локальный polling
- attachments/widgets/dictation в UI отключены
- все такие места документированы как `TODO`, а не подменены выдуманным контрактом

## Локальная работа в UserLAnd

Системный `npm` в текущей среде нерабочий, поэтому используй Node 18 из `~/.nvm`.

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js install
```

Проверки:

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run typecheck

PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run build
```

Синхронизация Android wrapper:

```bash
cd /home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise
PATH=/home/userland/.nvm/versions/node/v18.20.8/bin:$PATH \
/home/userland/.nvm/versions/node/v18.20.8/bin/node \
/home/userland/.nvm/versions/node/v18.20.8/lib/node_modules/npm/bin/npm-cli.js run android:sync
```

Локальная полноценная APK-сборка не является обязательной. Основной сценарий сборки APK вынесен в CI.

## Настройка backend в APK

Debug APK из CI не знает заранее, где именно доступен ваш `Enterprise Core`, поэтому адрес сервера должен быть проверен в карточке `Runtime` после установки приложения.

- Открой `Runtime`
- В поле `Enterprise Core URL` укажи полный адрес сервера, например `http://192.168.1.10:8766`
- Нажми `Сохранить`
- Затем `Обновить`

Важно:

- `127.0.0.1` и `localhost` внутри APK почти никогда не означают ваш UserLAnd backend
- для Android включён cleartext `http`, поэтому debug-сценарий с локальным HTTP сервером допустим
- если сервер доступен только по HTTPS с нестандартным сертификатом, нужен отдельный подтверждённый TLS сценарий

## CI/CD

Файлы:

- [enterprise-android.yml](/home/userland/projects/bots/jarvis_portable_2026-03-24/.github/workflows/enterprise-android.yml)
- [`.gitlab-ci.yml`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/.gitlab-ci.yml)

GitHub Actions делает:

- `verify_web` — `npm ci`, `typecheck`, `build`, `cap sync android`
- `build_debug_apk` — собирает `app-debug.apk`
- `build_release_apk` — либо собирает signed `app-release.apk`, либо кладёт blocker artifact

GitLab делает:

- `verify_web` — `npm ci`, `typecheck`, `build`, `cap sync android`
- `build_debug_apk` — собирает `app-debug.apk`
- `build_release_apk` — либо собирает signed `app-release.apk`, либо кладёт в artifacts явный файл с отсутствующими переменными

## Secrets / Variables для release signing

GitHub secrets:

- `ENTERPRISE_RELEASE_KEYSTORE_BASE64`
- `ENTERPRISE_RELEASE_STORE_PASSWORD`
- `ENTERPRISE_RELEASE_KEY_ALIAS`
- `ENTERPRISE_RELEASE_KEY_PASSWORD`

GitLab variables:

- `ENTERPRISE_RELEASE_KEYSTORE_BASE64`
- `ENTERPRISE_RELEASE_STORE_PASSWORD`
- `ENTERPRISE_RELEASE_KEY_ALIAS`
- `ENTERPRISE_RELEASE_KEY_PASSWORD`

## Документация

- [`AGENTS.md`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/AGENTS.md)
- [`docs/source-map.md`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/docs/source-map.md)
- [`docs/openai-dependencies-audit.md`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/docs/openai-dependencies-audit.md)
- [`docs/adapter-layer.md`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/docs/adapter-layer.md)
- [`docs/enterprise-core-api-required.md`](/home/userland/projects/bots/jarvis_portable_2026-03-24/Enterprise/docs/enterprise-core-api-required.md)
