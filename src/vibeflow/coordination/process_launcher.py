"""Explicit process launch adapter; registration determines workflow readiness."""
import os
from pathlib import Path
import subprocess
from threading import Thread

from .protocol import CoordinationError


class ProcessLauncher:
    def __init__(self, url, failed):
        self.url, self.failed = url, failed

    def __call__(self, item, launch, declarations):
        bases = {str(row.get('base','.')) for row in declarations}
        if len(bases) != 1:
            raise CoordinationError('VF_LAUNCH_AMBIGUOUS','launch declarations have different declaring roots')
        environment = {**os.environ, **launch['env'], 'VIBEFLOW_COORDINATION_URL':self.url(),
                       'VIBEFLOW_INSTANCE_ID':item['id']}
        process = subprocess.Popen(launch['command'],cwd=Path(bases.pop())/launch['cwd'],env=environment,
                                   start_new_session=os.name=='posix',close_fds=True,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        # Reaping is independent from workflow lifetime: a launcher may hand off.
        def reap():
            code = process.wait()
            if code:
                self.failed(item, code)
        Thread(target=reap,daemon=True,name='vibeflow-launcher-reaper').start()
