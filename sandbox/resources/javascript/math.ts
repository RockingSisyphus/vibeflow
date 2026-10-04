import {defineBaseLib} from "@vibeflow/plugin";
import {add} from "./math_support.ts";
export const library=defineBaseLib({id:"demo.math",implementation_files:["math_support.ts"],rulesets:["vibeflow.base_lib"],presentation:{fill:"#c8e4ff",shape:"cyl",icon:"Σ"},implementation(value:number):number{return add(value,1);}});
