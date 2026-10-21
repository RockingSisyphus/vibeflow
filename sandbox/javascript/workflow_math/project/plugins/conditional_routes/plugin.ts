import {definePlugin,defineDataSchema} from "@vibeflow/plugin";
export const plugin = definePlugin({
  id: "sandbox.conditional_routes",
  resources: [
    defineDataSchema({ type_key: "sandbox.call.event", representation: "json", schema: { type: "string" } }),
    defineDataSchema({ type_key: "sandbox.call.route", representation: "json", schema: { type: "string" } }),
  ],
});
