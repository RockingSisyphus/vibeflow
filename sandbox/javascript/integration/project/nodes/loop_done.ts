interface Envelope<T> {
  readonly value: T;
}

interface LoopDoneInputs {
  readonly "sandbox.loop.next": Envelope<number>;
}

interface LoopDoneParams {
  readonly target: number;
}

export function run(
  inputs: LoopDoneInputs,
  params: LoopDoneParams,
): { readonly done: boolean } {
  return {
    done: inputs["sandbox.loop.next"].value >= params.target,
  };
}
