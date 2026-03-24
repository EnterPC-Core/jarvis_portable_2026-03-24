import { buildTelegramFileUrl, getFile } from './api';
import type { Env } from '../types';
import { getDocumentTextMaxBytes } from '../utils/env';

const supportedMimePrefixes = ['text/', 'application/json', 'application/xml'];
const supportedExtensions = ['.txt', '.md', '.json', '.csv', '.log', '.xml'];

function hasSupportedExtension(fileName = ''): boolean {
  return supportedExtensions.some((ext) => fileName.toLowerCase().endsWith(ext));
}

export async function extractDocumentText(
  env: Env,
  fileId: string,
  fileName?: string,
  mimeType?: string,
): Promise<{ ok: boolean; text: string; reason?: string }> {
  const isSupported = supportedMimePrefixes.some((prefix) => (mimeType ?? '').startsWith(prefix)) || hasSupportedExtension(fileName);

  if (!isSupported) {
    return {
      ok: false,
      text: '',
      reason: 'Этот тип документа пока не поддерживается для автоматического разбора. Сейчас доступны в основном текстовые файлы: txt, md, json, csv, log, xml.',
    };
  }

  const file = await getFile(env, fileId);
  const response = await fetch(buildTelegramFileUrl(env, file.file_path));
  if (!response.ok) {
    return { ok: false, text: '', reason: 'Не удалось скачать документ из Telegram.' };
  }

  const maxBytes = getDocumentTextMaxBytes(env);
  const blob = await response.arrayBuffer();
  if (blob.byteLength > maxBytes) {
    return {
      ok: false,
      text: '',
      reason: `Документ слишком большой для текущего лимита (${maxBytes} байт).`,
    };
  }

  return {
    ok: true,
    text: new TextDecoder().decode(blob),
  };
}

export async function transcribeVoice(_env: Env, _fileId: string): Promise<{ ok: boolean; text: string; reason?: string }> {
  return {
    ok: false,
    text: '',
    reason: 'Распознавание голосовых пока не подключено. Архитектура под него подготовлена, но для реальной транскрипции нужен отдельный внешний сервис или подтверждённый speech-to-text провайдер.',
  };
}
