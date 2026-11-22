// Fixed per-node workflow API. The host owns the session and actual completion.
function nodeWorkflow(state, node, execution) {
  const signal = execution?.signal || state.root.signal;
  const session = state.root.workflowSession;
  const location = {nodePath: nodePath(state, node.id), blockPath: formatBlockPath(state.path)};
  function operation(name, request = {}) {
    if (execution && !execution.active) throw vfError("VF_NODE_CONTEXT_EXITED", "Node invocation has exited", state.workflow, location);
    if (name !== "send" && name !== "invoke_sync") throwIfAborted(signal, state.workflow, location.nodePath, location.blockPath);
    if (typeof session?.[name] !== "function") throw vfError(session == null ? "VF_WORKFLOW_UNCONNECTED" : "VF_WORKFLOW_UNSUPPORTED", `workflow session does not provide ${name}`, state.workflow, location);
    return session[name](request, {signal});
  }
  function immediate(name, request) {
    const value = operation(name, request);
    if (value && typeof value.then === "function") throw vfError("VF_COMPLETION_MISMATCH", `workflow ${name} returned pending work`, state.workflow, location);
    return value;
  }
  function suspended(name, request) {
    const promise = (async () => {
      try { return await awaitWithAbort(operation(name, request), signal, state.workflow, location.nodePath, location.blockPath); }
      catch (error) {
        if (signal?.aborted) throwIfAborted(signal, state.workflow, location.nodePath, location.blockPath);
        throw error;
      }
    })();
    return execution ? execution.own(promise) : promise;
  }
  return Object.freeze({
    self: () => state.root.identity.self(),
    invoke_sync: request => immediate("invoke_sync", request),
    send: request => immediate("send", request),
    call: request => suspended("call", request),
    wait: request => suspended("wait", request),
    receive: request => suspended("receive", request),
    kill: request => suspended("kill", request),
  });
}

const __vfMultipleInputs = Symbol('native input envelopes');
