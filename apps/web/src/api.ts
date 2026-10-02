export type Json = Record<string, any>;

const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

/** Expert access code, kept only for this browser session. */
export function expertCode(): string {
  try {
    return sessionStorage.getItem("kisanai_expert_code") || "";
  } catch {
    return "";
  }
}

/** Random id kept in this browser; the server uses it to know which farms you created. */
export function deviceId(): string {
  try {
    let id = localStorage.getItem("kisanai_device_id");
    if (!id) {
      id = typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
      localStorage.setItem("kisanai_device_id", id);
    }
    return id;
  } catch {
    return "";
  }
}

export async function api<T = Json>(path: string, options: RequestInit = {}, expert = false): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  // Local headers are ignored when Firebase authentication is enabled in production.
  headers.set("X-Actor-Id", expert ? "local-expert" : "local-farmer");
  headers.set("X-Actor-Role", expert ? "expert" : "farmer");
  if (expert) headers.set("X-Expert-Code", expertCode());
  const device = deviceId();
  if (device) headers.set("X-Device-Id", device);
  const response = await fetch(`${base}${path}`, {...options, headers});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detailMsg = typeof body?.detail === "string" ? body.detail : Array.isArray(body?.detail) ? body.detail.map((d: any) => d.msg || JSON.stringify(d)).join("; ") : null;
    throw new Error(body?.error?.message || detailMsg || body?.message || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

/** Shrinks a large photo to at most 1600 px (JPEG) so uploads stay quick on slow mobile data. */
async function shrinkPhoto(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.size < 1_500_000) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.85));
    return blob ? new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

export async function upload(file: File, purpose: "soil_card" | "crop_diagnosis", expert = false) {
  const body = new FormData();
  body.append("file", await shrinkPhoto(file));
  body.append("purpose", purpose);
  return api<Json>("/api/v1/media", { method: "POST", body }, expert);
}
