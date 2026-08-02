interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface FailureInputs {
  readonly "sandbox.number": Envelope<number>;
}

interface FailureParams {
  readonly mode: string;
}

export function run(
  inputs: FailureInputs,
  params: FailureParams,
): { readonly result: number } {
  if (params.mode === "throw") {
    throw new Error("sandbox node exploded");
  }
  void inputs;
  return {
    result: "not-a-number" as unknown as number,
  };
}
