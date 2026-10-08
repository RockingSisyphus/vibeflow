interface PortRequest {
  readonly port: string;
}

interface SendRequest extends PortRequest {
  readonly value: unknown;
}

interface PortCallOptions {
  readonly signal?: AbortSignal;
}

interface HostExtensionContext {
  readonly signal: AbortSignal;
}

interface InputMessage {
  readonly kind: "vibeflow-sandbox-input";
  readonly hostId: number;
  readonly value: unknown;
}

interface BindMessage {
  readonly kind: "vibeflow-sandbox-bind";
  readonly hostId: number;
}

interface PendingReceive {
  readonly signal: AbortSignal;
  readonly onAbort: () => void;
  readonly resolve: (value: { readonly value: unknown }) => void;
  readonly reject: (reason?: unknown) => void;
}

function isInputMessage(value: unknown): value is InputMessage {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<InputMessage>;
  return (
    candidate.kind === "vibeflow-sandbox-input"
    && typeof candidate.hostId === "number"
  );
}

function isBindMessage(value: unknown): value is BindMessage {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<BindMessage>;
  return (
    candidate.kind === "vibeflow-sandbox-bind"
    && typeof candidate.hostId === "number"
  );
}

export function createHostExtension(context: HostExtensionContext) {
  let hostId: number | null = null;
  const queued: unknown[] = [];
  let pending: PendingReceive | null = null;
  let receiveCount = 0;
  let started = false;

  function notify(payload: Record<string, unknown>): void {
    window.postMessage({ ...payload, hostId }, "*");
  }

  function settlePending(value: unknown): void {
    if (pending === null) {
      queued.push(value);
      return;
    }
    const current = pending;
    pending = null;
    current.signal.removeEventListener("abort", current.onAbort);
    current.resolve({ value });
  }

  function onMessage(event: MessageEvent<unknown>): void {
    if (event.source !== window) return;
    if (hostId === null && isBindMessage(event.data)) {
      hostId = event.data.hostId;
      notify({ kind: "vibeflow-sandbox-bound" });
      return;
    }
    if (!isInputMessage(event.data)) return;
    if (event.data.hostId !== hostId) return;
    settlePending(event.data.value);
  }

  return {
    capabilities: {
      "vibeflow.port": {
        receive(
          request: PortRequest,
          options: PortCallOptions = {},
        ): Promise<{ readonly value: unknown }> {
          receiveCount += 1;
          notify({
            kind: "vibeflow-sandbox-receive",
            port: request.port,
            receiveCount,
          });
          if (queued.length > 0) {
            return Promise.resolve({ value: queued.shift() });
          }
          const signal = options.signal ?? context.signal;
          notify({
            kind: "vibeflow-sandbox-waiting",
            port: request.port,
            receiveCount,
          });
          return new Promise((resolve, reject) => {
            const onAbort = () => {
              if (pending?.onAbort !== onAbort) return;
              pending = null;
              reject(signal.reason);
            };
            if (signal.aborted) {
              reject(signal.reason);
              return;
            }
            pending = { signal, onAbort, resolve, reject };
            signal.addEventListener("abort", onAbort, { once: true });
          });
        },
        send(request: SendRequest): null {
          notify({
            kind: "vibeflow-sandbox-output",
            port: request.port,
            value: request.value,
          });
          return null;
        },
      },
    },
    start(): void {
      if (started) return;
      started = true;
      window.addEventListener("message", onMessage);
      notify({ kind: "vibeflow-sandbox-lifecycle", phase: "start" });
    },
    stop(): void {
      if (!started) return;
      started = false;
      window.removeEventListener("message", onMessage);
      notify({ kind: "vibeflow-sandbox-lifecycle", phase: "stop" });
    },
  };
}
