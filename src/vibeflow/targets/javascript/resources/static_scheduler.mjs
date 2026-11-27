// The emitter prepares entry and route facts. All mutable scheduling data belongs
// to a single block invocation.
function openStaticBlock(program, callIndex, initial, root, path, entry, workflow) {
  const [blockIndex, , params, children] = program.calls[callIndex];
  const [, nodes, variants] = program.blocks[blockIndex];
  const [starts, checks] = variants[entry ?? 0];
  const state = createStaticState(workflow, initial, root, path);
  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index][0];
    initializeInbox(state, node.id);
    const seed = checks[index]?.[0];
    if (seed !== null && seed !== undefined) seedInbox(state, node.id, seed);
  }
  return {
    nodes, params, children, checks, state, ready: [...starts], queued: new Set(starts),
    pendingDispatches: new Map(), activeDispatches: new Map(), completed: false,
  };
}

function staticNodeAvailable(block, index) {
  const check = block.checks[index];
  if (check === undefined) return false;
  const [, policy, edges, required] = check;
  const {state} = block;
  if (policy === "all" && !edges.every(edge => state.activeEdges.has(edge))) return false;
  if (policy === "any_active" && !edges.some(edge => state.activeEdges.has(edge))) return false;
  const inbox = state.inboxes[block.nodes[index][0].id];
  return required.every(type => inbox.some(item => item.type === type));
}

function startStaticNode(block, index, node) {
  const {state, pendingDispatches, activeDispatches} = block;
  const dispatches = pendingDispatches.get(index);
  pendingDispatches.delete(index);
  if (dispatches) {
    for (const dispatch of dispatches) dispatch.active += 1;
    activeDispatches.set(index, dispatches);
  }
  if (state.stepCount >= state.workflow.max_steps) {
    throw vfError("VF_MAX_STEPS", "workflow exceeded max_steps", state.workflow);
  }
  state.stepCount += 1;
  const inputs = prepareStaticNode(node, state);
  const [, policy, edges] = block.checks[index];
  if (policy === "all") {
    for (const edge of edges) state.activeEdges.delete(edge);
  }
  return inputs;
}

function releaseStaticDispatch(block, index) {
  for (const dispatch of block.activeDispatches.get(index) || []) dispatch.active -= 1;
  block.activeDispatches.delete(index);
}

function activateStaticRoutes(block, index, outputs, inputs) {
  const [node, , routes, terminal, limit] = block.nodes[index];
  const {state, pendingDispatches, ready, queued} = block;
  const values = conditionValues(inputs, outputs);
  const envelopes = outputEnvelopes(node, outputs);
  for (const envelope of envelopes) recordCandidate(state, envelope);
  const targets = [];
  for (const [target, edge, accepts, condition] of routes) {
    if (condition !== null && !conditionMatches(condition, values)) continue;
    const targetId = block.nodes[target][0].id;
    if (edge !== null) {
      state.activeEdges.add(edge);
      targets.push(target);
      emitTrace(state.root, "edge_activated", {source: node.id, target: targetId, path: state.path});
    }
    if (accepts !== null) deliverStatic(envelopes, state, targetId, accepts);
  }
  if (terminal) {
    block.completed = true;
    return;
  }
  if (limit !== null) {
    const dispatch = {limit, active: 0};
    for (const target of targets) {
      if (!pendingDispatches.has(target)) pendingDispatches.set(target, new Set());
      pendingDispatches.get(target).add(dispatch);
    }
  }
  enqueueStaticTargets(targets, ready, queued);
}

function staticNodeLocation(node, state) {
  return {nodeId: node.id, nodePath: nodePath(state, node.id), blockPath: formatBlockPath(state.path)};
}

function staticFailureDetails(location, failure) {
  return {...location, code: failure.code, message: failure.message};
}

