import type { Env, SearchDecision, SearchResult } from '../types';

const freshnessHints = [
  'сегодня',
  'вчера',
  'завтра',
  'новост',
  'цена',
  'стоит',
  'курс',
  'релиз',
  'анонс',
  'обновлен',
  'обновил',
  'версия',
  'последн',
  'актуальн',
  'свеж',
  'сейчас',
  'текущ',
  'сколько стоит',
  'когда выш',
  'вышел',
  '2025',
  '2026',
];

const productHints = [
  'iphone',
  'samsung',
  'pixel',
  'xiaomi',
  'android',
  'telegram',
  'cloudflare',
  'openai',
  'cursor',
  'linux',
  'ubuntu',
  'debian',
  'npm',
  'node',
  'python',
  'api',
  'бот',
];

const searchOnlyPatterns = [
  /какая\s+сейчас\s+цена/i,
  /какая\s+последняя\s+версия/i,
  /что\s+нового/i,
  /какие\s+новости/i,
  /когда\s+вышел/i,
  /что\s+произошло/i,
];

export function decideSearch(messageText: string, searchMode: string): SearchDecision {
  if (searchMode === 'off') {
    return { shouldSearch: false, reason: 'search_disabled' };
  }

  if (searchMode === 'on') {
    return { shouldSearch: true, reason: 'forced_by_user' };
  }

  const normalized = messageText.toLowerCase();
  const hasFreshnessHint = freshnessHints.some((hint) => normalized.includes(hint));
  const hasProductHint = productHints.some((hint) => normalized.includes(hint));
  const hasExplicitSearchPattern = searchOnlyPatterns.some((pattern) => pattern.test(messageText));

  if (hasExplicitSearchPattern) {
    return { shouldSearch: true, reason: 'explicit_freshness_request' };
  }

  if (hasFreshnessHint && hasProductHint) {
    return { shouldSearch: true, reason: 'fresh_tech_topic' };
  }

  if (hasFreshnessHint) {
    return { shouldSearch: true, reason: 'freshness_detected' };
  }

  return {
    shouldSearch: false,
    reason: 'context_sufficient',
  };
}

export async function runSearch(_env: Env, decision: SearchDecision, query: string): Promise<SearchResult> {
  if (!decision.shouldSearch) {
    return {
      performed: false,
      provider: 'none',
      summary: '',
      sources: [],
    };
  }

  return {
    performed: false,
    provider: 'unconfigured',
    summary: [
      'Запрос, вероятно, требует свежих внешних данных.',
      `Поисковый запрос: ${query.slice(0, 400)}`,
      'Но реальный search provider в текущей конфигурации не подключён, поэтому бот не будет имитировать интернет-поиск.',
      'Я могу ответить по общим знаниям либо после подключения внешнего search adapter использовать реальные свежие источники.',
    ].join(' '),
    sources: [],
    error: 'search_provider_not_configured',
  };
}
