from vibeflow.targets.python.sdk import node
from ..base_lib.local import multiply
@node(id="local.step", node_type="vibeflow.node", flow_kind="terminal", rulesets=[], base_libs=["local.math"],
 contract={"provides":[{"key":"local","type":"local.value","display_name":"Local value"}],"output_semantics":{"local":["Private result"]}})
class Local:
    def run_pure(self, inputs, params): return {"local":multiply(4)}
