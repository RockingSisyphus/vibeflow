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
