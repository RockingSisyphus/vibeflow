interface Envelope<T> {
  readonly value: T;
}

export function receiveEvent(inputs: {
  readonly "sandbox.call.event": Envelope<string>;
}): { readonly route: string; readonly payload: number } {
  return { route: inputs["sandbox.call.event"].value, payload: 42 };
}

export function finishCall(inputs: {
  readonly "sandbox.number": Envelope<number>;
}): { readonly result: number } {
  return { result: inputs["sandbox.number"].value + 1 };
}
