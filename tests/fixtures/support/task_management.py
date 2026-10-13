"""Explicit finite task calls for native Python runtime fixtures."""
from dataclasses import replace
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor


def task_call(node_id, type_key, description, *, join=True, **options):
    return {"id":node_id, "type_used":f"manage.{type_key}.{'join' if join else 'start'}",
            "display_name":node_id, "description":description,
            "task_targets":{"work":{"id":"execution", "type_used":type_key,
                "display_name":"Execution", "description":description, **options}}}


def register_task_manager(registry, type_key, *, join=True, requires=None, provides=None):
    descriptor=registry.descriptor(type_key) if type_key in registry.available() else None
    contract=descriptor.contract if descriptor else NodeContractDescriptor(
        requires=tuple(DataRequirement(key,"exactly_one",display_name=key) for key in requires or []),
        provides=tuple(DataProvider(key,key,display_name=key) for key in provides or []),
        input_semantics={key:("Task input",) for key in requires or []},
        output_semantics={key:("Task output",) for key in provides or []})
    if not join:contract=replace(contract,provides=(),output_semantics={})
    class Manager:
        def run_pure(self, inputs, params, context):
            values={key:[item['value'] for item in value] if isinstance(value,list) else value['value'] for key,value in inputs.items()}
            ref=context.tasks.start('work',values)
            outcome=context.tasks.wait_all_exited([ref])[0]
            if outcome['status']!='succeeded':raise RuntimeError(outcome['error']['message'])
            return outcome['outputs'] if join else {}
    registry.register(NodeDescriptor(f"manage.{type_key}.{'join' if join else 'start'}", "Task manager",
        "Starts and observes an explicit task", "1", "task_manager",contract=contract,rulesets=()),Manager)
    return registry
