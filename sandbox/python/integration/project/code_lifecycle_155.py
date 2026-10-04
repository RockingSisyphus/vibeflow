from vibeflow.targets.python.sdk import Plugin

def create(context):
    from plugins.value_plugin import ValueShiftPlugin
    instance = ValueShiftPlugin()
    if hasattr(instance, "configure"):
        instance.configure(context["config"])
    return instance

plugin = Plugin(id='value_shift', runtime=create, rulesets=('vibeflow.plugin',), display_name='Sandbox Value Shift', description='Runtime plugin that shifts sandbox values during resource fixture execution.', version='0.1.0')
