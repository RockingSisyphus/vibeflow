import { identity } from "../../runtime/internal.ts";

interface Envelope<T> {
  readonly value: T;
}

interface InvalidInputs {
  readonly "sandbox.number": Envelope<number>;
}

export function run(
  inputs: InvalidInputs,
): { readonly result: number } {
  return {
    result: identity(inputs["sandbox.number"].value),
  };
}
