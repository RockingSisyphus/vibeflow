export function createPlugin(context: Readonly<{
  pluginId: string;
  pluginType: "policy" | "compiler";
  workflowId: string;
  config: Readonly<Record<string, unknown>>;
}>): Record<string, (payload: Readonly<Record<string, unknown>>) => unknown> {
  let phase = 0;
  if (context.pluginType === "policy") {
    return {
      extendPolicy() {
        phase = 1;
        return { annotation: { phase: "policy" } };
      },
      validateGraph() {
        if (phase !== 1) throw new Error("policy hook order was not preserved");
        phase = 2;
        return { annotation: { graphValidated: true } };
      },
    };
  }
  return {
    beforeCompile() {
      if (phase !== 0) throw new Error("compiler beforeCompile ran twice");
      phase = 1;
      return { annotation: { phase: "beforeCompile" } };
    },
    afterCompile() {
      if (phase !== 1) throw new Error("compiler afterCompile order was wrong");
      phase = 2;
      return { annotation: { phase: "afterCompile" } };
    },
    validateCompiledGraph() {
      if (phase !== 2) throw new Error("compiled graph validation order was wrong");
      phase = 3;
      return { annotation: { compiledValidated: true } };
    },
  };
}
