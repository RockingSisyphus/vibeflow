export const VIBEFLOW_WORKFLOW_ABI = "vibeflow.workflow.v2";
export const VIBEFLOW_PLUGIN_ABI = "vibeflow.plugin.v1";

export class VibeFlowWorkflowError extends Error {
  constructor(code, message, details = {}) {
    const options = details.cause === undefined ? undefined : { cause: details.cause };
    super(message, options);
    this.name = "VibeFlowWorkflowError";
    this.code = code;
    this.workflowId = details.workflowId || "";
    this.nodePath = details.nodePath || "";
    this.blockPath = details.blockPath || "";
  }
}

function vfError(code, message, workflow, details = {}) {
  return new VibeFlowWorkflowError(code, message, {
    workflowId: workflow.workflow_id,
    ...details,
  });
}

function throwIfAborted(signal, workflow, nodePath = "", blockPath = "") {
  if (!signal?.aborted) return;
  throw vfError("VF_ABORTED", "workflow execution was aborted", workflow, {
    nodePath,
    blockPath,
    cause: signal.reason,
  });
}

async function awaitWithAbort(value, signal, workflow, nodePath = "", blockPath = "") {
  throwIfAborted(signal, workflow, nodePath, blockPath);
  if (!signal) return await value;
  let onAbort;
  const aborted = new Promise((_, reject) => {
    onAbort = () => reject(vfError(
      "VF_ABORTED",
      "workflow execution was aborted",
      workflow,
      { nodePath, blockPath, cause: signal.reason },
    ));
    signal.addEventListener("abort", onAbort, { once: true });
  });
  try {
    return await Promise.race([Promise.resolve(value), aborted]);
  } finally {
    signal.removeEventListener("abort", onAbort);
  }
}

function assertObject(value, code, message, workflow) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw vfError(code, message, workflow);
  }
}

function dictionary() {
  return Object.create(null);
}

function setOwn(target, key, value) {
  Object.defineProperty(target, key, {
    value,
    enumerable: true,
    configurable: true,
    writable: true,
  });
  return target;
}

function validateJsonSchema(value, schema, path = "$") {
  if (!schema || typeof schema !== "object") return "";
  if (Array.isArray(schema.enum) && !schema.enum.some((item) => jsonEquals(item, value))) {
    return `${path} is not one of the allowed values`;
  }
  if (Object.prototype.hasOwnProperty.call(schema, "const") && !jsonEquals(schema.const, value)) {
    return `${path} does not equal the required constant`;
  }
  if (Array.isArray(schema.allOf)) {
    for (const child of schema.allOf) {
      const failure = validateJsonSchema(value, child, path);
      if (failure) return failure;
    }
  }
  if (Array.isArray(schema.anyOf)) {
    if (!schema.anyOf.some((child) => !validateJsonSchema(value, child, path))) {
      return `${path} does not match any allowed schema`;
    }
  }
  if (Array.isArray(schema.oneOf)) {
    const matches = schema.oneOf.filter((child) => !validateJsonSchema(value, child, path)).length;
    if (matches !== 1) return `${path} must match exactly one allowed schema`;
  }
  const allowedTypes = Array.isArray(schema.type)
    ? schema.type
    : schema.type ? [schema.type] : [];
  if (allowedTypes.length && !allowedTypes.some((type) => jsonTypeMatches(value, type))) {
    return `${path} has type ${jsonType(value)}, expected ${allowedTypes.join(" or ")}`;
  }
  if (typeof value === "string") {
    const length = [...value].length;
    if (Number.isInteger(schema.minLength) && length < schema.minLength) {
      return `${path} is shorter than minLength=${schema.minLength}`;
    }
    if (Number.isInteger(schema.maxLength) && length > schema.maxLength) {
      return `${path} is longer than maxLength=${schema.maxLength}`;
    }
    if (typeof schema.pattern === "string"
        && !(new RegExp(schema.pattern)).test(value)) {
      return `${path} does not match pattern`;
    }
  }
  if (typeof value === "number") {
    if (typeof schema.minimum === "number" && value < schema.minimum) {
      return `${path} is less than minimum=${schema.minimum}`;
    }
    if (typeof schema.maximum === "number" && value > schema.maximum) {
      return `${path} is greater than maximum=${schema.maximum}`;
    }
  }
  if (Array.isArray(value)) {
    if (Number.isInteger(schema.minItems) && value.length < schema.minItems) {
      return `${path} has fewer than minItems=${schema.minItems}`;
    }
    if (Number.isInteger(schema.maxItems) && value.length > schema.maxItems) {
      return `${path} has more than maxItems=${schema.maxItems}`;
    }
    if (schema.items && typeof schema.items === "object") {
      for (let index = 0; index < value.length; index += 1) {
        const failure = validateJsonSchema(value[index], schema.items, `${path}[${index}]`);
        if (failure) return failure;
      }
    }
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const properties = schema.properties && typeof schema.properties === "object"
      ? schema.properties : {};
    if (Array.isArray(schema.required)) {
      for (const key of schema.required) {
        if (!Object.prototype.hasOwnProperty.call(value, key)) {
          return `${path}.${key} is required`;
        }
      }
    }
    for (const [key, childValue] of Object.entries(value)) {
      if (Object.prototype.hasOwnProperty.call(properties, key)) {
        const failure = validateJsonSchema(childValue, properties[key], `${path}.${key}`);
        if (failure) return failure;
      } else if (schema.additionalProperties === false) {
        return `${path}.${key} is not allowed`;
      } else if (schema.additionalProperties && typeof schema.additionalProperties === "object") {
        const failure = validateJsonSchema(childValue, schema.additionalProperties, `${path}.${key}`);
        if (failure) return failure;
      }
    }
  }
  return "";
}

