const assert = (condition, message) => {if (!condition) throw new Error(message);};
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done;}); return {promise, resolve};};

export async function finite(workflow) {
  function invocation(b, label) {
    const gate = deferred(), arrived = deferred(), calls = [], trace = [];
    let settled = false;
    const promise = workflow.runWorkflowAsync({key:"same", b}, {
      trace:"full", onTrace:event => trace.push(event),
      capabilities:{"addition.storage":{read(request){calls.push({label,...request}); arrived.resolve(); return gate.promise;}}},
    });
    assert(promise instanceof Promise, "finite invocation did not return a Promise");
    promise.then(()=>{settled=true;});
    return {promise, arrived:arrived.promise, gate, calls, trace, settled:()=>settled};
  }
  const left = invocation(3, "left"), right = invocation(20, "right");
  await Promise.all([left.arrived, right.arrived]);
  await Promise.resolve();
  assert(!left.settled() && !right.settled(), "unreleased Capability completed early");
  right.gate.resolve({value:10});
  const second = await right.promise;
  assert(second.result === 30 && !left.settled(), "concurrent Capability calls mixed");
  left.gate.resolve({value:2});
  const first = await left.promise;
  assert(first.result === 5, JSON.stringify(first));
  for (const [call,label] of [[left,"left"],[right,"right"]]) {
    assert(JSON.stringify(call.calls) === JSON.stringify([{label,key:"same"}]), "wrong request count or key");
    assert(call.trace[0].kind === "run_start" && call.trace.at(-1).kind === "run_end", "wrong run boundaries");
    assert(call.trace.filter(event=>event.kind==="node_start" && event.nodePath==="add").length===1, "addition executed more than once");
  }
  assert(left.trace !== right.trace, "trace arrays shared");
  return {results:[first.result,second.result], requests:[left.calls,right.calls], heldUntilRelease:true, independent:true,
    checks:{promise:"PASS", waiting:"PASS", results:"PASS", requests:"PASS", concurrentIsolation:"PASS", trace:"PASS"}};
}

export async function stream(workflow, state) {
  assert(state.calls.length === 0, "host started on import");
  const host = workflow.createWorkflowHost();
  assert(JSON.stringify(state.calls)==='["create"]', "wrong creation lifecycle");
  await host.start();
  const invocation = host.runWorkflowAsync({});
  assert(invocation instanceof Promise, "host invocation is not a Promise");
  let failureCode;
  const observed = invocation.then(()=>{failureCode="completed";},error=>{failureCode=error.code;});
  let deadline;
  try {
    await Promise.race([state.waitingReady, new Promise((_,reject)=>{
      deadline=setTimeout(()=>reject(new Error("Port did not reach pending receive")),2000);
    })]);
  } finally {
    clearTimeout(deadline);
  }
  assert(JSON.stringify(state.sent)==='[{"port":"addition.out","value":5},{"port":"addition.out","value":30}]', JSON.stringify(state.sent));
  assert(JSON.stringify(state.received)==='[{"port":"addition.in"},{"port":"addition.in"},{"port":"addition.in"}]', JSON.stringify(state.received));
  await host.stop();
  await observed;
  await host.stop();
  assert(failureCode==="VF_ABORTED" && host.started===false, String(failureCode));
  assert(JSON.stringify(state.calls)==='["create","start","stop"]', JSON.stringify(state.calls));
  return {sent:state.sent, received:state.received, lifecycle:state.calls, failureCode,
    checks:{importWithoutStart:"PASS", lifecycle:"PASS", portTraffic:"PASS", pendingAbort:"PASS", idempotentStop:"PASS"}};
}
