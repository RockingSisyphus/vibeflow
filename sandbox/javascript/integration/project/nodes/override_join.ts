interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface OverrideJoinInputs {
  readonly "sandbox.math.result": Envelope<number>;
  readonly "sandbox.override.default": Envelope<number>;
}

export function run(
  inputs: OverrideJoinInputs,
): { readonly joined_result: number } {
  // Reading both inputs makes the join's dependency explicit in the TS source.
  void inputs["sandbox.override.default"].value;
  return {
    joined_result: inputs["sandbox.math.result"].value,
  };
}
