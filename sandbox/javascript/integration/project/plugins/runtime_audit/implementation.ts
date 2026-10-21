type PluginContext = Readonly<{
  pluginId: string;
  pluginType: "runtime";
  workflowId: string;
  config: Readonly<{ expectedNodes?: number }>;
  signal: Readonly<{ aborted: boolean }>;
}>;

export function createPlugin(context: PluginContext) {
  let beforeRuns = 0;
  let afterRuns = 0;
  let beforeBlocks = 0;
  let afterBlocks = 0;
  let beforeNodes = 0;
  let afterNodes = 0;
  return {
    beforeRun() {
      beforeRuns += 1;
    },
    afterRun() {
      afterRuns += 1;
    },
    beforeBlock() {
      beforeBlocks += 1;
    },
    afterBlock() {
      afterBlocks += 1;
    },
    beforeNode() {
      beforeNodes += 1;
    },
    afterNode() {
      afterNodes += 1;
    },
    dispose() {
      const expected = Number(context.config.expectedNodes ?? 0);
      if (context.signal.aborted) throw new Error("unexpected abort");
      if (beforeRuns !== 1 || afterRuns !== 1) {
        throw new Error("run hooks were not paired");
      }
      if (beforeBlocks !== 1 || afterBlocks !== 1) {
        throw new Error("block hooks were not paired");
      }
      if (beforeNodes !== expected || afterNodes !== expected) {
        throw new Error(
          `expected ${expected} node hook pairs, saw ${beforeNodes}/${afterNodes}`,
        );
      }
    },
  };
}
