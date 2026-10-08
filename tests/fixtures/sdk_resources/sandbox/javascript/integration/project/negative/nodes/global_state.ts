let count = 0;

export function run(): { readonly result: number } {
  count += 1;
  return { result: count };
}
