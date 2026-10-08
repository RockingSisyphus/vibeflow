import { subtract } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface SubtractInputs {
  readonly "sandbox.sum": Envelope<number>;
  readonly "sandbox.subtrahend.forwarded": Envelope<number>;
}

export function run(
  inputs: SubtractInputs,
): { readonly result: number } {
  return {
    result: subtract(
      inputs["sandbox.sum"].value,
      inputs["sandbox.subtrahend.forwarded"].value,
    ),
  };
}
