from __future__ import annotations

class GlobalStateFileNode:

    def run_pure(self, inputs, params):
        del inputs, params
        with open('forbidden.txt', 'w', encoding='utf-8') as handle:
            handle.write('forbidden')
        return {'bad.out': 1}

class GlobalStateEnvironmentNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import os
        return {'bad.out': int(bool(os.getenv('FORBIDDEN')))}

class GlobalStateNetworkNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import socket
        return {'bad.out': int(socket.gethostname() == '')}

class GlobalStateSubprocessNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import subprocess
        subprocess.run(('true',), check=True)
        return {'bad.out': 1}

class GlobalStateThreadNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import threading
        worker = threading.Thread(target=lambda: None)
        worker.start()
        worker.join()
        return {'bad.out': 1}

class GlobalStateEvalNode:

    def run_pure(self, inputs, params):
        del inputs, params
        return {'bad.out': eval('1')}

class GlobalStateDynamicImportNode:

    def run_pure(self, inputs, params):
        del inputs, params
        module = __import__('math')
        return {'bad.out': int(module.sqrt(1))}

class GlobalStateFfiNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import ctypes
        return {'bad.out': int(ctypes.sizeof(ctypes.c_int))}

class GlobalStateCffiNode:

    def run_pure(self, inputs, params):
        del inputs, params
        import cffi
        return {'bad.out': int(cffi.FFI() is not None)}
