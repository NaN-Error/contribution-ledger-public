import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiFailure, fetchStatus, type SystemStatus } from '../lib/status.js';

export interface StatusState {
  data: SystemStatus | null;
  loading: boolean;
  error: string | null;
  requestId: string | null;
  lastSuccess: string | null;
}

export function useSystemStatus() {
  const [state, setState] = useState<StatusState>({ data: null, loading: true, error: null, requestId: null, lastSuccess: null });
  const [tick, setTick] = useState(0);
  const generation = useRef(0);
  const refresh = useCallback(() => setTick(value => value + 1), []);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    let poll: ReturnType<typeof setTimeout> | undefined;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 6000);
    setState(previous => ({ ...previous, loading: true }));
    async function run() {
      try {
        const data = await fetchStatus(controller.signal);
        if (current !== generation.current) return;
        setState({ data, loading: false, error: null, requestId: null, lastSuccess: data.checked_at });
      } catch (error) {
        if (current !== generation.current) return;
        const message = timedOut ? 'The API did not respond in time. Check that the services are running.'
          : error instanceof ApiFailure ? error.message
          : 'The API cannot be reached. Check that the services are running.';
        setState(previous => ({ ...previous, data: null, loading: false, error: message,
          requestId: error instanceof ApiFailure ? error.requestId : null }));
      } finally {
        clearTimeout(timeout);
        if (current === generation.current) poll = setTimeout(refresh, 15000);
      }
    }
    void run();
    return () => { generation.current += 1; controller.abort(); clearTimeout(timeout); clearTimeout(poll); };
  }, [tick, refresh]);
  return { ...state, refresh };
}
