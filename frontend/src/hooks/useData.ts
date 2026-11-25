import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";

/** Fetch JSON with loading/error state; optional polling interval in ms. */
export function useData<T = any>(path: string | null, poll?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    reload();
    if (!poll) return;
    const t = setInterval(reload, poll);
    return () => clearInterval(t);
  }, [reload, poll]);
  return { data, error, loading, reload, setData };
}

/** Live queue updates via server-sent events. */
export function useJobStream() {
  const [jobs, setJobs] = useState<any[]>([]);
  useEffect(() => {
    const es = new EventSource("/api/jobs/stream");
    es.onmessage = (e) => setJobs(JSON.parse(e.data));
    return () => es.close();
  }, []);
  return jobs;
}
