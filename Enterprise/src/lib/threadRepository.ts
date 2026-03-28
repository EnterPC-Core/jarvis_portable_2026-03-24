import type { EnterpriseThread } from "../types";

const STORAGE_KEY = "enterprise.mobile.threads.v1";
const ACTIVE_THREAD_KEY = "enterprise.mobile.activeThreadId.v1";

const parseThreads = (raw: string | null): EnterpriseThread[] => {
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as EnterpriseThread[]) : [];
  } catch {
    return [];
  }
};

const persistThreads = (threads: EnterpriseThread[]) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
};

export const threadRepository = {
  list(): EnterpriseThread[] {
    return parseThreads(localStorage.getItem(STORAGE_KEY)).sort((left, right) =>
      right.updatedAt.localeCompare(left.updatedAt)
    );
  },
  saveAll(threads: EnterpriseThread[]) {
    persistThreads(threads);
  },
  save(thread: EnterpriseThread) {
    const threads = threadRepository.list().filter((item) => item.id !== thread.id);
    threads.push(thread);
    persistThreads(threads);
  },
  remove(threadId: string) {
    const threads = threadRepository.list().filter((item) => item.id !== threadId);
    persistThreads(threads);
    if (threadRepository.getActiveThreadId() === threadId) {
      localStorage.removeItem(ACTIVE_THREAD_KEY);
    }
  },
  getActiveThreadId(): string | null {
    return localStorage.getItem(ACTIVE_THREAD_KEY);
  },
  setActiveThreadId(threadId: string | null) {
    if (threadId) {
      localStorage.setItem(ACTIVE_THREAD_KEY, threadId);
      return;
    }
    localStorage.removeItem(ACTIVE_THREAD_KEY);
  },
};
