import { handleCallback, handleCommand } from '../commands/handlers';
import { decideAccess, isAdmin } from '../admin/access';
import { generateAssistantReply } from '../ai/generate';
import { logEvent } from '../logger';
import {
  appendChatMemory,
  appendUserMemory,
  getChatMemory,
  getChatReplyMode,
  getPersonaMode,
  getRecentHistory,
  getResolvedAccessMode,
  getSearchPreference,
  getUserMemory,
  saveMessage,
  upsertChat,
  upsertUser,
} from '../memory/store';
import { decideSearch, runSearch } from '../search';
import type { ConversationTurn, Env } from '../types';
import { json } from '../utils/http';
import { compactWhitespace, escapeHtml, truncate } from '../utils/strings';
import { getBotUsername, getDefaultAccessMode, getDefaultStyle } from '../utils/env';
import { answerCallbackQuery, sendMessage } from './api';
import { extractDocumentText, transcribeVoice } from './media';
import type { TelegramMessage, TelegramUpdate } from './types';
import { getMessageText, isCommand, shouldReplyInChat } from './updates';

function shouldBeShort(messageText: string): boolean {
  return messageText.length < 220;
}

function historyToTurns(history: Array<{ role: 'user' | 'assistant'; message_text: string }>): ConversationTurn[] {
  return history.filter((item) => item.message_text).map((item) => ({ role: item.role, content: item.message_text }));
}

async function resolveSearchMode(env: Env, message: TelegramMessage): Promise<string> {
  const userPref = await getSearchPreference(env, 'user', String(message.from?.id ?? ''));
  if (userPref) {
    return userPref.enabled ? userPref.mode : 'off';
  }
  const chatPref = await getSearchPreference(env, 'chat', String(message.chat.id));
  if (chatPref) {
    return chatPref.enabled ? chatPref.mode : 'off';
  }
  return env.SEARCH_MODE;
}

async function resolveStyle(env: Env, message: TelegramMessage) {
  const userStyle = await getPersonaMode(env, 'user', String(message.from?.id ?? ''));
  const chatStyle = await getPersonaMode(env, 'chat', String(message.chat.id));
  return userStyle ?? chatStyle ?? getDefaultStyle();
}

function buildUserMemoryLine(message: TelegramMessage, textInput: string): string | null {
  const trimmed = textInput.trim();
  if (!trimmed || trimmed.startsWith('/')) {
    return null;
  }

  if (message.chat.type === 'private') {
    return `Пользователь недавно писал: ${truncate(trimmed, 220)}`;
  }

  return `Пользователь участвовал в чате ${message.chat.id}: ${truncate(trimmed, 220)}`;
}

function buildChatMemoryLine(message: TelegramMessage, textInput: string): string | null {
  const trimmed = textInput.trim();
  if (!trimmed || trimmed.startsWith('/')) {
    return null;
  }

  const author = message.from?.first_name ?? message.from?.username ?? 'Пользователь';
  return `${author}: ${truncate(trimmed, 220)}`;
}

async function updateMemory(env: Env, message: TelegramMessage, textInput: string): Promise<void> {
  const userLine = buildUserMemoryLine(message, textInput);
  const chatLine = buildChatMemoryLine(message, textInput);

  if (message.from?.id && userLine) {
    await appendUserMemory(env, message.from.id, userLine);
  }

  if (chatLine) {
    await appendChatMemory(env, message.chat.id, chatLine);
  }
}

async function buildAssistantReply(env: Env, message: TelegramMessage, textInput: string): Promise<string> {
  const history = historyToTurns(await getRecentHistory(env, message.chat.id, 12));
  const userMemory = await getUserMemory(env, message.from?.id);
  const chatMemory = await getChatMemory(env, message.chat.id);
  const style = await resolveStyle(env, message);
  const searchMode = await resolveSearchMode(env, message);
  const searchDecision = decideSearch(textInput, searchMode);
  const searchResult = await runSearch(env, searchDecision, textInput);

  const reply = await generateAssistantReply({
    env,
    history,
    userMemory,
    chatMemory,
    userText: textInput,
    style,
    searchResult,
    shouldStayShort: shouldBeShort(textInput),
  });

  await logEvent(env, 'info', 'message_answered', 'Assistant replied', {
    chat_id: message.chat.id,
    user_id: message.from?.id,
    style,
    search_reason: searchDecision.reason,
    search_performed: searchResult.performed,
  });

  return compactWhitespace(reply);
}

