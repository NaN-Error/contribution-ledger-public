import { useCallback, useEffect, useRef, useState } from 'react';
import { api, explainError } from '../lib/api.js';

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setLoading(!!path);
    if (!path) return () => controller.abort();
    api<T>(path, 'GET', undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(error => { if (!controller.signal.aborted) setError(explainError(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, nonce]);
  return { data, error, loading, refresh };
}

export function useAction() {
  const busy = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  async function run<T>(task: () => Promise<T>, onSuccess?: (result: T) => void, message?: string) {
    if (busy.current) return;
    busy.current = true;
    setPending(true); setError(null); setSuccess(null);
    try { const result = await task(); onSuccess?.(result); if (message) setSuccess(message); }
    catch (error) { setError(explainError(error)); }
    finally { busy.current = false; setPending(false); }
  }
  return { pending, error, success, run };
}
