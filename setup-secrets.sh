#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
GITIGNORE_FILE="$PROJECT_DIR/.gitignore"
DEV_VARS_FILE="$PROJECT_DIR/.dev.vars"
DEV_VARS_EXAMPLE="$PROJECT_DIR/.dev.vars.example"

ensure_gitignore_entry() {
  if [ ! -f "$GITIGNORE_FILE" ]; then
    : > "$GITIGNORE_FILE"
  fi

  if ! grep -Fxq '.dev.vars' "$GITIGNORE_FILE"; then
    printf '\n.dev.vars\n' >> "$GITIGNORE_FILE"
  fi
}

write_dev_vars() {
  if [ -f "$DEV_VARS_EXAMPLE" ]; then
    cp "$DEV_VARS_EXAMPLE" "$DEV_VARS_FILE"
  else
    cat > "$DEV_VARS_FILE" <<'VARS'
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_ID=
BOT_PUBLIC_URL=
BOT_NAME=Jarvis AI
TELEGRAM_BOT_USERNAME=
BOT_MODE_DEFAULT=selective
MEMORY_MODE=d1
SEARCH_MODE=auto
ALLOW_PUBLIC_ACCESS=false
WORKERS_AI_MODEL=@cf/meta/llama-3.1-8b-instruct-fast
SYSTEM_BRAND_NAME=Jarvis AI
CREATOR_NAME=Дмитрий
OPTIONAL_ALLOWED_USER_IDS=
OPTIONAL_ALLOWED_CHAT_IDS=
VOICE_MODE=disabled
DOCUMENT_TEXT_MAX_BYTES=262144
VARS
  fi

  chmod 600 "$DEV_VARS_FILE"
  printf 'Created %s\n' "$DEV_VARS_FILE"
  printf '\nCloudflare Dashboard setup:\n'
  printf '1. Open Workers & Pages -> your worker -> Settings -> Variables and Secrets\n'
  printf '2. Add secret: TELEGRAM_BOT_TOKEN\n'
  printf '3. Add plain text variables: TELEGRAM_ADMIN_ID, BOT_PUBLIC_URL\n'
  printf '4. Optionally add TELEGRAM_BOT_USERNAME for accurate group mentions\n'
  printf '5. Redeploy the Worker after saving variables\n'
}

ensure_gitignore_entry
write_dev_vars
