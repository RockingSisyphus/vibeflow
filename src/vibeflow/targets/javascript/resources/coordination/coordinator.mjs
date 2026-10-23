// Explicit in-process scope, shared by Node and browser hosts.
import {WorkflowCoordinationError, portable, errorRecord} from './workflow_client.mjs';
import {terminalStates} from './contracts.mjs';
const terminal = new Set(terminalStates);
const key = ref => JSON.stringify([ref.root || '', ref.path]);
const same = (a, b) => key(a) === key(b) && (a.entry || '') === (b.entry || '');
const fail = (code, message) => {throw new WorkflowCoordinationError(code, message);};
const id = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
const pending = value => value && typeof value.then === 'function';
function reference(value, root = '') {
  if (!value || Object.keys(value).some(k => !['root', 'path', 'entry'].includes(k)) ||
      typeof value.path !== 'string' || !value.path || /^[\\/]/.test(value.path) || value.path.includes(':'))
    fail('VF_WORKFLOW_REFERENCE', 'workflow requires a relative path');
  const parts = [];
  for (const part of value.path.replaceAll('\\', '/').split('/')) {
    if (part === '..') {if (!parts.length) fail('VF_WORKFLOW_REFERENCE', 'path leaves its root'); parts.pop();}
    else if (part && part !== '.') parts.push(part);
  }
  if (value.entry !== undefined && (typeof value.entry !== 'string' || !value.entry.trim()))
    fail('VF_WORKFLOW_ENTRY', 'entry must name an entry');
  return {root: value.root || root, path: parts.join('/') || '.', ...(value.entry ? {entry: value.entry} : {})};
}
export class Coordinator {
  constructor() {this.bindings = new Map(); this.instances = new Map(); this.closed = false;}
  bind(descriptor, runner) {
    descriptor = portable(descriptor);
    if (!['sync', 'async'].includes(descriptor.entry_mode) || typeof runner !== 'function')
      fail('VF_WORKFLOW_DESCRIPTOR', 'descriptor requires entry_mode and an execution method');
    descriptor.workflow = reference(descriptor.workflow);
    const name = key(descriptor.workflow);
    if (this.bindings.has(name)) fail('VF_WORKFLOW_BOUND', name);
    this.bindings.set(name, {descriptor, runner});
    return this;
  }
  target(ref) {
    ref = reference(ref);
    const binding = this.bindings.get(key(ref));
    if (!binding) fail('VF_WORKFLOW_UNBOUND', JSON.stringify(ref));
    const entries = Object.keys(binding.descriptor.entries || {});
    const entry = ref.entry ?? (binding.descriptor.default_entry || undefined) ?? (entries.length === 1 ? entries[0] : undefined);
    if (entries.length && !entries.includes(entry) || !entries.length && entry !== undefined)
      fail('VF_WORKFLOW_ENTRY', 'select a declared workflow entry');
    return {...binding, entry, reference: ref};
  }
  instance(identifier) {
    const item = this.instances.get(identifier);
    if (!item) fail('VF_INSTANCE_UNKNOWN', identifier);
    return item;
  }
  status(item) {return portable(Object.fromEntries(['id', 'state', 'outputs', 'error', 'workflow', 'entry'].map(k => [k, item[k]])));}
  notify(item) {for (const wake of [...item.waiters]) wake();}
  register(workflow) {
    if (this.closed) fail('VF_SCOPE_CLOSED', 'coordinator is closed');
    const item = {id: id(), state: 'running', outputs: null, error: null, workflow: reference(workflow), entry: workflow.entry ?? null,
      mailboxes: new Map(), waiters: new Set(), controller: new AbortController(), task: null};
    this.instances.set(item.id, item);
    return item;
  }
  declared(owner, ref, operation, launch) {
    const binding = owner && this.bindings.get(key(owner.workflow));
    if (binding && !binding.descriptor.calls?.some(a => a.operation === operation && same(a.workflow, ref) &&
        (operation !== 'call' || a.launch?.kind === launch.kind)))
      fail(operation === 'call' ? 'VF_LAUNCH_UNDECLARED' : 'VF_WORKFLOW_UNDECLARED', `${operation} target was not declared`);
  }
  invoke_sync(request, sender) {
    if (this.closed) fail('VF_SCOPE_CLOSED', 'coordinator is closed');
    const owner = sender ? this.instance(sender) : null;
    const ref = reference(request.workflow, owner?.workflow.root);
    this.declared(owner, ref, 'invoke_sync');
    const {descriptor, runner, entry} = this.target(ref);
    if (descriptor.entry_mode !== 'sync') fail('VF_WORKFLOW_SYNC_UNSUPPORTED', JSON.stringify(ref));
    const item = this.register(ref);
    try {
      const result = runner(portable(request.inputs || {}), {entry, workflowInstanceId: item.id,
        capabilities: {'vibeflow.workflow': this.operations(item.id)}});
      if (pending(result)) fail('VF_COMPLETION_MISMATCH', 'synchronous target returned pending work');
      return portable(result);
    } catch (error) {
      if (error && typeof error === 'object')
        (error.workflowCalls ||= []).push({id:item.id, workflow:ref, entry:entry ?? null});
      throw error;
    } finally {this.instances.delete(item.id);}
  }
  start(item, binding, inputs) {
    const {descriptor, runner, entry} = binding;
    item.task = Promise.resolve().then(async () => {
      try {
        item.controller.signal.throwIfAborted();
        const result = runner(portable(inputs), {entry, workflowInstanceId: item.id, signal: item.controller.signal,
          capabilities: {'vibeflow.workflow': this.operations(item.id)}});
        if (descriptor.entry_mode === 'sync' && pending(result)) fail('VF_COMPLETION_MISMATCH', 'sync target returned pending work');
        item.outputs = portable(await result);
        item.state = 'succeeded';
      } catch (error) {
        item.state = item.controller.signal.aborted || error?.code === 'VF_ABORTED' || error?.name === 'AbortError' ? 'cancelled' : 'failed';
        item.error = errorRecord(error);
      } finally {this.notify(item);}
    });
  }
  async run(ref, inputs = {}) {
    const binding = this.target(ref), item = this.register(binding.reference);
    this.start(item, binding, inputs);
    await item.task;
    return this.status(item);
  }
  async call(sender, request, {signal} = {}) {
    signal?.throwIfAborted();
    const owner = this.instance(sender), ref = reference(request.workflow, owner.workflow.root);
    if (request.launch?.kind !== 'in_process' || Object.keys(request.launch).length !== 1)
      fail('VF_LAUNCH_UNSUPPORTED', 'in-process host requires launch.kind in_process');
    this.declared(owner, ref, 'call', request.launch);
    const binding = this.target(ref), inputs = portable(request.inputs || {}), item = this.register(ref);
    this.start(item, binding, inputs);
    return {id: item.id};
  }
  send(sender, request) {
    this.instance(sender);
    const item = this.instance(request.id);
    if (terminal.has(item.state)) fail('VF_INSTANCE_ENDED', item.id);
    const port = request.port || 'default', queue = item.mailboxes.get(port) || [];
    queue.push(portable({sender, port, payload: request.payload}));
    item.mailboxes.set(port, queue);
    this.notify(item);
    return null;
  }
  async poll(operation, identifier, request = {}, {signal} = {}) {
    const item = this.instance(identifier), deadline = request.timeout == null ? Infinity : Date.now() + request.timeout * 1000;
    while (true) {
      if (this.closed) fail('VF_SCOPE_CLOSED', 'coordinator is closed');
      signal?.throwIfAborted();
      if (operation === 'wait' && terminal.has(item.state)) return this.status(item);
      if (operation === 'receive') {
        const queue = item.mailboxes.get(request.port || 'default');
        if (queue?.length) return queue.shift();
        if (terminal.has(item.state)) fail('VF_INSTANCE_ENDED', item.id);
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) fail('VF_WAIT_TIMEOUT', item.id);
      await new Promise((resolve, reject) => {
        let timer;
        const cleanup = () => {item.waiters.delete(wake); signal?.removeEventListener('abort', abort); if (timer) clearTimeout(timer);};
        const wake = () => {cleanup(); resolve();};
        const abort = () => {cleanup(); reject(signal.reason);};
        item.waiters.add(wake);
        signal?.addEventListener('abort', abort, {once: true});
        if (signal?.aborted) abort();
        else if (Number.isFinite(remaining)) timer = setTimeout(wake, remaining);
      });
    }
  }
  async kill(request, context) {
    const item = this.instance(request.id);
    if (key(reference(request.workflow)) !== key(item.workflow)) fail('VF_WORKFLOW_MISMATCH', item.id);
    if (!terminal.has(item.state)) {
      if (!item.task) fail('VF_STOP_UNSUPPORTED', item.id);
      item.state = 'stopping';
      item.controller.abort(new DOMException('workflow stop requested', 'AbortError'));
    }
    return this.poll('wait', item.id, request, context);
  }
  operations(identifier) {
    return Object.freeze({invoke_sync: request => this.invoke_sync(request, identifier),
      call: (request, context) => this.call(identifier, request, context), send: request => this.send(identifier, request),
      receive: (request, context) => this.poll('receive', identifier, request, context),
      wait: (request, context) => this.poll('wait', request.id, request, context),
      kill: (request, context) => this.kill({...request, workflow: reference(request.workflow, this.instance(identifier).workflow.root)}, context)});
  }
  release(identifier) {
    const item = this.instance(identifier);
    if (!terminal.has(item.state)) fail('VF_INSTANCE_RUNNING', identifier);
    this.instances.delete(identifier);
  }
  async close() {
    this.closed = true;
    for (const item of this.instances.values()) {
      this.notify(item);
      if (item.task && !terminal.has(item.state)) {
        item.state = 'stopping'; item.controller.abort(new DOMException('scope closed', 'AbortError'));
      }
    }
    await Promise.all([...this.instances.values()].map(item => item.task));
    this.instances.clear();
  }
}
