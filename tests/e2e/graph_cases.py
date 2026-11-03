"""Declared graph variants and a business-operation log oracle."""
from copy import deepcopy
import json

SUCCESS_CASES = (('concurrent', 'success', None), ('capacity-four', 'queue4', 4), ('default-eight', 'queue8', 8))

TOPOLOGY_CASES = {'collector-dispatch': ('GRAPH.JOIN.FORK_CONFLICT', 'error'), 'disconnected-worker': ('GRAPH.FLOW.CANNOT_REACH_END', 'error')}

def write_cases(work):
    """Derive small, inspectable variants without maintaining duplicate graphs."""
    directory = work / 'project/configs'
    original = json.loads((directory / 'concurrent.jsonc').read_text())
    for name, limit in (('capacity-four', 4), ('default-eight', None)):
        data = deepcopy(original)
        start = data['pipeline']['nodes'][0]
        if limit is None:
            start.pop('config', None)
        else:
            start['config'] = {'max_concurrency': limit}
        (directory / f'{name}.jsonc').write_text(json.dumps(data, indent=2) + '\n')
    for name in TOPOLOGY_CASES:
        data = deepcopy(original)
        graph = data['pipeline']
        if name == 'disconnected-worker':
            graph['edges'].remove(['w11', 'collect'])
        else:
            keep = {'start', 'w0', 'w1', 'w2', 'w3', 'w4', 'collect', 'end'}
            graph['nodes'] = [node for node in graph['nodes'] if node['id'] in keep]
            for node in graph['nodes']:
                if node['id'] not in {'start', 'end'}:
                    node['definition_id'] = 'native.noop'
            graph['outputs'] = []
            next((node for node in graph['nodes'] if node['id'] == 'w0'))['join_policy'] = 'all'
            graph['edges'] = [['start', 'w1'], ['start', 'w2'], ['w1', 'w0'], ['w2', 'w0'], ['w0', 'w3'], ['w0', 'w4'], ['w3', 'collect'], ['w4', 'collect'], ['collect', 'end']]
        (directory / f'{name}.jsonc').write_text(json.dumps(data, indent=2) + '\n')

def assert_worker_trace(events, capacity=None):
    """Count real starts/exits and require refill before the first batch drains."""
    active, started, finished = (set(), [], [])
    peak = collectors = 0
    for event in events:
        kind = event.get('event') if event.get('kind') == 'node_trace' else event.get('kind')
        if kind == 'collector_started':
            assert not active and len(finished) == 12, (active, finished)
            collectors += 1
        if kind not in {'worker_started', 'cleanup_finished'}:
            continue
        index = event['details']['index']
        if kind == 'worker_started':
            assert index not in started, started
            if capacity is not None and index == capacity:
                assert finished == [capacity - 1], (started, finished)
                assert active == set(range(capacity - 1)), active
            active.add(index)
            started.append(index)
            peak = max(peak, len(active))
            if capacity is not None:
                assert peak <= capacity, (peak, capacity)
        else:
            assert index in active, (index, active)
            active.remove(index)
            finished.append(index)
    assert sorted(started) == sorted(finished) == list(range(12)), (started, finished)
    assert not active and collectors == 1, (active, collectors)
    if capacity is not None:
        assert peak == capacity, (peak, capacity)
    return {'workers': 12, 'peak': peak, 'collectors': collectors, 'incremental_refill': capacity is not None}
