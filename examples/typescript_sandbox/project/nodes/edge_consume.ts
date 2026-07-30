interface Envelope<T> {
  readonly value: T;
}

interface EdgeConsumeInputs {
  readonly "sandbox.fanout.added": Envelope<number>;
}

export function run(
  inputs: EdgeConsumeInputs,
): { readonly result: number } {
  return {
    result: inputs["sandbox.fanout.added"].value * 2,
  };
}
