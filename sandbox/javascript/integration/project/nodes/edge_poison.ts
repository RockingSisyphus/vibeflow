interface EdgePoisonParams {
  readonly value: number;
}

export function run(
  _inputs: Readonly<Record<never, never>>,
  params: EdgePoisonParams,
): { readonly poisoned: number } {
  return {
    poisoned: params.value,
  };
}
