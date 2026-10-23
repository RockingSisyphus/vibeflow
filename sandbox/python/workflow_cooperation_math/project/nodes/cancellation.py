"""Explicit cancellation branch and a real asynchronous second-round cleanup."""
import asyncio
from vibeflow.targets.python.sdk import node



@node(id="math.choose",node_type="vibeflow.node",flow_kind="decision",rulesets=["vibeflow.process"],contract={
    "requires":[{"type":"math.seed","cardinality":"exactly_one","display_name":"Seed"}],
    "provides":[{"key":"stop_route","type":"math.stop","display_name":"Stop"}],
    "input_semantics":{"math.seed":["Requested execution path"]},"output_semantics":{"stop_route":["Choose explicit Kill or normal continuation"]}})
class Choose:
    def run_pure(self,inputs,params):
        return {"stop_route":inputs["math.seed"]["value"]["stop"]}


@node(**{'id': 'math.ready_to_kill',
 'node_type': 'vibeflow.node',
 'flow_kind': 'workflow-io',
 'rulesets': ['vibeflow.process',
              {'rule_id': 'vibeflow.capability.allow',
               'params': {'capability': 'vibeflow.workflow', 'operations': ['receive']}}],
 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['receive']}],
 'contract': {'requires': [{'type': 'math.seed',
                            'cardinality': 'exactly_one',
                            'display_name': 'math.seed'},
                           {'type': 'example.instance',
                            'cardinality': 'exactly_one',
                            'display_name': 'example.instance'}],
              'provides': [],
              'input_semantics': {'math.seed': ['Cancellation protocol input'],
                                  'example.instance': ['Cancellation protocol input']},
              'output_semantics': {},
              'params_schema': {'expected_workflows': {'type': 'array', 'items': {'type': 'object'}}},
              'params_defaults': {'expected_workflows': []}}})
class ReadyToKill:
    async def run_pure(self,inputs,params,context):
        message=await context.capabilities["vibeflow.workflow"]["receive"]({"port":"ready"})
        assert message["sender"]==inputs["example.instance"]["value"]
        assert message["payload"]["case_id"]==inputs["math.seed"]["value"]["case_id"]
        return {}


@node(**{'id': 'math.receive_next',
 'node_type': 'vibeflow.node',
 'flow_kind': 'workflow-io',
 'rulesets': ['vibeflow.process',
              {'rule_id': 'vibeflow.capability.allow',
               'params': {'capability': 'vibeflow.workflow', 'operations': ['send', 'receive']}}],
 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['send', 'receive']}],
 'contract': {'requires': [{'type': 'math.request',
                            'cardinality': 'exactly_one',
                            'display_name': 'math.request'},
                           {'type': 'math.reply',
                            'cardinality': 'exactly_one',
                            'display_name': 'math.reply'}],
              'provides': [{'key': 'message', 'type': 'example.message', 'display_name': 'message'}],
              'input_semantics': {'math.request': ['Cancellation protocol input'],
                                  'math.reply': ['Cancellation protocol input']},
              'output_semantics': {'message': ['Cancellation protocol result']},
              'params_schema': {'expected_workflows': {'type': 'array', 'items': {'type': 'object'}}},
              'params_defaults': {'expected_workflows': []}}})
class ReceiveNext:
    async def run_pure(self,inputs,params,context):
        request,reply=(inputs[k]["value"] for k in ("math.request","math.reply"))
        api=context.capabilities["vibeflow.workflow"]
        try:
            api["send"]({"id":request["a_id"],"port":"ready","payload":{"case_id":request["case_id"]}})
            return {"message":await api["receive"]({})}
        finally:
            await asyncio.sleep(.01)
            api["send"]({"id":request["a_id"],"port":"cleanup","payload":{
                "case_id":request["case_id"],"c_id":reply["c_id"],"cleanup":"finished"}})


@node(**{'id': 'math.cancelled',
 'node_type': 'vibeflow.node',
 'flow_kind': 'workflow-io',
 'rulesets': ['vibeflow.process',
              {'rule_id': 'vibeflow.capability.allow',
               'params': {'capability': 'vibeflow.workflow', 'operations': ['receive']}}],
 'capabilities': [{'id': 'vibeflow.workflow', 'operations': ['receive']}],
 'contract': {'requires': [{'type': 'math.seed',
                            'cardinality': 'exactly_one',
                            'display_name': 'math.seed'},
                           {'type': 'example.result',
                            'cardinality': 'exactly_one',
                            'display_name': 'example.result'}],
              'provides': [{'key': 'answer', 'type': 'math.answer', 'display_name': 'answer'}],
              'input_semantics': {'math.seed': ['Cancellation protocol input'],
                                  'example.result': ['Cancellation protocol input']},
              'output_semantics': {'answer': ['Cancellation protocol result']},
              'params_schema': {'expected_workflows': {'type': 'array', 'items': {'type': 'object'}}},
              'params_defaults': {'expected_workflows': []}}})
class Cancelled:
    async def run_pure(self,inputs,params,context):
        seed,status=(inputs[k]["value"] for k in ("math.seed","example.result"))
        assert status["state"]=="cancelled" and status["outputs"] is None
        # Zero timeout checks that cleanup already handed off its message.
        message=await context.capabilities["vibeflow.workflow"]["receive"]({"port":"cleanup","timeout":0})
        assert message["sender"]==status["id"] and message["payload"]["case_id"]==seed["case_id"]
        assert message["payload"]["cleanup"]=="finished"
        return {"answer":{"status":"cancelled","case_id":seed["case_id"],"cleanup":"finished", "identities":{
            "a":context.workflow.self()["id"],"b":status["id"],"c":message["payload"]["c_id"]}}}


