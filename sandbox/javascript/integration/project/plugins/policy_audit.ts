type PluginContext = Readonly<{
  pluginId: string;
  pluginType: "policy";
  workflowId: string;
  config: Readonly<{ expectedNodes?: number }>;
}>;

type HookPayload = Readonly<Record<string, unknown>>;

export function createPlugin(context: PluginContext) {
  let policyExtended = false;
  let validatedNodes = 0;
  return {
    extendPolicy(payload: HookPayload) {
      if (!Object.isFrozen(payload)) {
        throw new Error("policy payload must be frozen");
      }
      policyExtended = true;
      return {annotation: {phase: "policy", pluginId: context.pluginId}};
    },
    validateNode() {
      if (!policyExtended) throw new Error("extendPolicy must run first");
      validatedNodes += 1;
    },
    validateGraph() {
      const expected = Number(context.config.expectedNodes ?? 0);
      if (validatedNodes !== expected) {
        throw new Error(`expected ${expected} nodes, saw ${validatedNodes}`);
      }
      return {annotation: {validatedNodes}};
    },
  };
}
