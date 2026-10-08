interface Envelope<T> {
  readonly value: T;
}

interface StorageInputs {
  readonly "sandbox.storage.key": Envelope<string>;
}

interface StorageContext {
  readonly capabilities: {
    readonly "sandbox.storage": {
      readonly read: (
        input: { readonly key: string },
      ) =>
        | { readonly value: string }
        | Promise<{ readonly value: string }>;
    };
  };
}

export async function run(
  inputs: StorageInputs,
  _params: Readonly<Record<never, never>>,
  context: StorageContext,
): Promise<{ readonly value: string }> {
  const result = await context.capabilities["sandbox.storage"].read({
    key: inputs["sandbox.storage.key"].value,
  });
  return { value: result.value };
}
