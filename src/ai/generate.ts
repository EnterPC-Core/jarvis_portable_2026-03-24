import { buildSystemPrompt } from '../persona/systemPrompt';
import type { ConversationTurn, Env, ResponseStyle, SearchResult } from '../types';
import { truncate } from '../utils/strings';

function buildSearchContext(searchResult: SearchResult): string {
  if (!searchResult.performed && !searchResult.summary) {
    return '';
  }

  const sources = searchResult.sources
    .map((source) => `- ${source.title}: ${source.url}${source.snippet ? ` — ${source.snippet}` : ''}`)
    .join('\n');

  return [searchResult.summary, sources].filter(Boolean).join('\n');
}

export async function generateAssistantReply(input: {
  env: Env;
  history: ConversationTurn[];
  userMemory: string;
  chatMemory: string;
  userText: string;
  style: ResponseStyle;
  searchResult: SearchResult;
  shouldStayShort: boolean;
}): Promise<string> {
  const system = buildSystemPrompt({
    botName: input.env.BOT_NAME,
    brandName: input.env.SYSTEM_BRAND_NAME,
    creatorName: input.env.CREATOR_NAME,
    responseStyle: input.style,
    userMemory: input.userMemory,
    chatMemory: input.chatMemory,
    searchContext: buildSearchContext(input.searchResult),
    shouldStayShort: input.shouldStayShort,
  });

  const messages = [
    { role: 'system', content: system },
    ...input.history.map((turn) => ({
      role: turn.role,
      content: truncate(turn.content, 2000),
    })),
    {
      role: 'user',
      content: truncate(input.userText, 4000),
    },
  ];

  const ai = input.env.AI as any;
  const result = (await ai.run(input.env.WORKERS_AI_MODEL, {
    messages,
    max_tokens: input.style === 'deep' ? 900 : 500,
    temperature: 0.35,
  })) as { response?: string };

  return result.response?.trim() || 'Сейчас не удалось сформировать ответ. Попробуй повторить запрос чуть короче.';
}
