const sandboxGlobal = globalThis as typeof globalThis & {
  __vibeflowSandboxHostCalls?: string[];
};

sandboxGlobal.__vibeflowSandboxHostCalls?.push("planned-import");

export function createHostExtension() {
  sandboxGlobal.__vibeflowSandboxHostCalls?.push("planned-create");
  return {
    start() {
      sandboxGlobal.__vibeflowSandboxHostCalls?.push("planned-start");
    },
    stop() {
      sandboxGlobal.__vibeflowSandboxHostCalls?.push("planned-stop");
    },
  };
}
