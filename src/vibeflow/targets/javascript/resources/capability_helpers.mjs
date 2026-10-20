// Native runtime support; assembled by frontend.templates.
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
  const schema=operationDescriptor.input_type?schemas[operationDescriptor.input_type]:undefined;
  if(input===undefined&&schema?.type==="object"&&!schema.required?.length)input={};
  const failure = validateJsonSchema(
    input,
    schema,
  );
  if (failure) {
    throw vfError(
      "VF_CAPABILITY_INPUT",
      `capability '${capabilityId}.${operationName}' input failed schema validation: ${failure}`,
      workflow,
      location,
    );
  }
  return input;
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
  if (root.signal?.aborted && (cause?.name === "AbortError" || cause === root.signal.reason)) {
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
        setOwn(capability, operationName, (input, caller = {}) => {
          const promise = (async () => {
          const location = capabilityLocation(caller);
          const signal = caller.signal || root.signal;
          input=validateCapabilityInput(
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
              callable.call(implementation, input, { signal: signal }),
              signal,
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
              {signal},
              capabilityId,
              operationName,
              location,
            );
          }
          })();
          return caller.execution ? caller.execution.own(promise) : promise;
        });
      } else {
        setOwn(capability, operationName, (input, caller = {}) => {
          const location = capabilityLocation(caller);
          const signal = caller.signal || root.signal;
          input=validateCapabilityInput(
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
              { signal: signal },
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

const __vfMultipleInputs = Symbol('native input envelopes');

