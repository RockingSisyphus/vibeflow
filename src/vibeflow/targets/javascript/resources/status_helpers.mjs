// Target-independent status cache. Node AOT supplies file sinks; browsers use onStatus.
function __vfSnapshotInfo(info) {
  const active = new Set();
  function copy(value) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return value;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value !== "object" || active.has(value)) throw new TypeError("run info must contain JSON values");
    const array = Array.isArray(value);
    if (!array && ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
      throw new TypeError("run info must contain plain JSON objects");
    }
    active.add(value);
    let result;
    if (array) {
      result = Array.from(value, item => copy(item));
    } else {
      result = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copy(item)]));
    }
    active.delete(value);
    return Object.freeze(result);
  }
  if (!Array.isArray(info) || info.some(item => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new TypeError("run info must be an array of JSON objects");
  }
  return copy(info);
}

function __vfObservation(options) {
  const raw = options ?? {};
  const interval = raw.statusIntervalMs ?? 60000;
  if (!Number.isFinite(interval) || interval <= 0) throw new TypeError("statusIntervalMs must be positive finite milliseconds");
  if (raw.onStatus !== undefined && typeof raw.onStatus !== "function") throw new TypeError("onStatus must be a function");
  let info = Object.freeze([]);
  let state = "starting";
  let error = null;
  let closed = false;
  let timer;
  let sink;
  const record = () => Object.freeze({state, error, updated_at: new Date().toISOString(), info});
  const publish = () => {
    const snapshot = record();
    sink?.publish(snapshot);
    raw.onStatus?.(snapshot);
  };
  const observer = {
    updateInfo(value) {
      if (closed) throw new Error("cannot update info after the run has finished");
      info = __vfSnapshotInfo(value);
      sink?.cache(record());
    },
    kernel(event) { sink?.kernel(JSON.stringify(event)); },
    run(callback) { return sink ? sink.run(callback) : callback(); },
    stopping() {
      if (closed || state === "stopping") return;
      state = "stopping";
      publish();
    },
    start() {
      if (typeof __vfCreateFileObservation === "function") {
        sink = __vfCreateFileObservation(raw, record(), interval);
      }
      publish();
      state = "running";
      publish();
      if (raw.onStatus) {
        timer = setInterval(() => {
          try { raw.onStatus(record()); }
          catch (failure) {
            try { observer.finish(failure); } catch { /* The sink may also fail. */ }
            throw failure;
          }
        }, interval);
        timer.unref?.();
      }
    },
    finish(failure) {
      if (closed) return;
      if (timer) clearInterval(timer);
      state = failure ? "failed" : "succeeded";
      if (failure) {
        const messages = [];
        const seen = new Set();
        for (let cause = failure; cause && !seen.has(cause); cause = cause.cause) {
          seen.add(cause);
          messages.push(String(cause.message || cause));
        }
        error = messages.join(": ");
      } else error = null;
      if (failure) sink?.kernel(String(failure.stack || failure));
      closed = true;
      try { sink?.finish(record()); raw.onStatus?.(record()); }
      catch (cause) {
        if (!failure) {
          state = "failed";
          error = String(cause?.message || cause);
          try { sink?.finish(record()); } catch { /* Preserve the sink failure. */ }
        }
        throw cause;
      }
      finally { sink?.close(); }
    },
  };
  return observer;
}

function __vfObservedOptions(options, observer) {
  return {...(options ?? {}), __vfStatusUpdate: info => observer.updateInfo(info),
          __vfKernelLog: event => observer.kernel(event), __vfStatusStopping: () => observer.stopping()};
}

function __vfObserveSync(invoke, inputs, options) {
  if (options !== undefined && (!options || typeof options !== "object" || Array.isArray(options))) return invoke(inputs, options);
  const observer = __vfObservation(options);
  try {
    observer.start();
    const outputs = observer.run(() => invoke(inputs, __vfObservedOptions(options, observer)));
    observer.finish(null);
    return outputs;
  } catch (error) {
    try { observer.finish(error); } catch { /* Preserve the execution failure. */ }
    throw error;
  }
}

async function __vfObserveAsync(invoke, inputs, options) {
  if (options !== undefined && (!options || typeof options !== "object" || Array.isArray(options))) return invoke(inputs, options);
  const observer = __vfObservation(options);
  try {
    observer.start();
    const outputs = await observer.run(() => invoke(inputs, __vfObservedOptions(options, observer)));
    observer.finish(null);
    return outputs;
  } catch (error) {
    try { observer.finish(error); } catch { /* Preserve the execution failure. */ }
    throw error;
  }
}
