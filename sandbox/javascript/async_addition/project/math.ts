import {defineBaseLib} from "@vibeflow/plugin";
export const library=defineBaseLib({id:"addition.math",rulesets:["vibeflow.base_lib"],implementation(a:number,b:number):number{return a+b;}});
