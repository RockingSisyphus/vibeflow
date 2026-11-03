from vibeflow.targets.python.sdk import node
from ..base_lib.shared import increment
@node(id="shared.step", node_type="vibeflow.node", flow_kind="terminal", rulesets=[], base_libs=["shared.math"],
 contract={"requires":[{"type":"local.value","cardinality":"exactly_one","display_name":"Local value"}],
 "provides":[{"key":"result","type":"result.value","display_name":"Result"}],"input_semantics":{"local.value":["Prepared private value"]},"output_semantics":{"result":["Shared result"]}})
class Shared:
    def run_pure(self, inputs, params): return {"result":increment(inputs["local.value"]["value"])}
