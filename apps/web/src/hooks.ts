import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

const cache = new Map<string, { at: number; data: unknown }>();
const inflight = new Map<string, Promise<unknown>>();
const TTL_MS = 10 * 60 * 1000;

export function invalidate(prefix: string) {
  for (const key of Array.from(cache.keys())) if (key.startsWith(prefix)) cache.delete(key);
}

async function load<T>(path: string, force: boolean): Promise<T> {
  const hit = cache.get(path);
  if (!force && hit && Date.now() - hit.at < TTL_MS) return hit.data as T;
  if (!force && inflight.has(path)) return inflight.get(path) as Promise<T>;
  const request = api<T>(path).then((data) => {
    cache.set(path, { at: Date.now(), data });
    return data;
  }).finally(() => inflight.delete(path));
  inflight.set(path, request);
  return request;
}

/** GET a JSON resource with a short shared cache; pass null to skip. */
export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(() => (path && cache.get(path) ? (cache.get(path)!.data as T) : null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const current = useRef(path);
  current.current = path;

  const run = useCallback(async (force = false) => {
    if (!path) return;
    setLoading(true);
    setError("");
    try {
      const result = await load<T>(path, force);
      if (current.current === path) setData(result);
    } catch (err) {
      if (current.current === path) setError((err as Error).message);
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setData(path && cache.get(path) ? (cache.get(path)!.data as T) : null);
    run(false);
  }, [run, path]);

  return { data, loading, error, reload: () => run(true), setData };
}

/** Localized crop name lookup from the crop catalog (falls back to the id). */
export function useCropName(locale: string) {
  const catalog = useResource<{ crops: { id: string; name: string }[] }>(`/api/v1/catalog/crops?locale=${locale}`);
  return (id?: string | null) => (id ? catalog.data?.crops.find((c) => c.id === id)?.name || id : "");
}
