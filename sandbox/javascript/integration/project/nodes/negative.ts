interface Envelope<T> {
  readonly value: T;
}

interface BranchInputs {
  readonly "sandbox.branch.forwarded": Envelope<number>;
}

export function run(
  inputs: BranchInputs,
): { readonly negative_message: string } {
  return {
    negative_message:
      `negative:${inputs["sandbox.branch.forwarded"].value}`,
  };
}
