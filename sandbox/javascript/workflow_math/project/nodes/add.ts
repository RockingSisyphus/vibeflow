import { add } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface AddInputs {
  readonly "sandbox.x": Envelope<number>;
  readonly "sandbox.addend": Envelope<number>;
  readonly "sandbox.subtrahend": Envelope<number>;
}

export function run(inputs: AddInputs): {
  readonly sum: number;
  readonly forwarded_subtrahend: number;
} {
  return {
    sum: add(
      inputs["sandbox.x"].value,
      inputs["sandbox.addend"].value,
    ),
    forwarded_subtrahend: inputs["sandbox.subtrahend"].value,
  };
}
