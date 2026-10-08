const ready = Promise.resolve(1);

export function run(): { readonly result: number } {
  void ready;
  return { result: 1 };
}
