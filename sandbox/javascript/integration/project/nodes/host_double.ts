interface Envelope<T> {
  readonly value: T;
}

interface Inputs {
  readonly "sandbox.number": Envelope<number>;
}

interface Context {
  readonly capabilities: {
    readonly "sandbox.host_math": {
      readonly double: (input: number) => number;
    };
  };
}

export function run(
  inputs: Inputs,
  _params: Readonly<Record<string, unknown>>,
  context: Context,
): { readonly result: number } {
  return {
    result: context.capabilities["sandbox.host_math"].double(
      inputs["sandbox.number"].value,
    ),
  };
}
