from vibeflow.targets.python.sdk import Plugin,base_lib,SourceLocator
core=base_lib(id="probe.base",source=SourceLocator(kind="file",ref="../base_lib/core.py"),rulesets=["vibeflow.base_lib"])
plugin=Plugin(id="probe.library",resources=[core])
