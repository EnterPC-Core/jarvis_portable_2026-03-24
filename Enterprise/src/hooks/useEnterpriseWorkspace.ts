import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { enterpriseCapabilities, enterpriseCoreClient } from "../lib/enterpriseCoreClient";
import { threadRepository } from "../lib/threadRepository";
import type {
  EnterpriseMessage,
  EnterpriseThread,
  JobSnapshot,
  RuntimeSnapshot,
} from "../types";

const createMessage = (
  partial: Partial<EnterpriseMessage> & Pick<EnterpriseMessage, "role" | "content">
): EnterpriseMessage => {
  return {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    progressEvents: [],
    status: "idle",
    ...partial,
  };
};

const getInitialThreads = async (): Promise<EnterpriseThread[]> => {
  const existing = threadRepository.list();
  if (existing.length > 0) {
    return existing;
  }
  const firstThread = await enterpriseCoreClient.createSession();
  threadRepository.save(firstThread);
  threadRepository.setActiveThreadId(firstThread.id);
  return [firstThread];
};

const replaceThread = (threads: EnterpriseThread[], nextThread: EnterpriseThread): EnterpriseThread[] => {
  return threads.map((thread) => (thread.id === nextThread.id ? nextThread : thread));
};

export function useEnterpriseWorkspace() {
  const [threads, setThreads] = useState<EnterpriseThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [runtimeError, setRuntimeError] = useState<string>("");
  const [loadingRuntime, setLoadingRuntime] = useState(true);
  const [busyThreadId, setBusyThreadId] = useState<string | null>(null);
  const [composerText, setComposerText] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? null,
    [threads, activeThreadId]
  );

  const commitThreads = useCallback((updater: (current: EnterpriseThread[]) => EnterpriseThread[]) => {
    setThreads((current) => {
      const nextThreads = updater(current);
      threadRepository.saveAll(nextThreads);
      return nextThreads;
    });
  }, []);

  const saveThread = useCallback(
    (nextThread: EnterpriseThread) => {
      commitThreads((current) => replaceThread(current, nextThread));
    },
    [commitThreads]
  );

  const refreshHealth = useCallback(async () => {
    setLoadingRuntime(true);
    try {
      const snapshot = await enterpriseCoreClient.healthcheck();
      setRuntime(snapshot);
      setRuntimeError("");
    } catch (error) {
      setRuntimeError(error instanceof Error ? error.message : "Healthcheck failed");
    } finally {
      setLoadingRuntime(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const initialThreads = await getInitialThreads();
      setThreads(initialThreads);
      const storedActiveId = threadRepository.getActiveThreadId();
      setActiveThreadId(storedActiveId ?? initialThreads[0]?.id ?? null);
      void refreshHealth();
    })();
  }, [refreshHealth]);

  const selectThread = useCallback((threadId: string) => {
    setActiveThreadId(threadId);
    threadRepository.setActiveThreadId(threadId);
  }, []);

  const createThread = useCallback(async () => {
    const thread = await enterpriseCoreClient.createSession();
    commitThreads((current) => [thread, ...current]);
    selectThread(thread.id);
  }, [commitThreads, selectThread]);

  const renameThread = useCallback(
    (threadId: string, title: string) => {
      const nextTitle = title.trim() || "Новая сессия";
      commitThreads((current) =>
        current.map((thread) =>
          thread.id === threadId
            ? {
                ...thread,
                localTitle: nextTitle,
                updatedAt: new Date().toISOString(),
              }
            : thread
        )
      );
    },
    [commitThreads]
  );

  const deleteThread = useCallback(
    async (threadId: string) => {
      const nextThreads = threads.filter((thread) => thread.id !== threadId);
      if (nextThreads.length === 0) {
        const fallback = await enterpriseCoreClient.createSession();
        nextThreads.push(fallback);
      }
      threadRepository.saveAll(nextThreads);
      setThreads(nextThreads);
      threadRepository.remove(threadId);
      const nextActiveId = nextThreads[0]?.id ?? null;
      setActiveThreadId(nextActiveId);
      threadRepository.setActiveThreadId(nextActiveId);
    },
    [threads]
  );

  const updateAssistantMessage = useCallback(
    (thread: EnterpriseThread, assistantMessageId: string, snapshot: JobSnapshot) => {
      const nextMessages = thread.messages.map((message) => {
        if (message.id !== assistantMessageId) {
          return message;
        }
        const nextStatus: EnterpriseMessage["status"] = snapshot.done
          ? snapshot.error
            ? "error"
            : "done"
          : "streaming";
        return {
          ...message,
          content: snapshot.done ? snapshot.answer || message.content : message.content,
          progressEvents: snapshot.events,
          status: nextStatus,
          error: snapshot.error || undefined,
          jobId: snapshot.id,
        };
      });
      const nextThread = {
        ...thread,
        messages: nextMessages,
        updatedAt: new Date().toISOString(),
      };
      saveThread(nextThread);
    },
    [saveThread]
  );

  const sendMessage = useCallback(async () => {
    if (!activeThread || !composerText.trim() || busyThreadId) {
      return;
    }

    const userMessage = createMessage({
      role: "user",
      content: composerText.trim(),
      status: "done",
    });
    const assistantMessage = createMessage({
      role: "assistant",
      content: "",
      status: "streaming",
      progressEvents: ["• Старт\n└ Запрос поставлен в очередь клиента"],
    });

    const preparedThread: EnterpriseThread = {
      ...activeThread,
      messages: [...activeThread.messages, userMessage, assistantMessage],
      updatedAt: new Date().toISOString(),
    };

    setComposerText("");
    saveThread(preparedThread);
    setBusyThreadId(preparedThread.id);

    try {
      const { jobId } = await enterpriseCoreClient.sendMessage(preparedThread, userMessage.content);
      abortControllerRef.current = new AbortController();

      await enterpriseCoreClient.streamResponse(jobId, {
        signal: abortControllerRef.current.signal,
        onSnapshot: (snapshot) => {
          updateAssistantMessage(preparedThread, assistantMessage.id, snapshot);
        },
      });
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === "AbortError"
          ? "Локальное ожидание остановлено. Server-side cancel в Enterprise Core пока не реализован."
          : error instanceof Error
            ? error.message
            : "Не удалось получить ответ Enterprise Core.";

      const failedThread = {
        ...preparedThread,
        messages: preparedThread.messages.map((item) =>
          item.id === assistantMessage.id
            ? {
                ...item,
                status: "error" as const,
                error: message,
                progressEvents: [...item.progressEvents, `• Ошибка\n└ ${message}`],
              }
            : item
        ),
        updatedAt: new Date().toISOString(),
      };
      saveThread(failedThread);
    } finally {
      abortControllerRef.current = null;
      setBusyThreadId(null);
    }
  }, [activeThread, busyThreadId, composerText, saveThread, updateAssistantMessage]);

  const cancelActiveResponse = useCallback(async () => {
    if (!busyThreadId || !activeThread) {
      return;
    }
    abortControllerRef.current?.abort();
    const unsupported = await enterpriseCoreClient.cancelResponse();
    const nextThread = {
      ...activeThread,
      messages: activeThread.messages.map((item) =>
        item.status === "streaming"
          ? {
              ...item,
              status: "cancelled" as const,
              error: unsupported.reason,
              progressEvents: [...item.progressEvents, `• Отмена\n└ ${unsupported.reason}`],
            }
          : item
      ),
      updatedAt: new Date().toISOString(),
    };
    saveThread(nextThread);
    setBusyThreadId(null);
  }, [activeThread, busyThreadId, saveThread]);

  return {
    activeThread,
    activeThreadId,
    busyThreadId,
    capabilities: enterpriseCapabilities,
    composerText,
    loadingRuntime,
    runtime,
    runtimeError,
    threads,
    setComposerText,
    cancelActiveResponse,
    createThread,
    deleteThread,
    refreshHealth,
    renameThread,
    selectThread,
    sendMessage,
  };
}
