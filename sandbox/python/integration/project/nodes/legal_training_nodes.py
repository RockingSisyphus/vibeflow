from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class OrdinaryCallbackWarningNode:

    def run_pure(self, inputs, params):
        callback = VALUE(inputs, 'callback.in')
        return {'value.out': callback() if callable(callback) else callback}

class TrainingInputNode:

    def run_pure(self, inputs, params):
        return {'train.model.input': VALUE(inputs, 'train.model'), 'train.batch.input': VALUE(inputs, 'train.batch'), 'train.optimizer.input': VALUE(inputs, 'train.optimizer')}

class ForwardLossNode:

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        if not hasattr(model, 'loss'):
            return {'train.loss': 1}
        return {'train.loss': model.loss(VALUE(inputs, 'train.batch'))}

class BackwardGradNode:

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        if not hasattr(model, 'grad'):
            return {'train.grad': 0.1}
        return {'train.grad': model.grad(VALUE(inputs, 'train.loss'))}

class OptimizerStepNode:

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        optimizer = VALUE(inputs, 'train.optimizer')
        if not hasattr(optimizer, 'step'):
            return {'train.model_after': model, 'train.optimizer_after': optimizer, 'train.step_report': {'steps': 1}}
        optimizer.step(model, VALUE(inputs, 'train.grad'))
        return {'train.model_after': model, 'train.optimizer_after': optimizer, 'train.step_report': {'steps': optimizer.steps, 'weight': model.weight}}

class TrainingMetricsNode:

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model_after')
        if not hasattr(model, 'weight'):
            return {'train.metrics': {'loss': VALUE(inputs, 'train.loss'), 'tags': ['train']}}
        return {'train.metrics': {'loss': VALUE(inputs, 'train.loss'), 'tags': {'sandbox', 'train'}, 'unstable': float('nan'), 'model': model}}

class TrainingBatchStepNode:

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        batch = VALUE(inputs, 'train.batch')
        optimizer = VALUE(inputs, 'train.optimizer')
        loss = model.loss(batch) if hasattr(model, 'loss') else 1
        grad = model.grad(loss) if hasattr(model, 'grad') else 0.1
        if hasattr(optimizer, 'step'):
            optimizer.step(model, grad)
            report = {'steps': optimizer.steps, 'weight': model.weight}
        else:
            report = {'steps': 1}
        metrics = {'loss': loss, 'tags': {'sandbox', 'train'}, 'unstable': float('nan'), 'model': model}
        return {'train.model_after': model, 'train.optimizer_after': optimizer, 'train.step_report': report, 'train.loss': loss, 'train.metrics': metrics}

class BatchMetricsNode:

    def run_pure(self, inputs, params):
        batch = VALUE(inputs, 'train.batch')
        if isinstance(batch, dict):
            return {'train.metrics': {'size': 1}}
        items = batch.items if hasattr(batch, 'items') and (not isinstance(batch, dict)) else [1]
        return {'train.metrics': {'items': set(items), 'unstable': float('nan'), 'batch': batch}}

class TrainingMetricsEndNode:

    def run_pure(self, inputs, params):
        return {}
