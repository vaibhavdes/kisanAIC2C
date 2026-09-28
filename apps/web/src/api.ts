export type Json = Record<string, any>;

const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const DEVICE_KEY = "kisanai_device_id";
const EXPERT_KEY = "kisanai_expert_code";

function safeGet(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(storage: Storage, key: string, value: string | null) {
  try {
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, value);
  } catch {
    /* storage unavailable (private mode) - identity lasts for this page only */
  }
}

let memoryDeviceId: string | null = null;

/** Anonymous per-device identity. No name, phone or login is collected. */
export function deviceId(): string {
  const stored = safeGet(localStorage, DEVICE_KEY);
  if (stored && /^dev-[a-z0-9-]{8,64}$/.test(stored)) return stored;
  if (!memoryDeviceId) {
    const random = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
    memoryDeviceId = `dev-${random.toLowerCase()}`;
    safeSet(localStorage, DEVICE_KEY, memoryDeviceId);
  }
  return memoryDeviceId;
}

export function expertCode(): string | null {
  return safeGet(sessionStorage, EXPERT_KEY);
}

export function setExpertCode(code: string | null) {
  safeSet(sessionStorage, EXPERT_KEY, code);
}

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;
  constructor(message: string, status: number, code = "error", retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

function headersFor(options: RequestInit, expert: boolean): Headers {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  headers.set("X-Actor-Id", deviceId());
  const code = expertCode();
  if (expert && code) headers.set("X-Expert-Token", code);
  if (expert && !code) headers.set("X-Actor-Role", "expert");
  return headers;
}

export async function api<T = Json>(path: string, options: RequestInit = {}, expert = false): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { ...options, headers: headersFor(options, expert) });
  } catch {
    throw new ApiError("No connection. Check your internet and try again.", 0, "network", true);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail
      : Array.isArray(body?.detail) ? body.detail.map((d: any) => d.msg || JSON.stringify(d)).join("; ") : null;
    throw new ApiError(body?.error?.message || detail || `Request failed (${response.status})`, response.status,
      body?.error?.code, Boolean(body?.error?.retryable));
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function apiBlob(path: string, options: RequestInit = {}, expert = false): Promise<Blob> {
  const response = await fetch(`${base}${path}`, { ...options, headers: headersFor(options, expert) });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body?.error?.message || `Request failed (${response.status})`, response.status, body?.error?.code);
  }
  return response.blob();
}

export function upload(file: File, purpose: "soil_card" | "crop_diagnosis") {
  const body = new FormData();
  body.append("file", file);
  body.append("purpose", purpose);
  return api<Json>("/api/v1/media", { method: "POST", body });
}

/** Play server text-to-speech; falls back to the browser voice when the server voice is unavailable. */
export async function speakText(text: string, locale: string): Promise<void> {
  try {
    const blob = await apiBlob("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text: text.slice(0, 4800), locale }) });
    await new Audio(URL.createObjectURL(blob)).play();
    return;
  } catch {
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = locale;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      return;
    }
    throw new ApiError("Voice playback is not available on this device.", 0);
  }
}
