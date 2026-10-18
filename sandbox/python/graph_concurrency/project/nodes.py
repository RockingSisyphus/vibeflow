from threading import Barrier
import time
barrier=Barrier(12)
class Terminal:
    def run_pure(self,inputs,params):return {}
class Worker:
    def run_pure(self,inputs,params,context):
        index=params['index'];scenario=inputs['scenario']['value']
        try:
            barrier.wait(timeout=5)
            context.trace('worker_started',{'index':index})
            if scenario=='root_failure' and index==0:raise RuntimeError('parent failed')
            if scenario in ('external_cancel','root_failure'):context.signal.wait(5)
            time.sleep((12-index)*.001)
            return {'receipt'+str(index):index}
        finally:
            time.sleep(.005);context.trace('cleanup_finished',{'index':index})
class Collect:
    def run_pure(self,inputs,params):return {'report':[item['value'] for item in inputs['receipt']]}
