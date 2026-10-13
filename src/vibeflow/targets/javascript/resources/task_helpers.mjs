// Preserve language-provided causes and framework cleanup failures as data.
function taskErrorData(error, fallbackPath, seen = new Set()) {
  if(error && typeof error==='object') {
    if(seen.has(error))return {code:String(error.code || 'VF_NODE_FAILED'),
      message:String(error.message || error),node_path:String(error.nodePath || fallbackPath),
      source_location:error.sourceLocation || {}};
    seen.add(error);
  }
  const cause=error?.cause;
  return {
    code:String(error?.code || 'VF_NODE_FAILED'),
    message:String(cause?.message || error?.message || error),
    node_path:String(error?.nodePath || fallbackPath),
    source_location:error?.sourceLocation || {},
    exception_type:String(cause?.name || error?.name || typeof error),
    stack:String(cause?.stack || error?.stack || ''),
    ...(cause!==undefined ? {cause:taskErrorData(cause,fallbackPath,seen)} : {}),
    ...(Array.isArray(error?.errors) ? {errors:error.errors.map(item=>taskErrorData(item,fallbackPath,seen))} : {}),
    ...(error?.taskErrors ? {task_errors:error.taskErrors} : {}),
    ...(error?.cleanupErrors?.length ? {cleanup_errors:error.cleanupErrors.map(item=>taskErrorData(item,fallbackPath,seen))} : {}),
  };
}

// One registry per workflow invocation. Lists are ordinary arrays of references.
class TaskRegistry {
  constructor() {
    this.runId = globalThis.crypto?.randomUUID?.() || Array.from(
      globalThis.crypto?.getRandomValues(new Uint8Array(16))
        || Uint8Array.from({length:16}, ()=>Math.floor(Math.random()*256)),
      value=>value.toString(16).padStart(2,"0")).join("");
    this.nextId = 0;
    this.nextExit = 0;
    this.closing = false;
    this.records = new Map();
  }

  select(refs, workflow) {
    if (!Array.isArray(refs)) throw vfError("VF_TASK_REF_INVALID", "task references must be an array", workflow);
    const seen = new Set();
    return refs.map(ref => {
      if (!ref || ref.run_id !== this.runId || !this.records.has(ref.task_id))
        throw vfError("VF_TASK_REF_INVALID", "unknown or foreign workflow task reference", workflow);
      return this.records.get(ref.task_id);
    }).filter(record => !seen.has(record.ref.task_id) && seen.add(record.ref.task_id));
  }

  stop(records, reason = "task stop requested") {
    return records.map(record => {
      if (record.outcome) return {task: record.ref, state: "already_exited"};
      record.phase = "stopping";
      record.controller.abort(reason);
      return {task: record.ref, state: "stop_requested"};
    });
  }

  async drain(parent, workflow) {
    const children = [...this.records.values()].filter(record => record.parent === parent);
    this.stop(children);
    await Promise.allSettled(children.map(record => record.promise));
    const failures = children.filter(record => record.outcome.status === "failed" && !record.observed);
    const failed = failures[0];
    if (failed) {
      for (const record of failures) record.observed = true;
      throw vfError("VF_TASK_UNOBSERVED", failed.outcome.error.message, workflow,
        {nodePath: failed.outcome.error.node_path, taskErrors: failures.map(record=>record.outcome)});
    }
  }

  async finish(root) {
    this.closing = true;
    let statusFailure;
    if ([...this.records.values()].some(record=>!record.outcome)) {
      try { root.statusStopping?.(); } catch(error) { statusFailure = error; }
    }
    await this.drain(null, root.workflow);
    if (statusFailure) throw statusFailure;
  }

