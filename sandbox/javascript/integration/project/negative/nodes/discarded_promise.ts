export async function run(): Promise<{ readonly result: number }> {
  void Promise.resolve(1);
  return { result: 1 };
}
