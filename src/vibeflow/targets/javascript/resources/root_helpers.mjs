// Native runtime support; assembled by frontend.templates.
function createRoot(workflow, normalized) {
  const instanceId=normalized.workflowInstanceId??Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,"0")).join("");
  const controller = new AbortController();
  const parentSignal = normalized.signal;
  const propagate = () => controller.abort(parentSignal.reason);
  parentSignal?.addEventListener("abort", propagate, {once:true});
  if (parentSignal?.aborted) propagate();
  const root = {
    workflow,
    workflowId: workflow.workflow_id,
    identity: Object.freeze({self:()=>({id:instanceId})}),
    signal: controller.signal,
    traceMode: normalized.traceMode,
    onTrace: normalized.onTrace,
    statusStopping: normalized.statusStopping,
    statusUpdate: normalized.statusUpdate,
    kernelLog: normalized.kernelLog,
    capabilities: {},
    controller,
    runtimePlugins: [],
  };
  const onAbort = () => {
    try { root.statusStopping?.(); }
    catch (error) { root.observationFailure ||= error; }
  };
  root.signal.addEventListener("abort", onAbort, {once:true});
  root.unsubscribeSignal = () => { root.signal.removeEventListener("abort", onAbort); parentSignal?.removeEventListener("abort", propagate); };
  return root;
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
    root.unsubscribeSignal();
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
    let failed = false;
    let primaryFailure;
    try {
    root.runtimePlugins = createRuntimePluginsSync(
      workflow,
      plugins,
      runtimePluginFactories,
      root,
    );

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
      primaryFailure = failure;
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
      try { disposeRuntimePluginsSync(root, failed); }
      finally {
        if(primaryFailure && root.cleanupErrors?.length)(primaryFailure.cleanupErrors ||= []).push(...root.cleanupErrors);
        root.unsubscribeSignal();
      }
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
    let result;
    let failure = null;
    try {
    root.runtimePlugins = await createRuntimePluginsAsync(
      workflow,
      plugins,
      runtimePluginFactories,
      root,
    );

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
    if (root.observationFailure && !failure) failure = root.observationFailure;
    root.unsubscribeSignal();
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
      if(root.cleanupErrors?.length)(failure.cleanupErrors ||= []).push(...root.cleanupErrors);
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
      if(root.cleanupErrors?.length)(failure.cleanupErrors ||= []).push(...root.cleanupErrors);
      throw failure;
    }
    await disposeRuntimePluginsAsync(root);
    return result.publicOutputs;
  };
}
