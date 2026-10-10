import {affine, subtract} from "../base_lib/arithmetic.ts";
export function run(i: any, p: any) {
  return {q: subtract(i["math.scaled"].value, p.amount)};
}
