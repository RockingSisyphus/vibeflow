interface Envelope<T> {
  readonly value: T;
}

interface BranchInputs {
  readonly "sandbox.branch.forwarded": Envelope<number>;
}

export function run(
  inputs: BranchInputs,
): { readonly positive_message: string } {
  return {
    positive_message:
      `non-negative:${inputs["sandbox.branch.forwarded"].value}`,
  };
}
