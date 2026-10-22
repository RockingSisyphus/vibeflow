// Copy alongside release-generated interfaces.mjs into plugins/workflow_protocol/.
import {definePlugin,defineCapability,defineDataSchema} from "@vibeflow/plugin";
import {capabilities,schemas} from "./interfaces.mjs";

export const resources=[...capabilities.map(defineCapability),...Object.entries(schemas).map(([type_key,schema])=>defineDataSchema({type_key,schema})),
  ...["instance","payload","message","result"].map(key=>defineDataSchema({type_key:"example."+key,schema:key==="instance"?{type:"string"}:{}}))];

export const plugin=definePlugin({id:"example.workflow.protocol",resources});
