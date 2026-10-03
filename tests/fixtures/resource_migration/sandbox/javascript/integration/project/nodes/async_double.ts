interface Envelope<T> {
  readonly value: T;
}

interface AsyncInputs {
  readonly "sandbox.number": Envelope<number>;
}

export async function run(
  inputs: AsyncInputs,
): Promise<{ readonly doubled: number }> {
  await Promise.resolve();
  return {
    doubled: inputs["sandbox.number"].value * 2,
  };
}
