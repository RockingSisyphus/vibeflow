interface Inputs {
  readonly "sandbox.number": {
    readonly value: number;
  };
}

export function run(
  inputs: Inputs,
): { readonly result: number } {
  return { result: inputs["sandbox.number"].value };
}
