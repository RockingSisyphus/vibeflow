interface Envelope<T> {
  readonly value: T;
}

interface StorageInputs {
  readonly "sandbox.storage.key": Envelope<string>;
}



export async function run(
  inputs: StorageInputs,
  _params: Readonly<Record<never, never>>,
  context: any,
): Promise<{ readonly value: string }> {
  const result = await (inputs as any)["app.session"].value.storage.read({
    key: inputs["sandbox.storage.key"].value,
  }, {signal: context.signal});
  return { value: result.value };
}
