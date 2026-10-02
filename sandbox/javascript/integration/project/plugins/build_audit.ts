export function createPlugin() {
  return {
    beforeCompile() { return {annotation: {phase: "beforeCompile"}}; },
    afterCompile() { return {annotation: {phase: "afterCompile"}}; },
  };
}
