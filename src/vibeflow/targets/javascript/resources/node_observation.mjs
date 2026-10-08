// Node-only file and console adapter; omitted from browser bundles.
import * as __vfFs from "node:fs";
import * as __vfPath from "node:path";
import {randomUUID as __vfUuid} from "node:crypto";
import {AsyncLocalStorage as __vfAsyncLocalStorage} from "node:async_hooks";
import {Worker as __vfStatusWorker} from "node:worker_threads";

const __vfConsoleKey = Symbol.for("vibeflow.console.observation.v1");
function __vfConsoleStorage() {
  if (!globalThis[__vfConsoleKey]) {
    const storage = new __vfAsyncLocalStorage();
    globalThis[__vfConsoleKey] = storage;
    for (const stream of [process.stdout, process.stderr]) {
      const original = stream.write;
      stream.write = function(chunk, ...args) {
        storage.getStore()?.business(chunk);
        return original.call(this, chunk, ...args);
      };
    }
  }
  return globalThis[__vfConsoleKey];
}

const __vfHeartbeatSource = `
const {workerData, parentPort} = require('node:worker_threads');
const fs = require('node:fs');
const flags = new Int32Array(workerData.flags);
let record = workerData.record;
parentPort.on('message', value => {record = value;});
const timer = setInterval(() => {
  if (Atomics.compareExchange(flags, 1, 0, 1) !== 0) return;
  try {
    if (Atomics.load(flags, 0)) {clearInterval(timer); return;}
    const temporary = workerData.file + '.heartbeat-' + process.pid;
    fs.writeFileSync(temporary, JSON.stringify({...record, updated_at: new Date().toISOString()}) + '\\n');
    fs.renameSync(temporary, workerData.file);
  } catch (error) {
    parentPort.postMessage({error: String(error)});
    clearInterval(timer);
  } finally {
    Atomics.store(flags, 1, 0); Atomics.notify(flags, 1);
  }
}, workerData.interval);
`;

function __vfCreateFileObservation(options, initial, interval) {
  const runDir = __vfPath.resolve(options.runDir ?? __vfPath.join("runs", new Date().toISOString().replace(/[:.]/g, "-") + "_" + __vfUuid()));
  const file = __vfPath.resolve(options.statusFile ?? __vfPath.join(runDir, "status.json"));
  __vfFs.mkdirSync(runDir, {recursive: true});
  __vfFs.mkdirSync(__vfPath.dirname(file), {recursive: true});
  const businessFd = __vfFs.openSync(__vfPath.join(runDir, "business.log"), "w");
  const kernelFd = __vfFs.openSync(__vfPath.join(runDir, "vibeflow.log"), "w");
  const flags = new Int32Array(new SharedArrayBuffer(8));
  let worker;
  let heartbeatError;
  let closed = false;
  const storage = __vfConsoleStorage();
  function write(record) {
    if (heartbeatError) throw heartbeatError;
    while (Atomics.compareExchange(flags, 1, 0, 1) !== 0) Atomics.wait(flags, 1, 1, 100);
    const temporary = file + ".main-" + process.pid + "-" + __vfUuid();
    try {
      __vfFs.writeFileSync(temporary, JSON.stringify(record) + "\n");
      __vfFs.renameSync(temporary, file);
    } finally {
      if (__vfFs.existsSync(temporary)) __vfFs.unlinkSync(temporary);
      Atomics.store(flags, 1, 0); Atomics.notify(flags, 1);
    }
  }
  const sink = {
    business(chunk) { if (!closed) __vfFs.writeSync(businessFd, typeof chunk === "string" ? chunk : Buffer.from(chunk)); },
    kernel(text) { if (!closed) __vfFs.writeSync(kernelFd, text + "\n"); },
    run(callback) { return storage.run(sink, callback); },
    cache(record) { worker?.postMessage(record); },
    publish(record) {
      sink.kernel("STATE " + record.state);
      write(record);
      worker?.postMessage(record);
    },
    finish(record) {
      Atomics.store(flags, 0, 1);
      sink.publish(record);
    },
    close() {
      if (closed) return;
      closed = true;
      Atomics.store(flags, 0, 1);
      worker?.terminate();
      __vfFs.closeSync(businessFd); __vfFs.closeSync(kernelFd);
    },
  };
  try {
    write(initial);
    worker = new __vfStatusWorker(__vfHeartbeatSource, {eval: true, workerData: {
      record: initial, file, interval, flags: flags.buffer,
    }});
    worker.on("message", message => { if (message.error) heartbeatError = new Error(message.error); });
    worker.on("error", error => {heartbeatError = error;});
    worker.unref();
    return sink;
  } catch (error) {
    sink.close(); throw error;
  }
}
