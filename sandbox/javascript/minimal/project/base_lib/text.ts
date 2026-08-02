export function normalizeName(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}
