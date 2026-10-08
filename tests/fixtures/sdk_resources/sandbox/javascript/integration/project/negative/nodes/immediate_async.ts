interface Inputs {
  readonly "sandbox.number": {
    readonly value: number;
  };
}

export async function run(
  inputs: Inputs,
): Promise<{ readonly result: number }> {
  return { result: inputs["sandbox.number"].value };
}
