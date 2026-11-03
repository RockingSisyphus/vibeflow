from vibeflow.targets.python.sdk import node

@node(id='app.input.formula_jsonc',node_type="vibeflow.node",contract={'requires': [{'type': 'app.session', 'cardinality': 'exactly_one', 'display_name': 'Application session'}], 'provides': [{'key': 'app_session_input', 'type': 'app.session', 'display_name': 'Application session'}], 'input_semantics': {'app.session': ['Input supplied by the application.']}, 'output_semantics': {'app_session_input': ['The application input instance.']}})
class Input0:
    def run_pure(self, inputs, params):
        return {'app_session_input':inputs['app.session']["value"]}
