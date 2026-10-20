// The browser and Node.js run exactly the same public-ABI observations.
function assert(condition, message, value) {
  if (!condition) throw new Error(`${message}: ${JSON.stringify(value)}`);
}

async function runCase(workflow, test, trace = "full") {
  const received = [], sent = [], events = [];
  const input = test.offset === undefined ? {} : {"math.offset": test.offset};
  const result = await workflow.runWorkflowAsync(input, {
    trace, onTrace: event => events.push(event),
    capabilities: {"vibeflow.port": {
      async receive(request) { received.push(request); return {value: test.x}; },
      send(request) { sent.push(request); return null; },
    }},
  });
  assert(result.result === test.result, "wrong formula result", result);
  assert(JSON.stringify(result.history) === JSON.stringify(test.history), "wrong carry/collect history", result);
  assert(result.iterations === 3, "wrong iteration count", result);
  assert(Object.keys(result).sort().join(",") === "history,iterations,result", "public envelope leaked", result);
  assert(JSON.stringify(received) === '[{"port":"math.in"}]', "wrong receive", received);
  assert(JSON.stringify(sent) === JSON.stringify([{port: "math.out", value: test.result}]), "wrong send", sent);
  assert(events[0].kind === "run_start" && events.at(-1).kind === "run_end", "wrong run boundaries", events);
  const nodes = events.filter(event => event.kind === "node_start");
  if (trace === "full") {
    const root = nodes.filter(event => event.blockPath === "/").map(event => event.nodeId);
    assert(JSON.stringify(root) === JSON.stringify(["start", "receive", "offset", "prepare", "companion", "route", test.selected, "choice", "join", "loop", "finish", "send", "send_end"]), "wrong root execution order", root);
    assert(root.includes(test.selected) && !root.includes(test.selected === "square" ? "negative" : "square"), "inactive branch executed", root);
    assert(root.filter(id => id === "choice").length === 1 && root.filter(id => id === "join").length === 1, "join count differs", root);
    assert(nodes.some(event => event.nodePath === "prepare.inner.affine"), "nested path missing", nodes);
    assert(nodes.filter(event => event.nodeId === "step").length === 3, "loop body count differs", nodes);
    assert(events.filter(event => event.kind === "loop_iteration").length === 3, "loop trace count differs", events);
  } else {
    assert(nodes.length === 0, "boundary trace leaked node events", nodes);
    const kinds = events.map(event => event.kind);
    assert(kinds.includes("nodeset_enter") && kinds.includes("nodeset_exit"), "boundary trace lost nodeset boundaries", kinds);
  }
  return {name: test.name, result: result.result, history: result.history, trace,
    nodePaths: nodes.map(event => event.nodePath)};
}

export async function verify(workflow, cases) {
  const observations = [];
  for (const test of cases) observations.push(await runCase(workflow, test));
  observations.push(...await Promise.all([
    runCase(workflow, {...cases[0], name: "concurrent-positive"}),
    runCase(workflow, {...cases[1], name: "concurrent-negative"}, "boundary"),
  ]));
  // Hold a real Port receive. The workflow must remain pending until its
  // injected asynchronous dependency is released.
  let release, settled = false;
  const pending = workflow.runWorkflowAsync({}, {capabilities: {"vibeflow.port": {
    receive() { return new Promise(resolve => { release = () => resolve({value: cases[0].x}); }); },
    send() { return null; },
  }}});
  pending.then(() => { settled = true; });
  for (let attempt = 0; !release && attempt < 20; attempt++) await new Promise(resolve => setTimeout(resolve, 0));
  assert(typeof release === "function" && !settled, "async Port was not awaited", {settled});
  release();
  const result = await pending;
  assert(result.result === cases[0].result, "held Port result differs", result);
  return {observations, heldReceive: "PASS"};
}
