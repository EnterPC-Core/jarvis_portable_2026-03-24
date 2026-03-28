import {
  ENTERPRISE_PATHS,
  ENTERPRISE_POLL_INTERVAL_MS,
  ENTERPRISE_TIMEOUT_MS,
} from "./config";
import { getEnterpriseCoreBaseUrl } from "./runtimeSettings";
import type {
  EnterpriseCapabilities,
  EnterpriseThread,
  JobSnapshot,
  RuntimeSnapshot,
  SendMessageResult,
  UnsupportedResult,
} from "../types";

const withBaseUrl = (path: string): string => {
  return `${getEnterpriseCoreBaseUrl()}${path}`;
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const targetUrl = withBaseUrl(path);
  let response: Response;
  try {
    response = await fetch(targetUrl, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const details = error instanceof Error ? error.message : "Network request failed";
    throw new Error(
      `Не удалось подключиться к Enterprise Core: ${targetUrl}. ${details}. Для APK укажи доступный адрес сервера и не используй 127.0.0.1, если backend работает вне приложения.`
    );
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${targetUrl}: ${text || `HTTP ${response.status}`}`);
  }

  return (await response.json()) as T;
}

const createServerChatId = (): number => {
  const now = Date.now();
  const random = Math.floor(Math.random() * 1000);
  return Number(`${String(now).slice(-9)}${String(random).padStart(3, "0")}`);
};

const createThreadSkeleton = (): EnterpriseThread => {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    localTitle: "Новая сессия",
    serverChatId: createServerChatId(),
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
};

export const enterpriseCapabilities: EnterpriseCapabilities = {
  serverThreads: false,
  serverCancel: false,
  attachments: false,
  widgets: false,
  dictation: false,
};

export const enterpriseCoreClient = {
  createSession(): Promise<EnterpriseThread> {
    return Promise.resolve(createThreadSkeleton());
  },
  async healthcheck(): Promise<RuntimeSnapshot> {
    const health = await fetchJson<RuntimeSnapshot>(ENTERPRISE_PATHS.health);
    const runtime = await fetchJson<RuntimeSnapshot>(ENTERPRISE_PATHS.runtimeStatus);
    return { ...health, ...runtime };
  },
  async sendMessage(thread: EnterpriseThread, prompt: string): Promise<SendMessageResult> {
    const payload = {
      chat_id: thread.serverChatId,
      prompt,
      codex_timeout: Math.floor(ENTERPRISE_TIMEOUT_MS / 1000),
    };
    const response = await fetchJson<{ ok: boolean; job_id: string }>(ENTERPRISE_PATHS.jobs, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.job_id) {
      throw new Error("Enterprise Core не вернул job_id.");
    }
    return { jobId: response.job_id };
  },
  async streamResponse(
    jobId: string,
    options: {
      signal?: AbortSignal;
      onSnapshot: (snapshot: JobSnapshot) => void;
    }
  ): Promise<JobSnapshot> {
    let latestSnapshot: JobSnapshot | null = null;
    while (true) {
      if (options.signal?.aborted) {
        throw new DOMException("Polling aborted", "AbortError");
      }
      const snapshot = await fetchJson<JobSnapshot>(`${ENTERPRISE_PATHS.jobs}/${jobId}`);
      latestSnapshot = snapshot;
      options.onSnapshot(snapshot);
      if (snapshot.done) {
        return snapshot;
      }
      await sleep(ENTERPRISE_POLL_INTERVAL_MS);
    }
  },
  async cancelResponse(): Promise<UnsupportedResult> {
    return {
      ok: false,
      reason: "В Enterprise Core сейчас нет подтверждённого server-side cancel endpoint.",
    };
  },
  async uploadAttachment(): Promise<UnsupportedResult> {
    return {
      ok: false,
      reason: "В Enterprise Core сейчас нет подтверждённого attachment upload endpoint.",
    };
  },
  async downloadAttachment(): Promise<UnsupportedResult> {
    return {
      ok: false,
      reason: "В Enterprise Core сейчас нет подтверждённого attachment download endpoint.",
    };
  },
};
