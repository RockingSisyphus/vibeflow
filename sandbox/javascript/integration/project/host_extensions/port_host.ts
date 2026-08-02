interface PortRequest {
  readonly port: string;
}

interface SendRequest extends PortRequest {
  readonly value: unknown;
}

interface PortCallOptions {
  readonly signal?: AbortSignal;
}

interface SandboxPortState {
  readonly inputs: unknown[];
  readonly received: PortRequest[];
  readonly sent: SendRequest[];
  readonly calls: string[];
  resolveFirstOutput?: () => void;
  resolveWaiting?: () => void;
}

interface HostExtensionContext {
  readonly signal: AbortSignal;
}

function sandboxState(): SandboxPortState {
  return (
    globalThis as unknown as {
      readonly __vibeflowSandboxPortState: SandboxPortState;
    }
  ).__vibeflowSandboxPortState;
}

export function createHostExtension(context: HostExtensionContext) {
  const state = sandboxState();
  state.calls.push("create");
  return {
    capabilities: {
      "vibeflow.port": {
        receive(
          request: PortRequest,
          options: PortCallOptions = {},
        ): Promise<{ readonly value: unknown }> {
          state.received.push(request);
          if (state.inputs.length > 0) {
            return Promise.resolve({ value: state.inputs.shift() });
          }
          state.resolveWaiting?.();
          state.resolveWaiting = undefined;
          const signal = options.signal ?? context.signal;
          return new Promise((_resolve, reject) => {
            if (signal.aborted) {
              reject(signal.reason);
              return;
            }
            signal.addEventListener(
              "abort",
              () => reject(signal.reason),
              { once: true },
            );
          });
        },
        send(request: SendRequest): null {
          state.sent.push(request);
          state.resolveFirstOutput?.();
          state.resolveFirstOutput = undefined;
          return null;
        },
      },
    },
    start(): void {
      state.calls.push("start");
    },
    stop(): void {
      state.calls.push("stop");
    },
  };
}
