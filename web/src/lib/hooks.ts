import { useEffect, useState, useCallback } from "react";
import { request } from "./api";
export function useResource<T>(path: string, body?: unknown) {
  const key = JSON.stringify(body);
  const [value, setValue] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setValue(undefined);
    setError("");
    request<T>(
      path,
      key === undefined ? undefined : JSON.parse(key),
      undefined,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setValue(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, key, version]);
  return { value, error, loading, reload };
}
export function useDebounced(value: string, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
