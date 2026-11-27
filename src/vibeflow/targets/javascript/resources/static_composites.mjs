function executeStaticNodeSync(_program, block, index, node, implementation, inputs) {
  return invokeStaticImplementationSync(implementation, node, block.params[index], inputs, block.state);
}

async function executeStaticNodeAsync(_program, block, index, node, implementation, inputs) {
  return invokeStaticImplementationAsync(implementation, node, block.params[index], inputs, block.state);
}

function staticNodesetInputs(program, child, outputs, inputs, state, event) {
  emitTrace(state.root, "nodeset_enter", {nodeId: event.nodeId, nodePath: event.nodePath}, true);
  if (typeof outputs === "string") {
    throw vfError("VF_OUTPUT_CARDINALITY", outputs, state.workflow, {nodePath: event.nodePath});
  }
  const metadata = program.blocks[program.calls[child][0]][0];
  return rawInputsForChild(metadata.inputs, inputs, state.workflow, event.nodeId);
}

function staticNodesetOutputs(node, mapping, child, state, event) {
  const outputs = outputsFromChild(node, mapping, child, state);
  emitTrace(state.root, "nodeset_exit", {nodeId: event.nodeId, nodePath: event.nodePath}, true);
  return outputs;
}

function executeStaticNodesetSync(program, block, index, node, mapping, inputs) {
  const {state} = block;
  const child = block.children[index];
  const event = staticNodeLocation(node, state);
  try {
    invokeRuntimeHookSync(state.root, "beforeNodeset", event);
    const initial = staticNodesetInputs(program, child, mapping, inputs, state, event);
    const result = executeStaticBlockSync(program, child, initial, state.root, [...state.path, node.id]);
    const outputs = staticNodesetOutputs(node, mapping, result, state, event);
    invokeRuntimeHookSync(state.root, "afterNodeset", event);
    return outputs;
  } catch (cause) {
    const failure = ensureErrorLocation(cause, state.workflow, state.path, node.id);
    invokeRuntimeHookSync(state.root, "nodesetFailed", staticFailureDetails(event, failure), true);
    throw failure;
  }
}

async function executeStaticNodesetAsync(program, block, index, node, mapping, inputs) {
  const {state} = block;
  const child = block.children[index];
  const event = staticNodeLocation(node, state);
  try {
    await invokeRuntimeHookAsync(state.root, "beforeNodeset", event);
    const initial = staticNodesetInputs(program, child, mapping, inputs, state, event);
    const result = await awaitWithAbort(
      executeStaticBlockAsync(program, child, initial, state.root, [...state.path, node.id]),
      state.root.signal, state.workflow, event.nodePath,
    );
    const outputs = staticNodesetOutputs(node, mapping, result, state, event);
    await invokeRuntimeHookAsync(state.root, "afterNodeset", event);
    return outputs;
  } catch (cause) {
    const failure = ensureErrorLocation(cause, state.workflow, state.path, node.id);
    await invokeRuntimeHookAsync(state.root, "nodesetFailed", staticFailureDetails(event, failure), true);
    throw failure;
  }
}

function staticLoopValue(values, key, label, code, state, event) {
  if (!Object.prototype.hasOwnProperty.call(values, key)) {
    throw vfError(code, `${label} '${key}' is unavailable`, state.workflow, {nodePath: event.nodePath});
  }
  return values[key];
}

function openStaticLoop(node, spec, inputs, state) {
  const event = {nodeId: node.id, nodePath: nodePath(state, node.id)};
  emitTrace(state.root, "loop_enter", event, true);
  const values = dictionary();
  for (const [type, input] of Object.entries(inputs)) {
    setOwn(values, type, Array.isArray(input) ? input.map(valueFromEnvelope) : valueFromEnvelope(input));
    for (const item of Array.isArray(input) ? input : [input]) {
      if (item?.key) setOwn(values, item.key, item.value);
      if (item?.type) setOwn(values, item.type, item.value);
    }
  }
  for (const carry of spec.carry) {
    setOwn(values, carry.as, staticLoopValue(values, carry.from, "loop carry source", "VF_INPUT_REQUIRED", state, event));
  }
  return {event, values, spec, state, stopped: false};
}

