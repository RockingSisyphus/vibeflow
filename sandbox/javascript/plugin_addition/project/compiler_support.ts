type PluginContext = Readonly<{
  pluginId: string;
  pluginType: "compiler";
  workflowId: string;
  config: Readonly<Record<string, unknown>>;
}>;

export function createPlugin(_context: PluginContext) {
  let phase = 0;
  return {
    beforeCompile() {
      if (phase !== 0) throw new Error("beforeCompile ran out of order");
      phase = 1;
      return {annotation: {phase: "beforeCompile"}};
    },
    afterCompile() {
      if (phase !== 1) throw new Error("afterCompile ran out of order");
      phase = 2;
      return {annotation: {phase: "afterCompile"}};
    },
  };
}
