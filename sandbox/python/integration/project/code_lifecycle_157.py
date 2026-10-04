from vibeflow.targets.python.sdk import Plugin

def create(context):
    from plugins.hook_plugins import RuntimePlugin
    instance = RuntimePlugin()
    if hasattr(instance, "configure"):
        instance.configure(context["config"])
    return instance

plugin = Plugin(id='runtime_hook', runtime=create, rulesets=('vibeflow.plugin',), display_name='Runtime Hook Plugin', description='Records runtime hook calls for the plugin fixture.', version='0.1.0')
