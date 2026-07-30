import { run as forbiddenMathNodeRun } from "../../nodes/math.ts";

interface Envelope<T> {
  readonly value: T;
}

interface InvalidInputs {
  readonly "sandbox.number": Envelope<number>;
}

export function run(
  inputs: InvalidInputs,
): { readonly result: number } {
  if (typeof forbiddenMathNodeRun !== "function") {
    throw new Error("unreachable");
  }
  return { result: inputs["sandbox.number"].value };
}