function executeStaticBlockSync(program, call, initial, root, path, entry) {
  const location = {blockPath: formatBlockPath(path), path: [...path]};
  const workflow = staticBlockMetadata(program, call, root, entry);
  try {
    invokeRuntimeHookSync(root, "beforeBlock", {...location, path: [...path]});
    const block = openStaticBlock(program, call, initial, root, path, entry, workflow);
    const {state, ready, queued, nodes} = block;
    while (ready.length) {
      const index = ready.shift();
      queued.delete(index);
      if (staticNodeAvailable(block, index)) {
        const [node, [execute, target]] = nodes[index];
        const event = {...staticNodeLocation(node, state), type: node.definition_id};
        try {
          const inputs = startStaticNode(block, index, node);
          invokeRuntimeHookSync(root, "beforeNode", event);
          const outputs = execute(program, block, index, node, target, inputs);
          finishStaticNode(node, state);
          invokeRuntimeHookSync(root, "afterNode", {...event, outputKeys: Object.keys(outputs || {}).sort()});
          activateStaticRoutes(block, index, outputs, inputs);
        } catch (cause) {
          const failure = ensureErrorLocation(cause, workflow, path, node.id);
          invokeRuntimeHookSync(root, "nodeFailed", staticFailureDetails(staticNodeLocation(node, state), failure), true);
          throw failure;
        }
      }
      releaseStaticDispatch(block, index);
    }
    const publicOutputs = finalizeOutputs(state);
    invokeRuntimeHookSync(root, "afterBlock", location);
    return {publicOutputs, candidates: state.candidates, completed: block.completed};
  } catch (cause) {
    const failure = ensureErrorLocation(cause, workflow, path);
    invokeRuntimeHookSync(root, "blockFailed", staticFailureDetails(location, failure), true);
    throw failure;
  }
}

async function executeStaticBlockAsync(program, call, initial, root, path, entry) {
  const running = new Map();
  const location = {blockPath: formatBlockPath(path), path: [...path]};
  const workflow = staticBlockMetadata(program, call, root, entry);
  try {
    await invokeRuntimeHookAsync(root, "beforeBlock", {...location, path: [...path]});
    const block = openStaticBlock(program, call, initial, root, path, entry, workflow);
    const {state, ready, queued, nodes, pendingDispatches} = block;
    async function executeReady(index) {
      if (!staticNodeAvailable(block, index)) return;
      const [node, [execute, target]] = nodes[index];
      const event = {...staticNodeLocation(node, state), type: node.definition_id};
      try {
        const inputs = startStaticNode(block, index, node);
        await invokeRuntimeHookAsync(root, "beforeNode", event);
        const outputs = await execute(program, block, index, node, target, inputs);
        finishStaticNode(node, state);
        await invokeRuntimeHookAsync(root, "afterNode", {...event, outputKeys: Object.keys(outputs || {}).sort()});
        activateStaticRoutes(block, index, outputs, inputs);
      } catch (cause) {
        const failure = ensureErrorLocation(cause, workflow, path, node.id);
        await invokeRuntimeHookAsync(root, "nodeFailed", staticFailureDetails(staticNodeLocation(node, state), failure), true);
        throw failure;
      }
    }
    while (ready.length || running.size) {
      throwIfAborted(root.signal, state.workflow);
      for (const index of ready.splice(0)) {
        queued.delete(index);
        const dispatches = pendingDispatches.get(index);
        if (running.has(index) || (dispatches && [...dispatches].some(dispatch => dispatch.active >= dispatch.limit))) {
          enqueueStaticTargets([index], ready, queued);
          continue;
        }
        running.set(index, executeReady(index).then(() => ({index}), error => ({index, error})));
      }
      if (!running.size) break;
      const outcome = await Promise.race(running.values());
      running.delete(outcome.index);
      releaseStaticDispatch(block, outcome.index);
      if (outcome.error) throw outcome.error;
    }
    const publicOutputs = finalizeOutputs(state);
    await invokeRuntimeHookAsync(root, "afterBlock", location);
    return {publicOutputs, candidates: state.candidates, completed: block.completed};
  } catch (cause) {
    root.controller.abort(cause);
    for (const outcome of await Promise.all(running.values())) {
      if (outcome.error && outcome.error !== cause && (outcome.error.code !== "VF_ABORTED" || outcome.error.cleanupErrors?.length)) {
        (cause.cleanupErrors ||= []).push(outcome.error);
      }
    }
    const failure = ensureErrorLocation(cause, workflow, path);
    await invokeRuntimeHookAsync(root, "blockFailed", staticFailureDetails(location, failure), true);
    throw failure;
  }
}

function staticBlockMetadata(program, call, root, entry) {
  if (entry !== undefined) return root.workflow;
  const [block, workflowId] = program.calls[call];
  return {...program.blocks[block][0], workflow_id: workflowId};
}
