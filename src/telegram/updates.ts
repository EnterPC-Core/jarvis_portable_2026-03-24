import type { TelegramMessage } from './types';

export function getMessageText(message: TelegramMessage): string {
  return message.text?.trim() || message.caption?.trim() || '';
}

export function isCommand(message: TelegramMessage): boolean {
  return Boolean(message.text?.startsWith('/'));
}

export function isMentioned(message: TelegramMessage, botName: string, botUsername?: string): boolean {
  const text = getMessageText(message).toLowerCase();
  const normalizedBotName = botName.toLowerCase().trim();
  const normalizedUsername = (botUsername ?? '').toLowerCase().trim().replace(/^@+/, '');

  if (normalizedUsername && text.includes(`@${normalizedUsername}`)) {
    return true;
  }

  return normalizedBotName ? text.includes(normalizedBotName) : false;
}

export function isReplyToBot(message: TelegramMessage, botUserId?: number): boolean {
  return message.reply_to_message?.from?.id === botUserId;
}

export function shouldReplyInChat(input: {
  message: TelegramMessage;
  botName: string;
  botUsername?: string;
  botUserId?: number;
  activeReplyMode: string;
}): boolean {
  if (input.message.chat.type === 'private') {
    return true;
  }

  if (isCommand(input.message)) {
    return true;
  }

  if (isReplyToBot(input.message, input.botUserId)) {
    return true;
  }

  if (isMentioned(input.message, input.botName, input.botUsername)) {
    return true;
  }

  return input.activeReplyMode === 'always';
}

export function extractCommand(text: string): { command: string; args: string[] } {
  const parts = text.trim().split(/\s+/);
  const raw = parts.shift() ?? '';
  const command = raw.split('@')[0].toLowerCase();
  return { command, args: parts };
}
