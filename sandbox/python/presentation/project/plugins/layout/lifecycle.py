class Compiler:
    def after_compile(self, graph, compiled):
        return None
class Runtime:
    def before_run(self, state):
        return None
def create_compiler(context):
    return Compiler()
def create_runtime(context):
    return Runtime()
