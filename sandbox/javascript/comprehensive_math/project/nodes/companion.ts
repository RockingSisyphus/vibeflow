import {affine, subtract} from "../base_lib/arithmetic.ts";
export function run(i: any, p: any) {
  return {companion: affine(i["math.x"].value, 2, 0) + 1};
}
