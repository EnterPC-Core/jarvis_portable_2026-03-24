const BASE_URL_STORAGE_KEY = "enterprise.runtime.baseUrl";

const normalizeBaseUrl = (value: string): string => value.trim().replace(/\/+$/, "");

export const getDefaultEnterpriseCoreBaseUrl = (): string => {
  const envValue = import.meta.env.VITE_ENTERPRISE_CORE_BASE_URL;
  if (typeof envValue === "string" && envValue.trim()) {
    return normalizeBaseUrl(envValue);
  }
  return "http://127.0.0.1:8766";
};

export const getEnterpriseCoreBaseUrl = (): string => {
  if (typeof window === "undefined") {
    return getDefaultEnterpriseCoreBaseUrl();
  }
  const storedValue = window.localStorage.getItem(BASE_URL_STORAGE_KEY);
  if (storedValue && storedValue.trim()) {
    return normalizeBaseUrl(storedValue);
  }
  return getDefaultEnterpriseCoreBaseUrl();
};

export const saveEnterpriseCoreBaseUrl = (value: string): string => {
  const normalized = normalizeBaseUrl(value);
  if (!normalized) {
    throw new Error("Укажи URL Enterprise Core.");
  }
  try {
    new URL(normalized);
  } catch {
    throw new Error("URL Enterprise Core должен быть полным адресом, например http://192.168.1.10:8766");
  }
  window.localStorage.setItem(BASE_URL_STORAGE_KEY, normalized);
  return normalized;
};

export const resetEnterpriseCoreBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(BASE_URL_STORAGE_KEY);
  }
  return getDefaultEnterpriseCoreBaseUrl();
};