async function processAssistantTurn(
  env: Env,
  message: TelegramMessage,
  textInput: string,
  messageKind = 'text',
): Promise<void> {
  const globalMode = await getResolvedAccessMode(env, getDefaultAccessMode(env));
  const access = await decideAccess(env, message, globalMode);
  if (!access.allowed) {
    await logEvent(env, 'info', 'message_skipped', 'Access denied for message', {
      reason: access.reason,
      chat_id: message.chat.id,
      user_id: message.from?.id,
    });
    return;
  }

  if (isCommand(message)) {
    const commandResult = await handleCommand(env, message);
    if (commandResult.handled) {
      await sendMessage(env, message.chat.id, escapeHtml(commandResult.text), commandResult.options ?? {});
      await saveMessage({
        env,
        chatId: message.chat.id,
        userId: message.from?.id,
        role: 'assistant',
        messageText: commandResult.text,
        messageKind: 'command',
      });
    }
    return;
  }

  const chatReplyMode = (await getChatReplyMode(env, message.chat.id)) ?? (message.chat.type === 'private' ? 'always' : 'smart');
  const shouldReply = shouldReplyInChat({
    message,
    botName: env.BOT_NAME,
    botUsername: getBotUsername(env),
    activeReplyMode: chatReplyMode,
  });

  if (!shouldReply || chatReplyMode === 'silent') {
    await logEvent(env, 'debug', 'smart_silence', 'Message skipped by routing rules', {
      chat_id: message.chat.id,
      user_id: message.from?.id,
      active_reply_mode: chatReplyMode,
    });
    return;
  }

  await saveMessage({
    env,
    chatId: message.chat.id,
    userId: message.from?.id,
    role: 'user',
    messageText: textInput,
    messageKind,
    telegramMessageId: message.message_id,
  });
  await updateMemory(env, message, textInput);

  const finalReply = await buildAssistantReply(env, message, textInput);
  await sendMessage(env, message.chat.id, escapeHtml(truncate(finalReply, 4096)));
  await saveMessage({
    env,
    chatId: message.chat.id,
    userId: message.from?.id,
    role: 'assistant',
    messageText: finalReply,
  });
}

async function handleDocumentMessage(env: Env, message: TelegramMessage): Promise<void> {
  const document = message.document;
  if (!document) return;

  const extracted = await extractDocumentText(env, document.file_id, document.file_name, document.mime_type);
  if (!extracted.ok) {
    await sendMessage(env, message.chat.id, escapeHtml(extracted.reason ?? 'Документ не удалось обработать.'));
    await logEvent(env, 'info', 'document_skipped', 'Document could not be parsed', {
      chat_id: message.chat.id,
      user_id: message.from?.id,
      file_name: document.file_name,
      mime_type: document.mime_type,
    });
    return;
  }

  const prompt = [
    `Пользователь прислал документ${document.file_name ? ` ${document.file_name}` : ''}.`,
    message.caption ? `Комментарий пользователя: ${message.caption}` : '',
    'Нужно изучить текст документа, кратко понять суть и ответить по делу.',
    '',
    extracted.text.slice(0, 12000),
  ].filter(Boolean).join('\n');

  await processAssistantTurn(env, message, prompt, 'document');
}

async function handleVoiceMessage(env: Env, message: TelegramMessage): Promise<void> {
  const voice = message.voice;
  if (!voice) return;

  const transcription = await transcribeVoice(env, voice.file_id);
  if (!transcription.ok) {
    await sendMessage(env, message.chat.id, escapeHtml(transcription.reason ?? 'Голосовое сообщение пока не поддерживается.'));
    await logEvent(env, 'info', 'voice_not_transcribed', 'Voice transcription unavailable', {
      chat_id: message.chat.id,
      user_id: message.from?.id,
      duration: voice.duration,
      mime_type: voice.mime_type,
    });
    return;
  }

  await processAssistantTurn(env, message, `Пользователь прислал голосовое сообщение. Транскрипция:\n${transcription.text}`, 'voice');
}

export async function handleTelegramWebhook(request: Request, env: Env): Promise<Response> {
  let update: TelegramUpdate;

  try {
    update = await request.json<TelegramUpdate>();
  } catch {
    return json({ ok: false, error: 'invalid_json' }, 400);
  }

  try {
    if (update.callback_query) {
      const callbackResult = await handleCallback(env, update.callback_query);
      await answerCallbackQuery(env, update.callback_query.id, callbackResult.toast);
      if (update.callback_query.message && callbackResult.messageText) {
        await sendMessage(
          env,
          update.callback_query.message.chat.id,
          escapeHtml(truncate(callbackResult.messageText, 4096)),
          callbackResult.options ?? {},
        );
      }
      return json({ ok: true });
    }

    if (update.my_chat_member) {
      await logEvent(env, 'info', 'chat_member_update', 'Received my_chat_member update', {
        chat_id: update.my_chat_member.chat.id,
        chat_type: update.my_chat_member.chat.type,
      });
      return json({ ok: true, skipped: 'my_chat_member' });
    }

    const message = update.message ?? update.edited_message;
    if (!message) {
      return json({ ok: true, skipped: 'unsupported_update' });
    }

    await upsertUser(env, message.from);
    await upsertChat(env, message.chat);

    const text = getMessageText(message);
    if (text) {
      await processAssistantTurn(env, message, text);
      return json({ ok: true });
    }

    if (message.document) {
      await handleDocumentMessage(env, message);
      return json({ ok: true, kind: 'document' });
    }

    if (message.voice) {
      await handleVoiceMessage(env, message);
      return json({ ok: true, kind: 'voice' });
    }

    await logEvent(env, 'debug', 'unsupported_message', 'Unsupported Telegram message type', {
      chat_id: message.chat.id,
      user_id: message.from?.id,
    });
    return json({ ok: true, skipped: 'unsupported_message' });
  } catch (error) {
    await logEvent(env, 'error', 'webhook_error', 'Unhandled Telegram webhook error', {
      error: error instanceof Error ? error.message : String(error),
    });

    const message = update.message ?? update.edited_message ?? update.callback_query?.message;
    if (message && isAdmin(env, message.from?.id)) {
      await sendMessage(env, message.chat.id, 'Внутренняя ошибка обработки. Подробности записаны в лог.').catch(() => undefined);
    }

    return json({ ok: false, error: 'internal_error' }, 500);
  }
}
