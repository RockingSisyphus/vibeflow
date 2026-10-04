from vibeflow.targets.python.sdk import Plugin

def create(context):
    from plugins.hook_plugins import CompilerPlugin
    instance = CompilerPlugin()
    if hasattr(instance, "configure"):
        instance.configure(context["config"])
    return instance

plugin = Plugin(id='compiler_hook', compiler=create, rulesets=('vibeflow.plugin',), display_name='Compiler Hook Plugin', description='Records compiler hook calls for the plugin fixture.', version='0.1.0')
