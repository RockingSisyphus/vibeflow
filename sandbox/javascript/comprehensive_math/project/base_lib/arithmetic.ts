import {multiply} from "./scalar.ts";
export function affine(value: number, gain: number, shift: number): number {
  return multiply(value + shift, gain);
}
export function subtract(value: number, amount: number): number {
  return value - amount;
}
