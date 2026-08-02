from pathlib import Path


class DemoBoundary:
    calls: list[str] = []

    def __init__(self):
        self.run_dir = None

    def before_run(self, run_config):
        self.__class__.calls.append("before_run")
        self.run_dir = Path(run_config["run_dir"])
        return {}

    def after_run(self, outputs, run_config):
        self.__class__.calls.append("after_run")
        return {}

    def before_iteration(self, iteration, state):
        self.__class__.calls.append(f"before_iteration:{iteration}")
        return {}

    def after_iteration(self, iteration, outputs, state):
        self.__class__.calls.append(f"after_iteration:{iteration}")
        value = outputs.get("effects.request", {}).get("value", 0)
        run_dir = self.run_dir
        return {"io.result": value + iteration + 1, "artifacts": [str(run_dir / f"artifact_{iteration}.txt")]}


class FailingBoundary(DemoBoundary):
    def after_iteration(self, iteration, outputs, state):
        raise RuntimeError("boundary failed")


__all__ = [name for name in globals() if not name.startswith("__")]
