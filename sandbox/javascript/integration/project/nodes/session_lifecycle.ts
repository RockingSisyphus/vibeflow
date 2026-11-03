import {defineNode} from "@vibeflow/plugin";
export const windowOpen=defineNode({id:"sandbox.window_open",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{"requires": [{"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "input_semantics": {"app.session": ["Application-owned event queue or API instance."]}},
 rulesets:["vibeflow.document"],
 run(inputs,params,context){(inputs as any)["app.session"].value.window_session.open(null);return {};}});
export const windowClose=defineNode({id:"sandbox.window_close",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{"requires": [{"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "input_semantics": {"app.session": ["Application-owned event queue or API instance."]}},
 rulesets:["vibeflow.document"],
 run(inputs,params,context){(inputs as any)["app.session"].value.window_session.close(null);return {};}});
export const mathOpen=defineNode({id:"sandbox.math_open",node_type:"sandbox.lifecycle",flow_kind:"io",
 contract:{"requires": [{"type": "sandbox.number", "cardinality": "exactly_one", "display_name": "Number"}, {"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "provides": [{"key":"application","type":"app.session","display_name":"Application"},{"key": "opened_x", "type": "sandbox.number", "display_name": "Number"}], "input_semantics": {"sandbox.number": ["Value passed into the opened math session"], "app.session": ["Application-owned event queue or API instance."]}, "output_semantics": {"application":["Opened application instance"],"opened_x": ["Unchanged value for the calculation"]}},
 rulesets:["vibeflow.python_io"],
 run(inputs,params,context){(inputs as any)["app.session"].value.math_session.open(null);return {application:(inputs as any)["app.session"].value,opened_x:inputs["sandbox.number"].value};}});
export const mathClose=defineNode({id:"sandbox.math_close",node_type:"sandbox.lifecycle",flow_kind:"io",contract:{"requires": [{"type": "app.session", "cardinality": "exactly_one", "display_name": "Application session"}], "input_semantics": {"app.session": ["Application-owned event queue or API instance."]}},
 rulesets:["vibeflow.python_io"],
 run(inputs,params,context){(inputs as any)["app.session"].value.math_session.close(null);return {};}});
