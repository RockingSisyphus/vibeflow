import { affine } from "../base_lib/math.ts";

interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface MathInputs {
  readonly "sandbox.number": Envelope<number>;
}

interface MathParams {
  readonly scale: number;
  readonly offset: number;
}

export function run(
  inputs: MathInputs,
  params: MathParams,
): { readonly result: number } {
  return {
    result: affine(
      inputs["sandbox.number"].value,
      params.scale,
      params.offset,
    ),
  };
}
