from threading import Barrier, Condition
import time
barrier=Barrier(12)
queue_condition = Condition()
queue_started = set()


def queue_admission(index, capacity):
    # Hold every first-batch worker except the last until a queued call starts.
    # A scheduler that waits for the whole batch will time out instead of passing.
    with queue_condition:
        queue_started.add(index)
        queue_condition.notify_all()
        assert queue_condition.wait_for(lambda: len(queue_started) >= capacity, timeout=5)
        if index < capacity - 1:
            assert queue_condition.wait_for(lambda: capacity in queue_started, timeout=5)


class Terminal:
    def run_pure(self,inputs,params):return {}
class Worker:
    def run_pure(self,inputs,params,context):
        index=params['index'];scenario=inputs['scenario']['value']
        try:
            if scenario in ('queue4', 'queue8'):
                context.trace('worker_started',{'index':index})
                queue_admission(index, int(scenario[5:]))
            else:
                barrier.wait(timeout=5)
                context.trace('worker_started',{'index':index})
            if scenario=='root_failure' and index==0:raise RuntimeError('parent failed')
            if scenario in ('external_cancel','root_failure'):context.signal.wait(5)
            time.sleep((12-index)*.001)
            return {'receipt'+str(index):index}
        finally:
            time.sleep(.005);context.trace('cleanup_finished',{'index':index})
class Collect:
    def run_pure(self,inputs,params,context):
        context.trace('collector_started',{})
        with queue_condition:
            queue_started.clear()
        return {'report':[item['value'] for item in inputs['receipt']]}
