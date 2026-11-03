import {defineNode} from "@vibeflow/plugin";

export const input0=defineNode({id:"app.input.formula_jsonc",node_type:"vibeflow.node",contract:{"requires": [{"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "provides": [{"key": "app_session_input", "type": "app.session", "display_name": "Application session"}], "input_semantics": {"app.session": ["Input supplied by the application."]}, "output_semantics": {"app_session_input": ["The application input instance."]}},run(inputs,params){return {"app_session_input":inputs["app.session"].value};}});
