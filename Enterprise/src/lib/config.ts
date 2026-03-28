const readString = (value: unknown, fallback: string): string => {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
};

const readNumber = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

export const ENTERPRISE_CORE_BASE_URL = readString(
  import.meta.env.VITE_ENTERPRISE_CORE_BASE_URL,
  "http://127.0.0.1:8766"
);

export const ENTERPRISE_POLL_INTERVAL_MS = readNumber(
  import.meta.env.VITE_ENTERPRISE_POLL_INTERVAL_MS,
  800
);

export const ENTERPRISE_TIMEOUT_MS = readNumber(
  import.meta.env.VITE_ENTERPRISE_TIMEOUT_MS,
  180000
);

export const ENTERPRISE_PATHS = {
  health: "/health",
  runtimeStatus: "/api/runtime/status",
  jobs: "/api/jobs",
  runSync: "/api/run_sync",
} as const;
