from __future__ import annotations

class OpenFileNode:

    def run_pure(self, inputs, params):
        open('x.txt', 'w')
        return {'bad.out': 1}

class PathReadTextNode:

    def run_pure(self, inputs, params):
        from pathlib import Path
        Path('x.txt').read_text()
        return {'bad.out': 1}

class OsGetenvNode:

    def run_pure(self, inputs, params):
        import os
        os.getenv('HOME')
        return {'bad.out': 1}

class SubprocessNode:

    def run_pure(self, inputs, params):
        import subprocess
        subprocess.run(['python', '--version'])
        return {'bad.out': 1}

class SocketNode:

    def run_pure(self, inputs, params):
        import socket
        socket.socket()
        return {'bad.out': 1}

class RequestsNode:

    def run_pure(self, inputs, params):
        import requests
        requests.get('https://example.com')
        return {'bad.out': 1}

class SqliteNode:

    def run_pure(self, inputs, params):
        import sqlite3
        sqlite3.connect(':memory:')
        return {'bad.out': 1}

class EvalNode:

    def run_pure(self, inputs, params):
        eval('1 + 1')
        return {'bad.out': 1}

class DynamicImportNode:

    def run_pure(self, inputs, params):
        import importlib
        importlib.import_module('math')
        return {'bad.out': 1}
