import {definePlugin, defineDataSchema} from "@vibeflow/plugin";
export const plugin=definePlugin({id:"example.workflow.protocol",resources:
  ["instance","payload","message","result"].map(name=>defineDataSchema({type_key:"example."+name,schema:name==="instance"?{type:"string"}:{}}))});
