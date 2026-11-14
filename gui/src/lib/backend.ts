// Client for the Python bridge (src/autopayroll/bridge.py).
//
// The Rust shell is a dumb pipe: `backend_send` writes one JSON line to the
// bridge's stdin, and every line the bridge prints arrives as a
// `backend://message` event. Matching responses to requests happens here.

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

type Message =
  | { id: number; result: unknown }
  | { id: number; error: { message: string } }
  | { event: string; data: unknown };

export interface BackendHandlers {
  /** An unsolicited event from the bridge (log line, stage change, prompt…). */
  event(name: string, data: unknown): void;
  /** A raw stderr line from the bridge process (tracebacks, warnings). */
  stderr(line: string): void;
  /** The bridge process exited; `code` is null when it was killed. */
  exit(code: number | null): void;
}

export class BackendError extends Error {}

let nextId = 1;
const pending = new Map<
  number,
  { resolve: (value: unknown) => void; reject: (error: Error) => void }
>();

function rejectAll(reason: string): void {
  for (const { reject } of pending.values()) reject(new BackendError(reason));
  pending.clear();
}

/** Subscribe to the bridge and make sure its process is running. */
export async function connect(handlers: BackendHandlers): Promise<void> {
  await listen<Message>("backend://message", ({ payload }) => {
    if ("event" in payload) {
      handlers.event(payload.event, payload.data);
      return;
    }
    const waiter = pending.get(payload.id);
    if (!waiter) return;
    pending.delete(payload.id);
    if ("error" in payload) waiter.reject(new BackendError(payload.error.message));
    else waiter.resolve(payload.result);
  });
  await listen<string>("backend://stderr", ({ payload }) => handlers.stderr(payload));
  await listen<number | null>("backend://exit", ({ payload }) => {
    rejectAll("The payroll backend stopped.");
    handlers.exit(payload);
  });
  // Listeners first, so an immediate crash still reaches the UI.
  await invoke("backend_start");
}

/** Restart the bridge process (after a crash). */
export async function restart(): Promise<void> {
  rejectAll("The payroll backend was restarted.");
  await invoke("backend_restart");
}

/** Call a bridge method and wait for its result. */
export function call<T = unknown>(method: string, params: object = {}): Promise<T> {
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
    invoke("backend_send", { message: { id, method, params } }).catch((error) => {
      pending.delete(id);
      reject(new BackendError(String(error)));
    });
  });
}
