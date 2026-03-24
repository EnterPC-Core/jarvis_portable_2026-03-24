export interface Env {
  AI: Ai;
  DB: D1Database;
  CACHE: KVNamespace;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_ADMIN_ID: string;
  BOT_PUBLIC_URL: string;
  TELEGRAM_BOT_USERNAME?: string;
  BOT_NAME: string;
  BOT_MODE_DEFAULT: string;
  MEMORY_MODE: string;
  SEARCH_MODE: string;
  ALLOW_PUBLIC_ACCESS: string;
  WORKERS_AI_MODEL: string;
  SYSTEM_BRAND_NAME: string;
  CREATOR_NAME: string;
  OPTIONAL_ALLOWED_USER_IDS: string;
  OPTIONAL_ALLOWED_CHAT_IDS: string;
  VOICE_MODE?: string;
  DOCUMENT_TEXT_MAX_BYTES?: string;
}

export interface JsonObject {
  [key: string]: unknown;
}

export type BotAccessMode = 'public' | 'selective' | 'admin_only' | 'off' | 'test';
export type ResponseStyle = 'concise' | 'normal' | 'technical' | 'deep' | 'admin';

export interface AccessDecision {
  allowed: boolean;
  reason: string;
}

export interface SearchDecision {
  shouldSearch: boolean;
  reason: string;
}

export interface SearchResult {
  performed: boolean;
  provider: string;
  summary: string;
  sources: Array<{ title: string; url: string; snippet?: string }>;
  error?: string;
}

export interface ConversationTurn {
  role: 'system' | 'user' | 'assistant';
  content: string;
}
