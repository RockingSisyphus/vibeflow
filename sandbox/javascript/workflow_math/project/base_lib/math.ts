export function add(left: number, right: number): number {
  return left + right;
}

export function subtract(left: number, right: number): number {
  return left - right;
}

export function affine(
  value: number,
  scale: number,
  offset: number,
): number {
  return value * scale + offset;
}

export function isNonNegative(value: number): boolean {
  return value >= 0;
}