  start(key, inputs, node, state) {
    throwIfAborted(state.root.signal, state.workflow, nodePath(state, node.id));
    if (this.closing) throw vfError("VF_ABORTED", "workflow is stopping", state.workflow);
    const targets = state.taskExecutors[node.id];
    const execute = typeof key === "string" && targets && Object.hasOwn(targets, key) ? targets[key] : null;
    if (!execute) throw vfError("VF_TASK_TARGET_UNKNOWN", `undeclared task target '${key}'`, state.workflow);
    if (!inputs || typeof inputs !== "object" || Array.isArray(inputs)) throw vfError("VF_TASK_INPUT_INVALID", "task inputs must be an object", state.workflow);
    const controller = new AbortController();
    const parentSignal = state.root.signal;
    let record;
    const abort = () => {if (record && !record.outcome) record.phase="stopping"; controller.abort(parentSignal.reason);};
    parentSignal.addEventListener("abort", abort, {once: true});
    const ref = Object.freeze({run_id: this.runId, task_id: String(++this.nextId)});
    record = {ref, controller, parent: state.root.currentTask?.ref.task_id ?? null,
      promise: null, outcome: null, observed: false, exitOrder: 0, phase:"running"};
    this.records.set(ref.task_id, record);
    record.promise = (async () => {
      let output;
      let failure;
      const root = {...state.root, signal: controller.signal, currentTask: record};
      try {
        await Promise.resolve();
        throwIfAborted(controller.signal, state.workflow);
        const result = await execute(inputs, root, [...state.path, node.id, "tasks", key, `task_${ref.task_id}`]);
        output = result.publicOutputs;
      } catch (error) { failure = error; }
      try { await this.drain(ref.task_id, state.workflow); }
      catch (error) {
        if (failure) (failure.cleanupErrors ||= []).push(error);
        else failure = error;
      }
      parentSignal.removeEventListener("abort", abort);
      record.controller = null;
      record.phase = "exited";
      const status = failure ? (failure.code === "VF_ABORTED" && !failure.cleanupErrors?.length ? "cancelled" : "failed") : "succeeded";
      record.outcome = Object.freeze({task: ref, status,
        ...(status === "succeeded" ? {outputs: output} : {error:taskErrorData(failure,nodePath(state,node.id))})});
      record.exitOrder = ++this.nextExit;
      try { emitTrace(state.root, "task_exited", {task: ref, status, managerNode: node.id, nodePath:nodePath(state,node.id),blockPath:formatBlockPath(state.path)}); }
      catch (error) {
        record.outcome = Object.freeze({task:ref, status:"failed", error:{code:error.code,
          message:error.message, node_path:error.nodePath || nodePath(state,node.id)}});
      }
      return record.outcome;
    })();
    emitTrace(state.root, "task_started", {task: ref, managerNode: node.id, key, nodePath:nodePath(state,node.id),blockPath:formatBlockPath(state.path)});
    return ref;
  }
}

function taskController(node, state, execution) {
  const assertActive = (starting=false) => {
    if (execution && !execution.active) throw vfError("VF_TASK_CONTEXT_EXITED", "task controller's Node invocation has exited", state.workflow);
    if (starting && execution?.stopping) throw vfError("VF_ABORTED", "Node invocation is stopping", state.workflow);
  };
  const registry = state.root.taskRegistry;
  return Object.freeze({
    start: (key, inputs = {}) => {assertActive(true); return registry.start(key, inputs, node, state);},
    requestStop: (refs, reason) => {assertActive(); return registry.stop(registry.select(refs, state.workflow), reason);},
    waitAny(refs) {
      assertActive();
      const waiting = (async () => {
      const records = registry.select(refs, state.workflow);
      if (!records.length) return null;
      const ready = records.filter(record => record.outcome).sort((a,b) => a.exitOrder-b.exitOrder);
      const result = ready.length ? ready[0].outcome : await waitTaskNotification(
        Promise.race(records.map(record => record.promise)), execution?.signal || state.root.signal, state.workflow);
      registry.records.get(result.task.task_id).observed = true;
      return result;
      })();
      return execution ? execution.own(waiting) : waiting;
    },
    waitAllExited(refs) {
      assertActive();
      const waiting = (async () => {
      const records = registry.select(refs, state.workflow);
      const outcomes = await Promise.all(records.map(record => record.promise));
      for (const record of records) record.observed = true;
      return outcomes;
      })();
      return execution ? execution.own(waiting) : waiting;
    },
  });
}

async function waitTaskNotification(value, signal, workflow) {
  throwIfAborted(signal, workflow);
  let onAbort;
  const cancelled = new Promise((_, reject) => {
    onAbort = () => reject(vfError("VF_ABORTED", "task observer cancelled", workflow));
    signal.addEventListener("abort", onAbort, {once:true});
  });
  try { return await Promise.race([value, cancelled]); }
  finally { signal.removeEventListener("abort", onAbort); }
}

// Each actual Node invocation owns SDK operations, including Promise.race losers.
// This is an execution record, not a public task group or a data value.
class NodeExecution {
  constructor(parentSignal) {
    this.controller = new AbortController();
    this.signal = this.controller.signal;
    this.operations = new Set();
    this.active = true;
    this.stopping = false;
    this.parentSignal = parentSignal;
    this.abort = () => this.controller.abort(parentSignal.reason);
    parentSignal.addEventListener("abort", this.abort, {once:true});
    if (parentSignal.aborted) this.abort();
  }
  own(promise) {
    this.operations.add(promise);
    promise.then(()=>this.operations.delete(promise),()=>this.operations.delete(promise));
    return promise;
  }
  exitSync() {
    this.stopping = true;
    this.controller.abort("Node exiting");
    this.active = false;
    this.parentSignal.removeEventListener("abort", this.abort);
  }
  async exit() {
    this.stopping = true;
    this.controller.abort("Node exiting");
    const failures = [];
    try {
      while (this.operations.size) {
        const outcomes = await Promise.allSettled([...this.operations]);
        for (const outcome of outcomes) {
          if (outcome.status === "rejected" && (outcome.reason?.code !== "VF_ABORTED" || outcome.reason?.cleanupErrors?.length))
            failures.push(outcome.reason);
        }
      }
    } finally {
      this.active = false;
      this.parentSignal.removeEventListener("abort",this.abort);
      this.operations.clear();
    }
    if (failures.length) {
      const first = failures[0];
      if (failures.length > 1) (first.cleanupErrors ||= []).push(...failures.slice(1));
      throw first;
    }
  }
}
