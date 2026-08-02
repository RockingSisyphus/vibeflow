interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface OverrideDefaultInputs {
  readonly "sandbox.math.result": Envelope<number>;
}

export function run(
  inputs: OverrideDefaultInputs,
): { readonly default_result: number } {
  return {
    default_result: inputs["sandbox.math.result"].value,
  };
}
