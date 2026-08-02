interface Envelope<T> {
  readonly value: T;
}

interface JoinInputs {
  readonly "sandbox.branch.message": Envelope<string>;
}

export function run(
  inputs: JoinInputs,
): { readonly message: string } {
  return {
    message: inputs["sandbox.branch.message"].value,
  };
}
