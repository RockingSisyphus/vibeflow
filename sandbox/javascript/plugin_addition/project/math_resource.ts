import {defineBaseLib} from "@vibeflow/plugin";
import {add} from "./math_support.ts";
export const library = defineBaseLib({id:"addition.math", implementation_files:["math_support.ts"], rulesets:["vibeflow.base_lib"], implementation(a:number,b:number){return add(a,b);}});
