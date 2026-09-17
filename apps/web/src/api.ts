export type Json = Record<string, any>;

const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export async function api<T = Json>(path: string, options: RequestInit = {}, expert = false): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  // Local headers are ignored when Firebase authentication is enabled in production.
  headers.set("X-Actor-Id", expert ? "local-expert" : "local-farmer");
  headers.set("X-Actor-Role", expert ? "expert" : "farmer");
  const response = await fetch(`${base}${path}`, {...options, headers});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detailMsg = typeof body?.detail === "string" ? body.detail : Array.isArray(body?.detail) ? body.detail.map((d: any) => d.msg || JSON.stringify(d)).join("; ") : null;
    throw new Error(body?.error?.message || detailMsg || body?.message || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function upload(file: File, purpose: "soil_card" | "crop_diagnosis", expert = false) {
  const body = new FormData(); body.append("file", file); body.append("purpose", purpose);
  return api<Json>("/api/v1/media", {method: "POST", body}, expert);
}
