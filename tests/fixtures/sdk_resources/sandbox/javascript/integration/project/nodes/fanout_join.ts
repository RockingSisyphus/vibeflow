interface Envelope<T> {
  readonly value: T;
}

interface JoinInputs {
  readonly "sandbox.fanout.added": Envelope<number>;
  readonly "sandbox.fanout.subtracted": Envelope<number>;
}

export function run(inputs: JoinInputs): {
  readonly added: number;
  readonly subtracted: number;
} {
  return {
    added: inputs["sandbox.fanout.added"].value,
    subtracted: inputs["sandbox.fanout.subtracted"].value,
  };
}
