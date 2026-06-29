import { useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import type { JobEvent, JobStatus } from "@/lib/types";

const TERMINAL: JobStatus[] = ["completed", "error", "cancelled"];

/**
 * Subscribe to a job's live progress stream. Reconnects automatically until the
 * job reaches a terminal state. `onTerminal` fires once when that happens.
 */
export function useJobSocket(
  jobId: number,
  enabled: boolean,
  onTerminal?: (status: JobStatus) => void,
) {
  const [event, setEvent] = useState<JobEvent | null>(null);
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      ws = new WebSocket(wsUrl(jobId));
      ws.onmessage = (e) => {
        const msg: JobEvent = JSON.parse(e.data);
        if (msg.kind === "ping") return;
        setEvent(msg);
        if (msg.status && TERMINAL.includes(msg.status)) {
          closed = true;
          onTerminalRef.current?.(msg.status);
          ws?.close();
        }
      };
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [jobId, enabled]);

  return event;
}
