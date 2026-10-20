// Native runtime support; assembled by frontend.templates.
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
      } catch (error) {
        (failure.cleanupErrors ||= []).push(runtimePluginError('VF_RUNTIME_PLUGIN_DISPOSE',records[index].descriptor,'dispose',error,workflow));
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
      } catch (error) {
        (failure.cleanupErrors ||= []).push(runtimePluginError('VF_RUNTIME_PLUGIN_DISPOSE',records[index].descriptor,'dispose',error,workflow));
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
      if (preserveFailure) {
        (root.cleanupErrors ||= []).push(runtimePluginError('VF_RUNTIME_PLUGIN_HOOK',record.descriptor,hook,cause,root.workflow,summary));
        continue;
      }
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
      if (preserveFailure) {
        (root.cleanupErrors ||= []).push(runtimePluginError('VF_RUNTIME_PLUGIN_HOOK',record.descriptor,hook,cause,root.workflow,summary));
        continue;
      }
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
  let firstFailure;
  for (let index=root.runtimePlugins.length-1;index>=0;index--) {
    const record=root.runtimePlugins[index];
    try { record.instance.dispose?.(); }
    catch(cause) {
      const error=runtimePluginError('VF_RUNTIME_PLUGIN_DISPOSE',record.descriptor,'dispose',cause,root.workflow);
      if(preserveFailure)(root.cleanupErrors ||= []).push(error);
      else if(firstFailure)(firstFailure.cleanupErrors ||= []).push(error);
      else firstFailure=error;
    }
  }
  root.runtimePlugins.length=0;
  if(firstFailure)throw firstFailure;
}

async function disposeRuntimePluginsAsync(root, preserveFailure = false) {
  let firstFailure;
  for (let index=root.runtimePlugins.length-1;index>=0;index--) {
    const record=root.runtimePlugins[index];
    try { await record.instance.dispose?.(); }
    catch(cause) {
      const error=runtimePluginError('VF_RUNTIME_PLUGIN_DISPOSE',record.descriptor,'dispose',cause,root.workflow);
      if(preserveFailure)(root.cleanupErrors ||= []).push(error);
      else if(firstFailure)(firstFailure.cleanupErrors ||= []).push(error);
      else firstFailure=error;
    }
  }
  root.runtimePlugins.length=0;
  if(firstFailure)throw firstFailure;
}
