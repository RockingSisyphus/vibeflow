interface Envelope<T> {
  readonly value: T;
}

interface Inputs {
  readonly "sandbox.number": Envelope<number>;
}



export function run(
  inputs: Inputs,
  _params: Readonly<Record<string, unknown>>,
  context: any,
): { readonly result: number } {
  return {
    result: (inputs as any)["app.session"].value.math_session.double(
      inputs["sandbox.number"].value,
    ),
  };
}
