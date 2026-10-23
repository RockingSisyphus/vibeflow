import {definePlugin,defineDataSchema} from "@vibeflow/plugin";

const schemas={x:{type:"number"},y:{type:"number"},case_id:{type:"string"},
  seed:{type:"object"},local:{type:"number"},checkpoint:{type:"object"},request:{type:"object"},
  reply:{type:"object"},shift:{type:"object"},square:{type:"object"},answer:{type:"object"}};
export const plugin=definePlugin({id:"math.cooperation",resources:Object.entries(schemas).map(
  ([name,schema])=>defineDataSchema({type_key:"math."+name,schema}))});
