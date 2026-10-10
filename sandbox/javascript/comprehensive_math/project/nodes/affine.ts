import {affine, subtract} from "../base_lib/arithmetic.ts";
export function run(i: any, p: any) {
  return {scaled: affine(i["math.x"].value, p.gain, p.shift)};
}
