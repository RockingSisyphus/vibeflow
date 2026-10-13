"""Native background work is governed independently of I/O permission."""
from pathlib import Path
import pytest
from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project.sources import analyze_node_source_context
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules


@pytest.mark.parametrize('body, forbidden', [
    ('thread=th.Thread(target=lambda:None)\nthread.start()',True),
    ('thread=th.Thread(target=lambda:None)\ntry: thread.start()\nfinally: thread.join()',False),
    ('thread=th.Thread(target=lambda:None)\ntry: thread.start()\nfinally: thread.join(timeout=0)',True),
    ('with futures.ThreadPoolExecutor() as pool:\n    pool.submit(lambda:None)',False),
    ('pool=futures.ThreadPoolExecutor()\npool.submit(lambda:None)',True),
    ('pool=futures.ThreadPoolExecutor()\ntry: pool.submit(lambda:None)\nfinally: pool.shutdown(wait=True)',False),
    ('class Local:\n    def start(self):return 1\nthread=Local()\nthread.start()',False),
])
def test_native_work_ownership_uses_bindings_and_actual_join_contract(tmp_path,body,forbidden):
    source='import threading as th\nimport concurrent.futures as futures\nclass Work:\n    def run_pure(self,inputs,params):\n'+''.join('        '+line+'\n' for line in body.splitlines())+'        return {}\n'
    path=tmp_path/'node.py';path.write_text(source)
    registry=native_registry()
    registry.register(NodeDescriptor('fixture.work','Work','Ownership fixture','1','process',contract=NodeContractDescriptor(),rulesets=('vibeflow.document',)),source={'path':str(path),'symbol':'Work'})
    registry.source_locations={'fixture.work':(path,'Work','fixture',tmp_path)}
    registry.source_roots=(tmp_path,);registry.source_root_ids={tmp_path:'fixture'}
    context=analyze_node_source_context(registry,('fixture.work',))
    result=execute_python_node_rules(registry,context,phase='static')
    codes={item.rule_id for item in result.findings}
    assert ('VF_NODE_RESOURCE_UNOWNED' in codes) is forbidden,result.findings
