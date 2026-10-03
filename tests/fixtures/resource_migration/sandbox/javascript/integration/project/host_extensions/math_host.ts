interface HostExtensionInstance {
  readonly capabilities: {
    readonly "sandbox.host_math": {
      readonly double: (input: number) => number;
    };
  };
  start(): void;
  stop(): void;
}

export function createHostExtension(): HostExtensionInstance {
  const calls = (
    globalThis as unknown as {
      readonly __vibeflowSandboxHostCalls: string[];
    }
  ).__vibeflowSandboxHostCalls;
  calls.push("create");
  return {
    capabilities: {
      "sandbox.host_math": {
        double(input: number): number {
          return input * 2;
        },
      },
    },
    start(): void {
      calls.push("start");
    },
    stop(): void {
      calls.push("stop");
    },
  };
}