function jsonEquals(left, right) {
  if (left === right) return true;
  if (left === null || right === null || typeof left !== typeof right) return false;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left)
      && Array.isArray(right)
      && left.length === right.length
      && left.every((item, index) => jsonEquals(item, right[index]));
  }
  if (typeof left !== "object") return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) =>
      key === rightKeys[index] && jsonEquals(left[key], right[key])
    );
}

function jsonTypeMatches(value, expected) {
  if (expected === "null") return value === null;
  if (expected === "array") return Array.isArray(value);
  if (expected === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
  if (expected === "integer") return Number.isInteger(value);
  if (expected === "number") return typeof value === "number" && Number.isFinite(value);
  return typeof value === expected;
}

function jsonType(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
}

function formatBlockPath(path) {
  if (!path.length) return "/";
  const segments = path.map((item) => String(item).replaceAll("~", "~0").replaceAll("/", "~1"));
  return `/${segments.join("/")}`;
}

function nodePath(state, nodeId) {
  return [...state.path, nodeId].join(".");
}

function ensureErrorLocation(cause, workflow, path, nodeId = "") {
  const failure = cause instanceof VibeFlowWorkflowError
    ? cause
    : vfError("VF_INTERNAL", "generated workflow failed internally", workflow, { cause });
  if (!failure.nodePath && nodeId) failure.nodePath = [...path, nodeId].join(".");
  if (!failure.blockPath) failure.blockPath = formatBlockPath(path);
  return failure;
}

function emitTrace(root, kind, details = {}, boundary = false) {
  if (root.traceMode === "off") return;
  if (root.traceMode !== "full" && !boundary) return;
  const event = Object.freeze({
    kind,
    workflowId: root.workflowId,
    ...details,
  });
  if (!root.onTrace) return;
  try {
    root.onTrace(event);
  } catch (cause) {
    throw vfError(
      "VF_TRACE_SINK_FAILED",
      `trace callback failed during '${kind}'`,
      root.workflow,
      { cause },
    );
  }
}

function normalizeOptions(workflow, options) {
  const raw = options === undefined ? {} : options;
  assertObject(raw, "VF_INTERNAL", "workflow options must be an object", workflow);
  const traceMode = raw.trace ?? "boundary";
  if (!["off", "boundary", "full"].includes(traceMode)) {
    throw vfError("VF_INTERNAL", `unsupported trace mode '${String(traceMode)}'`, workflow);
  }
  if (raw.onTrace !== undefined && typeof raw.onTrace !== "function") {
    throw vfError("VF_INTERNAL", "options.onTrace must be a function", workflow);
  }
  const detachedTimeoutMs = raw.detachedTimeoutMs ?? 5000;
  if (!Number.isFinite(detachedTimeoutMs) || detachedTimeoutMs < 0) {
    throw vfError("VF_INTERNAL", "options.detachedTimeoutMs must be a non-negative number", workflow);
  }
  return {
    signal: raw.signal,
    traceMode,
    onTrace: raw.onTrace,
    capabilities: raw.capabilities ?? {},
    detachedTimeoutMs,
  };
}

function capabilityLocation(caller) {
  return {
    nodePath: typeof caller?.nodePath === "string" ? caller.nodePath : "",
    blockPath: typeof caller?.blockPath === "string" ? caller.blockPath : "",
  };
}

function validateCapabilityInput(
  workflow,
  schemas,
  capabilityId,
  operationName,
  operationDescriptor,
  input,
  location,
) {
  const failure = validateJsonSchema(
    input,
    operationDescriptor.input_type ? schemas[operationDescriptor.input_type] : undefined,
  );
  if (failure) {
    throw vfError(
      "VF_CAPABILITY_INPUT",
      `capability '${capabilityId}.${operationName}' input failed schema validation: ${failure}`,
      workflow,
      location,
    );
  }
}

function validateCapabilityOutput(
  workflow,
  schemas,
  capabilityId,
  operationName,
  operationDescriptor,
  output,
  location,
) {
  const failure = validateJsonSchema(
    output,
    operationDescriptor.output_type ? schemas[operationDescriptor.output_type] : undefined,
  );
  if (failure) {
    throw vfError(
      "VF_CAPABILITY_OUTPUT",
      `capability '${capabilityId}.${operationName}' output failed schema validation: ${failure}`,
      workflow,
      location,
    );
  }
  return output;
}

function wrapCapabilityFailure(
  cause,
  workflow,
  root,
  capabilityId,
  operationName,
  location,
) {
  if (cause instanceof VibeFlowWorkflowError) throw cause;
  if (root.signal?.aborted) {
    throwIfAborted(root.signal, workflow, location.nodePath, location.blockPath);
  }
  throw vfError(
    "VF_CAPABILITY_FAILED",
    `capability '${capabilityId}.${operationName}' failed`,
    workflow,
    { ...location, cause },
  );
}

function prepareCapabilities(workflow, descriptors, requirements, schemas, supplied, root, entryMode) {
  assertObject(
    supplied,
    "VF_CAPABILITY_MISSING",
    "options.capabilities must be an object",
    workflow,
  );
  const wrapped = dictionary();
  for (const [capabilityId, operationNames] of Object.entries(requirements)) {
    const implementation = Object.prototype.hasOwnProperty.call(supplied, capabilityId)
      ? supplied[capabilityId]
      : undefined;
    if (!implementation || typeof implementation !== "object") {
      throw vfError(
        "VF_CAPABILITY_MISSING",
        `required capability '${capabilityId}' was not supplied`,
        workflow,
      );
    }
    const descriptor = descriptors[capabilityId] || {};
    const capability = dictionary();
    for (const operationName of operationNames) {
      const callable = implementation[operationName];
      if (typeof callable !== "function") {
        throw vfError(
          "VF_CAPABILITY_MISSING",
          `capability '${capabilityId}' is missing operation '${operationName}'`,
          workflow,
        );
      }
      const operationDescriptor = descriptor.operations?.[operationName] || {};
      const completion = operationDescriptor.completion || "immediate";
      if (entryMode === "sync" && completion === "suspend") {
        throw vfError(
          "VF_CAPABILITY_MISSING",
          `sync workflow cannot use suspending capability '${capabilityId}.${operationName}'`,
          workflow,
        );
      }
      if (completion === "suspend") {
        setOwn(capability, operationName, async (input, caller = {}) => {
          const location = capabilityLocation(caller);
          throwIfAborted(root.signal, workflow, location.nodePath, location.blockPath);
          validateCapabilityInput(
            workflow,
            schemas,
            capabilityId,
            operationName,
            operationDescriptor,
            input,
            location,
          );
          try {
            const output = await awaitWithAbort(
              callable.call(implementation, input, { signal: root.signal }),
              root.signal,
              workflow,
              location.nodePath,
              location.blockPath,
            );
            return validateCapabilityOutput(
              workflow,
              schemas,
              capabilityId,
              operationName,
              operationDescriptor,
              output,
              location,
            );
          } catch (cause) {
            return wrapCapabilityFailure(
              cause,
              workflow,
              root,
              capabilityId,
              operationName,
              location,
            );
          }
        });
      } else {
        setOwn(capability, operationName, (input, caller = {}) => {
          const location = capabilityLocation(caller);
          throwIfAborted(root.signal, workflow, location.nodePath, location.blockPath);
          validateCapabilityInput(
            workflow,
            schemas,
            capabilityId,
            operationName,
            operationDescriptor,
            input,
            location,
          );
          try {
            const output = callable.call(
              implementation,
              input,
              { signal: root.signal },
            );
            return validateCapabilityOutput(
              workflow,
              schemas,
              capabilityId,
              operationName,
              operationDescriptor,
              output,
              location,
            );
          } catch (cause) {
            return wrapCapabilityFailure(
              cause,
              workflow,
              root,
              capabilityId,
              operationName,
              location,
            );
          }
        });
      }
    }
    setOwn(wrapped, capabilityId, Object.freeze(capability));
  }
  return Object.freeze(wrapped);
}

function validatePublicInputs(workflow, inputs) {
  assertObject(inputs, "VF_INPUT_SCHEMA", "workflow inputs must be an object", workflow);
  const known = new Set(workflow.inputs.map((item) => item.key));
  for (const key of Object.keys(inputs)) {
    if (!known.has(key)) {
      throw vfError("VF_INPUT_UNKNOWN", `unknown workflow input '${key}'`, workflow);
    }
  }
  for (const input of workflow.inputs) {
    const present = Object.prototype.hasOwnProperty.call(inputs, input.key);
    if (input.required && !present) {
      throw vfError("VF_INPUT_REQUIRED", `required workflow input '${input.key}' is missing`, workflow);
    }
    if (!present) continue;
    const failure = validateJsonSchema(
      inputs[input.key],
      input.schema || workflow.schemas?.[input.type],
    );
    if (failure) {
      throw vfError(
        "VF_INPUT_SCHEMA",
        `workflow input '${input.key}' failed schema validation: ${failure}`,
        workflow,
      );
    }
  }
}

function createEnvelope(key, type, value, sourceNode) {
  return Object.freeze({ key, type, value, source_node: sourceNode });
}

function createStaticState(workflow, initial, root, path) {
  validatePublicInputs(workflow, initial);
  return {
    workflow,
    root,
    path,
    inboxes: dictionary(),
    candidates: new Map(),
    activeEdges: new Set(),
    lastInputs: new Map(),
    pending: new Map(),
    nodeRuns: new Map(),
    stepCount: 0,
    initial,
  };
}

function initializeInbox(state, nodeId) {
  setOwn(state.inboxes, nodeId, []);
}

function seedInbox(state, nodeId, acceptedTypes) {
  const accepted = new Set(acceptedTypes);
  for (const input of state.workflow.inputs) {
    if (!accepted.has(input.type)) continue;
    if (!Object.prototype.hasOwnProperty.call(state.initial, input.key)) continue;
    state.inboxes[nodeId].push(
      createEnvelope(input.key, input.type, state.initial[input.key], "pipeline.input"),
    );
  }
}

function requirementsFromInbox(node, state) {
  const inputs = dictionary();
  for (const requirement of node.requires) {
    const matches = state.inboxes[node.id].filter((item) => item.type === requirement.type);
    if (requirement.cardinality === "exactly_one") {
      if (matches.length !== 1) {
        throw vfError(
          "VF_OUTPUT_CARDINALITY",
          `node '${node.id}' requires type '${requirement.type}' exactly once, got ${matches.length}`,
          state.workflow,
          { nodePath: nodePath(state, node.id) },
        );
      }
      setOwn(inputs, requirement.type, matches[0]);
    } else if (requirement.cardinality === "optional_one") {
      if (matches.length > 1) {
        throw vfError(
          "VF_OUTPUT_CARDINALITY",
          `node '${node.id}' requires type '${requirement.type}' at most once, got ${matches.length}`,
          state.workflow,
          { nodePath: nodePath(state, node.id) },
        );
      }
      setOwn(inputs, requirement.type, matches[0] ?? null);
    } else {
      setOwn(inputs, requirement.type, [...matches]);
    }
  }
  return inputs;
}

function conditionValues(inputs, outputs) {
  const values = dictionary();
  for (const value of Object.values(inputs)) {
    const items = Array.isArray(value) ? value : [value];
    for (const item of items) {
      if (item && typeof item === "object" && "key" in item) {
        setOwn(values, item.key, item.value);
      }
    }
  }
  for (const [key, value] of Object.entries(outputs)) setOwn(values, key, value);
  return values;
}

function conditionMatches(condition, values) {
  if (!condition) return true;
  const equal = Object.is(values[condition.key], condition.literal);
  return condition.operator === "==" ? equal : !equal;
}

function recordCandidate(state, envelope) {
  if (!state.workflow.outputs.some((output) => output.type === envelope.type)) return;
  const candidates = state.candidates.get(envelope.type) || [];
  const index = candidates.findIndex(
    (item) => item.key === envelope.key
      && item.type === envelope.type
      && item.source_node === envelope.source_node,
  );
  if (index >= 0) candidates[index] = envelope;
  else candidates.push(envelope);
  state.candidates.set(envelope.type, candidates);
}

function validateNodeOutputs(node, outputs, state) {
  if (!outputs || typeof outputs !== "object" || Array.isArray(outputs)) {
    throw vfError(
      "VF_OUTPUT_KEYS",
      `node '${node.id}' must return an object`,
      state.workflow,
      { nodePath: nodePath(state, node.id) },
    );
  }
  const expected = node.provides.map((item) => item.key).sort();
  const actual = Object.keys(outputs).sort();
  if (expected.length !== actual.length
      || expected.some((key, index) => key !== actual[index])) {
    throw vfError(
      "VF_OUTPUT_KEYS",
      `node '${node.id}' output keys must exactly match provides: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
      state.workflow,
      { nodePath: nodePath(state, node.id) },
    );
  }
  for (const provider of node.provides) {
    const schemas = [
      ["node contract", node.output_schemas?.[provider.key]],
      ["data type", state.workflow.schemas?.[provider.type]],
    ];
    for (const [schemaKind, schema] of schemas) {
      const failure = validateJsonSchema(outputs[provider.key], schema);
      if (failure) {
        throw vfError(
          "VF_OUTPUT_SCHEMA",
          `node '${node.id}' output '${provider.key}' failed ${schemaKind} schema validation: ${failure}`,
          state.workflow,
          { nodePath: nodePath(state, node.id) },
        );
      }
    }
  }
  return outputs;
}

function outputEnvelopes(node, outputs) {
  return node.provides.map((provider) =>
    createEnvelope(provider.key, provider.type, outputs[provider.key], node.id)
  );
}

function deliverStatic(envelopes, state, targetId, acceptedTypes) {
  const accepted = new Set(acceptedTypes);
  for (const envelope of envelopes) {
    if (!accepted.has(envelope.type)) continue;
    state.inboxes[targetId] = state.inboxes[targetId].filter(
      (item) => !(item.key === envelope.key
        && item.type === envelope.type
        && item.source_node === envelope.source_node),
    );
    state.inboxes[targetId].push(envelope);
  }
}

function nodeContext(node, state) {
  const allowed = dictionary();
  for (const requirement of node.capabilities || []) {
    const capability = state.root.capabilities[requirement.id];
    if (!capability) continue;
    const contextual = dictionary();
    const requested = new Set(requirement.operations || []);
    for (const [operationName, operation] of Object.entries(capability)) {
      if (requested.size && !requested.has(operationName)) continue;
      setOwn(contextual, operationName, (input) => operation(input, {
        nodePath: nodePath(state, node.id),
        blockPath: formatBlockPath(state.path),
      }));
    }
    setOwn(allowed, requirement.id, Object.freeze(contextual));
  }
  return Object.freeze({
    signal: state.root.signal,
    capabilities: Object.freeze(allowed),
    trace(kind, details = {}) {
      emitTrace(state.root, "node_trace", {
        nodeId: node.id,
        nodePath: nodePath(state, node.id),
        event: String(kind),
        details,
      });
    },
  });
}

function invokeStaticImplementationSync(implementation, node, inputs, state) {
  if (typeof implementation !== "function") {
    throw vfError(
      "VF_INTERNAL",
      `node '${node.id}' has no emitted implementation binding`,
      state.workflow,
      { nodePath: nodePath(state, node.id) },
    );
  }
  try {
    const outputs = implementation(inputs, node.params, nodeContext(node, state));
    throwIfAborted(state.root.signal, state.workflow, nodePath(state, node.id));
    return validateNodeOutputs(node, outputs, state);
  } catch (cause) {
    if (cause instanceof VibeFlowWorkflowError) {
      throw ensureErrorLocation(cause, state.workflow, state.path, node.id);
    }
    if (state.root.signal?.aborted) {
      throwIfAborted(state.root.signal, state.workflow, nodePath(state, node.id));
    }
    throw vfError(
      "VF_NODE_FAILED",
      `node '${node.id}' failed`,
      state.workflow,
      { nodePath: nodePath(state, node.id), cause },
    );
  }
}

async function invokeStaticImplementationAsync(implementation, node, inputs, state) {
  if (typeof implementation !== "function") {
    throw vfError(
      "VF_INTERNAL",
      `node '${node.id}' has no emitted implementation binding`,
      state.workflow,
      { nodePath: nodePath(state, node.id) },
    );
  }
  try {
    const outputs = await awaitWithAbort(
      Promise.resolve().then(() =>
        implementation(inputs, node.params, nodeContext(node, state))
      ),
      state.root.signal,
      state.workflow,
      nodePath(state, node.id),
      formatBlockPath(state.path),
    );
    throwIfAborted(state.root.signal, state.workflow, nodePath(state, node.id));
    return validateNodeOutputs(node, outputs, state);
  } catch (cause) {
    if (cause instanceof VibeFlowWorkflowError) {
      throw ensureErrorLocation(cause, state.workflow, state.path, node.id);
    }
    if (state.root.signal?.aborted) {
      throwIfAborted(
        state.root.signal,
        state.workflow,
        nodePath(state, node.id),
        formatBlockPath(state.path),
      );
    }
    throw vfError(
      "VF_NODE_FAILED",
      `node '${node.id}' failed`,
      state.workflow,
      {
        nodePath: nodePath(state, node.id),
        blockPath: formatBlockPath(state.path),
        cause,
      },
    );
  }
}

function prepareStaticNode(node, state) {
  throwIfAborted(state.root.signal, state.workflow, nodePath(state, node.id));
  const inputs = requirementsFromInbox(node, state);
  state.lastInputs.set(node.id, inputs);
  state.inboxes[node.id] = [];
  state.nodeRuns.set(node.id, (state.nodeRuns.get(node.id) || 0) + 1);
  emitTrace(state.root, "node_start", {
    nodeId: node.id,
    nodePath: nodePath(state, node.id),
    blockPath: formatBlockPath(state.path),
    type: node.type_used,
  });
  return inputs;
}

function finishStaticNode(node, state) {
  emitTrace(state.root, "node_end", {
    nodeId: node.id,
    nodePath: nodePath(state, node.id),
    blockPath: formatBlockPath(state.path),
    type: node.type_used,
  });
}

async function joinStaticPending(node, state, activate) {
  if (!state.pending.has(node.id)) return;
  const pending = state.pending.get(node.id);
  state.pending.delete(node.id);
  let outputs;
  try {
    outputs = await awaitWithAbort(
      pending,
      state.root.signal,
      state.workflow,
      nodePath(state, node.id),
      formatBlockPath(state.path),
    );
  } catch (cause) {
    if (cause instanceof VibeFlowWorkflowError) throw cause;
    if (state.root.signal?.aborted) {
      throwIfAborted(
        state.root.signal,
        state.workflow,
        nodePath(state, node.id),
        formatBlockPath(state.path),
      );
    }
    throw vfError(
      "VF_NODE_FAILED",
      `async node '${node.id}' failed`,
      state.workflow,
      {
        nodePath: nodePath(state, node.id),
        blockPath: formatBlockPath(state.path),
        cause,
      },
    );
  }
  const inputs = state.lastInputs.get(node.id) || dictionary();
  activate(outputs, inputs, state, false);
  emitTrace(state.root, "async_result_join", {
    nodeId: node.id,
    nodePath: nodePath(state, node.id),
    blockPath: formatBlockPath(state.path),
  });
}

function enqueueStaticTargets(targets, ready, queued) {
  for (const target of targets) {
    if (queued.has(target)) continue;
    ready.push(target);
    queued.add(target);
  }
}

function rawInputsForChild(inputSpecs, inputs, workflow, nodeId) {
  const items = [];
  for (const value of Object.values(inputs)) {
    if (Array.isArray(value)) items.push(...value);
    else if (value) items.push(value);
  }
  const initial = dictionary();
  for (const input of inputSpecs) {
    const match = items.find((item) => item?.type === input.type);
    if (match) setOwn(initial, input.key, match.value);
    else if (input.required) {
      throw vfError(
        "VF_INPUT_REQUIRED",
        `composite node '${nodeId}' cannot supply required body input '${input.key}'`,
        workflow,
      );
    }
  }
  return initial;
}

function outputsFromChild(node, mappings, childResult, state) {
  const outputs = dictionary();
  for (const mapping of mappings) {
    if (!Object.prototype.hasOwnProperty.call(childResult.publicOutputs, mapping.alias)) {
      throw vfError(
        "VF_OUTPUT_CARDINALITY",
        `composite node '${node.id}' body omitted optional output '${mapping.alias}' required by provider '${mapping.provider}'`,
        state.workflow,
        { nodePath: nodePath(state, node.id) },
      );
    }
    setOwn(outputs, mapping.provider, childResult.publicOutputs[mapping.alias]);
  }
  return validateNodeOutputs(node, outputs, state);
}

function valueFromEnvelope(value) {
  if (value && typeof value === "object" && "value" in value && "type" in value) {
    return value.value;
  }
  return value;
}

function resultValues(child) {
  const values = dictionary();
  for (const [key, value] of Object.entries(child.publicOutputs)) setOwn(values, key, value);
  for (const [type, candidates] of child.candidates) {
    if (candidates.length === 1) setOwn(values, type, candidates[0].value);
  }
  return values;
}

function finalizeOutputs(state) {
  const output = {};
  for (const spec of state.workflow.outputs) {
    const matches = state.candidates.get(spec.type) || [];
    if (spec.cardinality === "exactly_one") {
      if (matches.length !== 1) {
        throw vfError(
          "VF_OUTPUT_CARDINALITY",
          `workflow output type '${spec.type}' expected exactly one value, got ${matches.length}`,
          state.workflow,
        );
      }
      setOwn(output, spec.as, matches[0].value);
    } else if (spec.cardinality === "optional_one") {
      if (matches.length > 1) {
        throw vfError(
          "VF_OUTPUT_CARDINALITY",
          `workflow output type '${spec.type}' expected at most one value, got ${matches.length}`,
          state.workflow,
        );
      }
      if (matches.length) setOwn(output, spec.as, matches[0].value);
    } else {
      setOwn(output, spec.as, matches.map((item) => item.value));
    }
    const schema = spec.schema || state.workflow.schemas?.[spec.type];
    const values = spec.cardinality === "all"
      ? matches.map((item) => item.value)
      : Object.prototype.hasOwnProperty.call(output, spec.as) ? [output[spec.as]] : [];
    for (const value of values) {
      const failure = validateJsonSchema(value, schema);
      if (failure) {
        throw vfError(
          "VF_OUTPUT_SCHEMA",
          `workflow output '${spec.as}' failed schema validation: ${failure}`,
          state.workflow,
        );
      }
    }
  }
  return output;
}

function abandonPending(state) {
  for (const [nodeId, promise] of state.pending) {
    promise.catch(() => {});
    emitTrace(state.root, "async_result_abandoned", {
      nodeId,
      nodePath: nodePath(state, nodeId),
      blockPath: formatBlockPath(state.path),
    });
  }
}

async function settleDetached(root) {
  const pending = [...root.detached];
  root.detached.clear();
  let firstFailure = root.detachedFailure;
  root.detachedFailure = null;
  for (const item of pending) {
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(vfError(
        "VF_ASYNC_FLUSH_TIMEOUT",
        `detached node '${item.node.id}' timed out after ${root.detachedTimeoutMs}ms`,
        item.workflow,
        { nodePath: item.nodePath, blockPath: item.blockPath },
      )), root.detachedTimeoutMs);
    });
    try {
      await Promise.race([item.promise, timeout]);
      emitTrace(root, "async_detached_done", {
        nodeId: item.node.id,
        nodePath: item.nodePath,
        blockPath: item.blockPath,
      });
    } catch (cause) {
      const failure = cause instanceof VibeFlowWorkflowError
        ? cause
        : vfError(
          "VF_NODE_FAILED",
          `detached node '${item.node.id}' failed`,
          item.workflow,
          { nodePath: item.nodePath, blockPath: item.blockPath, cause },
        );
      if (!firstFailure) firstFailure = failure;
    } finally {
      clearTimeout(timer);
    }
  }
  if (firstFailure) throw firstFailure;
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function runtimePluginError(
  code,
  descriptor,
  hook,
  cause,
  workflow,
  location = {},
) {
  const suffix = hook ? ` hook '${hook}'` : "";
  return vfError(
    code,
    `runtime plugin '${descriptor.id}'${suffix} failed`,
    workflow,
    {
      nodePath: location.nodePath || "",
      blockPath: location.blockPath || "/",
      cause,
    },
  );
}

function runtimePluginContext(workflow, descriptor, root) {
  return Object.freeze({
    abiVersion: VIBEFLOW_PLUGIN_ABI,
    pluginId: descriptor.id,
    pluginType: "runtime",
    target: descriptor.target,
    workflowId: workflow.workflow_id,
    config: deepFreeze(descriptor.config || {}),
    signal: root.signal,
  });
}

function runtimePluginSummary(root, details = {}) {
  return deepFreeze({
    workflowId: root.workflowId,
    entryMode: root.workflow.entry_mode,
    ...details,
  });
}

function createRuntimePluginsSync(workflow, descriptors, factories, root) {
  const records = [];
  try {
    for (const descriptor of descriptors) {
      const factory = factories[descriptor.factory_index];
      if (typeof factory !== "function") {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          new TypeError("plugin module does not export createPlugin()"),
          workflow,
        );
      }
      let instance;
      try {
        instance = factory(runtimePluginContext(workflow, descriptor, root));
      } catch (cause) {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          cause,
          workflow,
        );
      }
      if (!instance || typeof instance !== "object" || Array.isArray(instance)) {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          new TypeError("createPlugin() must return a RuntimePlugin object"),
          workflow,
        );
      }
      records.push({ descriptor, instance });
    }
    return records;
  } catch (failure) {
    for (let index = records.length - 1; index >= 0; index -= 1) {
      try {
        records[index].instance.dispose?.();
      } catch {
        // Preserve the primary creation failure.
      }
    }
    throw failure;
  }
}

async function createRuntimePluginsAsync(workflow, descriptors, factories, root) {
  const records = [];
  try {
    for (const descriptor of descriptors) {
      const factory = factories[descriptor.factory_index];
      if (typeof factory !== "function") {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          new TypeError("plugin module does not export createPlugin()"),
          workflow,
        );
      }
      let instance;
      try {
        instance = factory(runtimePluginContext(workflow, descriptor, root));
      } catch (cause) {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          cause,
          workflow,
        );
      }
      if (!instance || typeof instance !== "object" || Array.isArray(instance)) {
        throw runtimePluginError(
          "VF_RUNTIME_PLUGIN_CREATE",
          descriptor,
          "createPlugin",
          new TypeError("createPlugin() must return a RuntimePlugin object"),
          workflow,
        );
      }
      records.push({ descriptor, instance });
    }
    return records;
  } catch (failure) {
    for (let index = records.length - 1; index >= 0; index -= 1) {
      try {
        await records[index].instance.dispose?.();
      } catch {
        // Preserve the primary creation failure.
      }
    }
    throw failure;
  }
}

function invokeRuntimeHookSync(root, hook, details = {}, preserveFailure = false) {
  const summary = runtimePluginSummary(root, details);
  for (const record of root.runtimePlugins) {
    const callback = record.instance[hook];
    if (typeof callback !== "function") continue;
    try {
      callback(summary);
    } catch (cause) {
      if (preserveFailure) continue;
      throw runtimePluginError(
        "VF_RUNTIME_PLUGIN_HOOK",
        record.descriptor,
        hook,
        cause,
        root.workflow,
        summary,
      );
    }
  }
}

async function invokeRuntimeHookAsync(root, hook, details = {}, preserveFailure = false) {
  const summary = runtimePluginSummary(root, details);
  for (const record of root.runtimePlugins) {
    const callback = record.instance[hook];
    if (typeof callback !== "function") continue;
    try {
      await awaitWithAbort(
        Promise.resolve().then(() => callback(summary)),
        root.signal,
        root.workflow,
      );
    } catch (cause) {
      if (preserveFailure) continue;
      throw runtimePluginError(
        "VF_RUNTIME_PLUGIN_HOOK",
        record.descriptor,
        hook,
        cause,
        root.workflow,
        summary,
      );
    }
  }
}

function disposeRuntimePluginsSync(root, preserveFailure = false) {
  for (let index = root.runtimePlugins.length - 1; index >= 0; index -= 1) {
    const record = root.runtimePlugins[index];
    if (typeof record.instance.dispose !== "function") continue;
    try {
      record.instance.dispose();
    } catch (cause) {
      if (preserveFailure) continue;
      throw runtimePluginError(
        "VF_RUNTIME_PLUGIN_DISPOSE",
        record.descriptor,
        "dispose",
        cause,
        root.workflow,
      );
    }
  }
  root.runtimePlugins.length = 0;
}

async function disposeRuntimePluginsAsync(root, preserveFailure = false) {
  let firstFailure = null;
  for (let index = root.runtimePlugins.length - 1; index >= 0; index -= 1) {
    const record = root.runtimePlugins[index];
    if (typeof record.instance.dispose !== "function") continue;
    try {
      await record.instance.dispose();
    } catch (cause) {
      if (!preserveFailure && !firstFailure) {
        firstFailure = runtimePluginError(
          "VF_RUNTIME_PLUGIN_DISPOSE",
          record.descriptor,
          "dispose",
          cause,
          root.workflow,
        );
      }
    }
  }
  root.runtimePlugins.length = 0;
  if (firstFailure) throw firstFailure;
}

function createRoot(workflow, normalized) {
  return {
    workflow,
    workflowId: workflow.workflow_id,
    signal: normalized.signal || new AbortController().signal,
    traceMode: normalized.traceMode,
    onTrace: normalized.onTrace,
    detachedTimeoutMs: normalized.detachedTimeoutMs,
    detached: new Set(),
    detachedFailure: null,
    capabilities: {},
    runtimePlugins: [],
  };
}

function prepareWorkflowInvocation(
  workflow,
  descriptors,
  requirements,
  schemas,
  options,
  entryMode,
) {
  let normalized;
  try {
    normalized = normalizeOptions(workflow, options);
  } catch (cause) {
    throw ensureErrorLocation(cause, workflow, []);
  }
  const root = createRoot(workflow, normalized);
  try {
    throwIfAborted(root.signal, workflow);
    root.capabilities = prepareCapabilities(
      workflow,
      descriptors,
      requirements,
      schemas,
      normalized.capabilities,
      root,
      entryMode,
    );
    emitTrace(root, "run_start", {}, true);
    return root;
  } catch (cause) {
    throw ensureErrorLocation(cause, workflow, []);
  }
}

function assertWorkflowAbi(workflow) {
  if (workflow.abi_version !== VIBEFLOW_WORKFLOW_ABI) {
    throw vfError(
      "VF_INTERNAL",
      `generated workflow ABI '${workflow.abi_version}' is unsupported`,
      workflow,
    );
  }
}

function createStaticWorkflowSync(
  workflowMetadata,
  capabilityDescriptors,
  capabilityRequirements,
  schemaCatalog,
  runtimePluginDescriptors,
  runtimePluginFactories,
  executeRoot,
) {
  const workflow = deepFreeze(workflowMetadata);
  const descriptors = deepFreeze(capabilityDescriptors);
  const requirements = deepFreeze(capabilityRequirements);
  const schemas = deepFreeze(schemaCatalog);
  const plugins = deepFreeze(runtimePluginDescriptors);
  assertWorkflowAbi(workflow);
  return function invokeWorkflow(inputs, options) {
    const root = prepareWorkflowInvocation(
      workflow,
      descriptors,
      requirements,
      schemas,
      options,
      "sync",
    );
    root.runtimePlugins = createRuntimePluginsSync(
      workflow,
      plugins,
      runtimePluginFactories,
      root,
    );
    let failed = false;
    try {
      invokeRuntimeHookSync(root, "beforeRun", {
        inputKeys: Object.keys(inputs || {}).sort(),
      });
      const result = executeRoot(inputs, root, []);
      throwIfAborted(root.signal, workflow);
      invokeRuntimeHookSync(root, "afterRun", {
        outputKeys: Object.keys(result.publicOutputs || {}).sort(),
      });
      emitTrace(root, "run_end", {}, true);
      return result.publicOutputs;
    } catch (cause) {
      failed = true;
      const failure = cause instanceof VibeFlowWorkflowError
        ? cause
        : vfError("VF_INTERNAL", "generated workflow failed internally", workflow, { cause });
      if (failure.code !== "VF_TRACE_SINK_FAILED") {
        try {
          emitTrace(root, "run_failed", {
            code: failure.code,
            message: failure.message,
          }, true);
        } catch {
          // Preserve the primary workflow failure.
        }
      }
      invokeRuntimeHookSync(root, "runFailed", {
        code: failure.code,
        message: failure.message,
      }, true);
      throw ensureErrorLocation(failure, workflow, []);
    } finally {
      disposeRuntimePluginsSync(root, failed);
    }
  };
}

function createStaticWorkflowAsync(
  workflowMetadata,
  capabilityDescriptors,
  capabilityRequirements,
  schemaCatalog,
  runtimePluginDescriptors,
  runtimePluginFactories,
  executeRoot,
) {
  const workflow = deepFreeze(workflowMetadata);
  const descriptors = deepFreeze(capabilityDescriptors);
  const requirements = deepFreeze(capabilityRequirements);
  const schemas = deepFreeze(schemaCatalog);
  const plugins = deepFreeze(runtimePluginDescriptors);
  assertWorkflowAbi(workflow);
  return async function invokeWorkflow(inputs, options) {
    const root = prepareWorkflowInvocation(
      workflow,
      descriptors,
      requirements,
      schemas,
      options,
      "async",
    );
    root.runtimePlugins = await createRuntimePluginsAsync(
      workflow,
      plugins,
      runtimePluginFactories,
      root,
    );
    let result;
    let failure = null;
    try {
      await invokeRuntimeHookAsync(root, "beforeRun", {
        inputKeys: Object.keys(inputs || {}).sort(),
      });
      result = await executeRoot(inputs, root, []);
      throwIfAborted(root.signal, workflow);
    } catch (cause) {
      failure = cause instanceof VibeFlowWorkflowError
        ? cause
        : vfError("VF_INTERNAL", "generated workflow failed internally", workflow, { cause });
    }
    try {
      await settleDetached(root);
    } catch (cleanupCause) {
      const cleanupFailure = cleanupCause instanceof VibeFlowWorkflowError
        ? cleanupCause
        : vfError("VF_INTERNAL", "detached task cleanup failed internally", workflow, {
          cause: cleanupCause,
        });
      if (!failure) failure = cleanupFailure;
      else {
        try {
          emitTrace(root, "async_cleanup_failed", {
            code: cleanupFailure.code,
            message: cleanupFailure.message,
          }, true);
        } catch {
          // Preserve the primary failure after cleanup.
        }
      }
    }
    if (failure) {
      if (failure.code !== "VF_TRACE_SINK_FAILED") {
        try {
          emitTrace(root, "run_failed", {
            code: failure.code,
            message: failure.message,
          }, true);
        } catch {
          // Cleanup is complete; preserve the primary failure.
        }
      }
      await invokeRuntimeHookAsync(root, "runFailed", {
        code: failure.code,
        message: failure.message,
      }, true);
      await disposeRuntimePluginsAsync(root, true);
      throw ensureErrorLocation(failure, workflow, []);
    }
    try {
      await invokeRuntimeHookAsync(root, "afterRun", {
        outputKeys: Object.keys(result.publicOutputs || {}).sort(),
      });
      emitTrace(root, "run_end", {}, true);
    } catch (cause) {
      failure = ensureErrorLocation(cause, workflow, []);
      await invokeRuntimeHookAsync(root, "runFailed", {
        code: failure.code,
        message: failure.message,
      }, true);
      await disposeRuntimePluginsAsync(root, true);
      throw failure;
    }
    await disposeRuntimePluginsAsync(root);
    return result.publicOutputs;
  };
}
