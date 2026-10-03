interface Inputs {
  readonly "sandbox.number": {
    readonly value: number;
  };
}

export async function run(
  inputs: Inputs,
): Promise<{ readonly result: number }> {
  void Promise.resolve(inputs["sandbox.number"].value);
  return { result: inputs["sandbox.number"].value };
}
