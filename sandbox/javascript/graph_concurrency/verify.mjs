// Exercise each module twice to detect stale queue/barrier state.
export async function verify(workflow, scenario) {
  const rows = [];
  for (let round = 0; round < 2; round++) {
    const trace = [];
    const outputs = await workflow.runWorkflowAsync({scenario}, {
      trace: 'full', onTrace: event => trace.push(event),
    });
    if (JSON.stringify(outputs.report) !== JSON.stringify(Array.from({length: 12}, (_, i) => i))) {
      throw Error(JSON.stringify(outputs));
    }
    rows.push({round, outputs, trace});
  }
  return rows;
}
