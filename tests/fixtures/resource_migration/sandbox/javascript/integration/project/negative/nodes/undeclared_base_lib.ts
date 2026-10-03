import { add } from "../../base_lib/math.ts";

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
    result: add(inputs["sandbox.number"].value, 0),
  };
}