function staticLoopInputs(loop, iteration) {
  const {event, values, spec, state} = loop;
  throwIfAborted(state.root.signal, state.workflow, event.nodePath);
  const initial = dictionary();
  for (const carry of spec.carry) setOwn(initial, carry.as, values[carry.as]);
  emitTrace(state.root, "loop_iteration", {...event, iteration});
  return initial;
}

function updateStaticLoop(loop, child, iteration) {
  const {event, values, spec, state} = loop;
  for (const [key, value] of Object.entries(resultValues(child))) setOwn(values, key, value);
  for (const carry of spec.carry) {
    setOwn(values, carry.as, staticLoopValue(values, carry.update, "loop carry update", "VF_OUTPUT_KEYS", state, event));
  }
  for (const collect of spec.collect) {
    if (collect.mode !== "all") throw vfError("VF_INTERNAL", `unsupported loop collect mode '${collect.mode}'`, state.workflow);
    const value = staticLoopValue(values, collect.from, "loop collect source", "VF_OUTPUT_KEYS", state, event);
    if (!Array.isArray(values[collect.as])) setOwn(values, collect.as, []);
    values[collect.as].push(value);
  }
  const count = iteration + 1;
  setOwn(values, "loop.iterations", count);
  loop.stopped = count >= (spec.stop_after ?? Infinity);
  if (spec.stop_when) {
    const key = spec.stop_when.from;
    const value = staticLoopValue(values, key, "loop stop source", "VF_OUTPUT_KEYS", state, event);
    if (typeof value !== "boolean") {
      throw vfError("VF_OUTPUT_SCHEMA", `loop stop source '${key}' must be boolean`, state.workflow, {nodePath: event.nodePath});
    }
    loop.stopped ||= value === spec.stop_when.equals;
  }
}

function finishStaticLoop(loop, node) {
  const {event, values, spec, state, stopped} = loop;
  if (!stopped && spec.max_iterations !== null && (spec.stop_after || spec.stop_when)) {
    throw vfError("VF_MAX_STEPS", `loop node '${node.id}' exceeded max_iterations=${spec.max_iterations}`,
      state.workflow, {nodePath: event.nodePath});
  }
  const outputs = dictionary();
  for (const output of spec.outputs) {
    setOwn(outputs, output.as, staticLoopValue(values, output.from, "loop output source", "VF_OUTPUT_KEYS", state, event));
  }
  emitTrace(state.root, "loop_exit", event, true);
  return validateNodeOutputs(node, outputs, state);
}

function executeStaticLoopSync(program, block, index, node, spec, inputs) {
  const {state} = block;
  const child = block.children[index];
  const loop = openStaticLoop(node, spec, inputs, state);
  for (let i = 0; i < (spec.max_iterations ?? Infinity) && !loop.stopped; i += 1) {
    const initial = staticLoopInputs(loop, i);
    const result = executeStaticBlockSync(program, child, initial, state.root, [...state.path, node.id, `iter_${i}`]);
    updateStaticLoop(loop, result, i);
  }
  return finishStaticLoop(loop, node);
}

async function executeStaticLoopAsync(program, block, index, node, spec, inputs) {
  const {state} = block;
  const child = block.children[index];
  const loop = openStaticLoop(node, spec, inputs, state);
  for (let i = 0; i < (spec.max_iterations ?? Infinity) && !loop.stopped; i += 1) {
    const initial = staticLoopInputs(loop, i);
    const result = await awaitWithAbort(
      executeStaticBlockAsync(program, child, initial, state.root, [...state.path, node.id, `iter_${i}`]),
      state.root.signal, state.workflow, loop.event.nodePath,
    );
    updateStaticLoop(loop, result, i);
  }
  return finishStaticLoop(loop, node);
}
