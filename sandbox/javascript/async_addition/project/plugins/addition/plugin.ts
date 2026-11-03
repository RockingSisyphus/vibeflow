import {definePlugin,defineDataSchema} from "@vibeflow/plugin";
import {library} from "./math.ts";

export const a=defineDataSchema({type_key:"addition.a",schema:{type:"number"}});
export const b=defineDataSchema({type_key:"addition.b",schema:{type:"number"}});
export const result=defineDataSchema({type_key:"addition.result",schema:{type:"number"}});
export const key=defineDataSchema({type_key:"addition.key",schema:{type:"string"}});
export const pair=defineDataSchema({type_key:"addition.pair",schema:{type:"object",properties:{a:{type:"number"},b:{type:"number"}},required:["a","b"],additionalProperties:false}});

export const resource_1000 = defineDataSchema({"type_key":"app.session","schema":{}});
export const plugin=definePlugin({id:"addition.async",resources:[resource_1000,library,a,b,result,key,pair]});
