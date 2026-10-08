import { add } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface LoopInputs {
  readonly "sandbox.loop.value": Envelope<number>;
}

export function run(
  inputs: LoopInputs,
): { readonly next: number } {
  return {
    next: add(inputs["sandbox.loop.value"].value, 1),
  };
}
