"""Explicit task managers replacing removed concurrency call flags."""

class TaskManagement0:
    def run_pure(self, inputs, params, context):
        ref = context.tasks.start("work", {})
        return {"task": ref}

class TaskManagement1:
    def run_pure(self, inputs, params, context):
        outcome = context.tasks.wait_all_exited([inputs['task.ref.semantic_slow_async_value']["value"]])[0]
        if outcome["status"] != "succeeded":
            raise RuntimeError(outcome["error"]["message"])
        return outcome["outputs"]

class TaskManagement2:
    def run_pure(self, inputs, params, context):
        ref = context.tasks.start("work", {'train.batch': inputs['train.batch']["value"]})
        return {}

class TaskManagement3:
    def run_pure(self, inputs, params, context):
        ref = context.tasks.start("work", {})
        return {"task": ref}

class TaskManagement4:
    def run_pure(self, inputs, params, context):
        outcome = context.tasks.wait_all_exited([inputs['task.ref.sandbox_constant']["value"]])[0]
        if outcome["status"] != "succeeded":
            raise RuntimeError(outcome["error"]["message"])
        return outcome["outputs"]

class TaskManagement5:
    def run_pure(self, inputs, params, context):
        ref = context.tasks.start("work", {})
        return {}

class TaskManagement6:
    def run_pure(self, inputs, params, context):
        ref = context.tasks.start("work", {'value.in': inputs['value.in']["value"]})
        return {"task": ref}

class TaskManagement7:
    def run_pure(self, inputs, params, context):
        outcome = context.tasks.wait_all_exited([inputs['task.ref.math_add_five']["value"]])[0]
        if outcome["status"] != "succeeded":
            raise RuntimeError(outcome["error"]["message"])
        return outcome["outputs"]
