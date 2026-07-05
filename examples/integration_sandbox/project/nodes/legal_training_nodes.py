from __future__ import annotations
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

def REQ(data_type: str, cardinality: str='exactly_one') -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)

def PROV(key: str, data_type: str | None=None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class TrainingInputNode:
    NODE_INFO = NodeInfo('sandbox.training_input', 'Training Input', 'training', 'Reads model, batch, and optimizer objects.', '0.1.0', 'io')
    CONTRACT = NodeContract(requires=(REQ('train.model'), REQ('train.batch'), REQ('train.optimizer')), provides=(PROV('train.model.input', 'train.model'), PROV('train.batch.input', 'train.batch'), PROV('train.optimizer.input', 'train.optimizer')), input_semantics={'train.model': ('arbitrary model object',), 'train.batch': ('arbitrary batch object',), 'train.optimizer': ('arbitrary optimizer object',)}, output_semantics={'train.model.input': ('pass-through model object',), 'train.batch.input': ('pass-through batch object',), 'train.optimizer.input': ('pass-through optimizer object',)}, output_schema={'train.model.input': {'type': 'object'}, 'train.batch.input': {'type': 'object'}, 'train.optimizer.input': {'type': 'object'}}, examples=({'inputs': {'train.model': {'key': 'train.model', 'type': 'train.model', 'value': {}, 'source_node': 'example'}, 'train.batch': {'key': 'train.batch', 'type': 'train.batch', 'value': {}, 'source_node': 'example'}, 'train.optimizer': {'key': 'train.optimizer', 'type': 'train.optimizer', 'value': {}, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {'train.model.input': VALUE(inputs, 'train.model'), 'train.batch.input': VALUE(inputs, 'train.batch'), 'train.optimizer.input': VALUE(inputs, 'train.optimizer')}

class ForwardLossNode:
    NODE_INFO = NodeInfo('sandbox.forward_loss', 'Forward Loss', 'training', 'Computes a loss from model and batch objects.', '0.1.0', 'process')
    CONTRACT = NodeContract(requires=(REQ('train.model'), REQ('train.batch')), provides=(PROV('train.loss'),), input_semantics={'train.model': ('model object',), 'train.batch': ('batch object',)}, output_semantics={'train.loss': ('numeric loss',)}, output_schema={'train.loss': {'type': 'number'}}, examples=({'inputs': {'train.model': {'key': 'train.model', 'type': 'train.model', 'value': {}, 'source_node': 'example'}, 'train.batch': {'key': 'train.batch', 'type': 'train.batch', 'value': {}, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        if not hasattr(model, 'loss'):
            return {'train.loss': 1}
        return {'train.loss': model.loss(VALUE(inputs, 'train.batch'))}

class BackwardGradNode:
    NODE_INFO = NodeInfo('sandbox.backward_grad', 'Backward Grad', 'training', 'Computes a gradient from the loss.', '0.1.0', 'process')
    CONTRACT = NodeContract(requires=(REQ('train.model'), REQ('train.loss')), provides=(PROV('train.grad'),), input_semantics={'train.model': ('model object',), 'train.loss': ('numeric loss',)}, output_semantics={'train.grad': ('numeric gradient',)}, output_schema={'train.grad': {'type': 'number'}}, examples=({'inputs': {'train.model': {'key': 'train.model', 'type': 'train.model', 'value': {}, 'source_node': 'example'}, 'train.loss': {'key': 'train.loss', 'type': 'train.loss', 'value': 1, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        if not hasattr(model, 'grad'):
            return {'train.grad': 0.1}
        return {'train.grad': model.grad(VALUE(inputs, 'train.loss'))}

class OptimizerStepNode:
    NODE_INFO = NodeInfo('sandbox.optimizer_step', 'Optimizer Step', 'training', 'Mutates model through an optimizer and returns the same objects.', '0.1.0', 'process')
    CONTRACT = NodeContract(requires=(REQ('train.model'), REQ('train.optimizer'), REQ('train.grad')), provides=(PROV('train.model_after'), PROV('train.optimizer_after'), PROV('train.step_report')), input_semantics={'train.model': ('model object',), 'train.optimizer': ('optimizer object',), 'train.grad': ('numeric gradient',)}, output_semantics={'train.model_after': ('same model object after step',), 'train.optimizer_after': ('same optimizer object after step',), 'train.step_report': ('small JSON-safe training report',)}, output_schema={'train.model_after': {'type': 'object'}, 'train.optimizer_after': {'type': 'object'}, 'train.step_report': {'type': 'object'}}, examples=({'inputs': {'train.model': {'key': 'train.model', 'type': 'train.model', 'value': {}, 'source_node': 'example'}, 'train.optimizer': {'key': 'train.optimizer', 'type': 'train.optimizer', 'value': {}, 'source_node': 'example'}, 'train.grad': {'key': 'train.grad', 'type': 'train.grad', 'value': 0.1, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model')
        optimizer = VALUE(inputs, 'train.optimizer')
        if not hasattr(optimizer, 'step'):
            return {'train.model_after': model, 'train.optimizer_after': optimizer, 'train.step_report': {'steps': 1}}
        optimizer.step(model, VALUE(inputs, 'train.grad'))
        return {'train.model_after': model, 'train.optimizer_after': optimizer, 'train.step_report': {'steps': optimizer.steps, 'weight': model.weight}}

class TrainingMetricsNode:
    NODE_INFO = NodeInfo('sandbox.training_metrics', 'Training Metrics', 'training', 'Emits non-JSON metrics without snapshotting values.', '0.1.0', 'process')
    CONTRACT = NodeContract(requires=(REQ('train.model_after'), REQ('train.loss')), provides=(PROV('train.metrics'),), input_semantics={'train.model_after': ('model object',), 'train.loss': ('numeric loss',)}, output_semantics={'train.metrics': ('metrics object containing non-JSON values',)}, output_schema={'train.metrics': {'type': 'object'}}, examples=({'inputs': {'train.model_after': {'key': 'train.model_after', 'type': 'train.model_after', 'value': {}, 'source_node': 'example'}, 'train.loss': {'key': 'train.loss', 'type': 'train.loss', 'value': 1, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        model = VALUE(inputs, 'train.model_after')
        if not hasattr(model, 'weight'):
            return {'train.metrics': {'loss': VALUE(inputs, 'train.loss'), 'tags': ['train']}}
        return {'train.metrics': {'loss': VALUE(inputs, 'train.loss'), 'tags': {'sandbox', 'train'}, 'unstable': float('nan'), 'model': model}}

class TrainingBatchStepNode:
    NODE_INFO = NodeInfo('sandbox.training_batch_step', 'Training Batch Step', 'training', 'Runs one full training batch update for block-compiled loop bodies.', '0.1.0', 'process')
    CONTRACT = NodeContract(
        requires=(REQ('train.model'), REQ('train.batch'), REQ('train.optimizer')),
        provides=(PROV('train.model_after'), PROV('train.optimizer_after'), PROV('train.step_report'), PROV('train.loss'), PROV('train.metrics')),
        input_semantics={'train.model': ('model object',), 'train.batch': ('batch object',), 'train.optimizer': ('optimizer object',)},
        output_semantics={
            'train.model_after': ('same model object after step',),
            'train.optimizer_after': ('same optimizer object after step',),
            'train.step_report': ('small JSON-safe training report',),
            'train.loss': ('numeric loss',),
            'train.metrics': ('metrics object containing non-JSON values',),
        },
        output_schema={'train.model_after': {'type': 'object'}, 'train.optimizer_after': {'type': 'object'}, 'train.step_report': {'type': 'object'}, 'train.loss': {'type': 'number'}, 'train.metrics': {'type': 'object'}},
        examples=({'inputs': {'train.model': {'key': 'train.model', 'type': 'train.model', 'value': {}, 'source_node': 'example'}, 'train.batch': {'key': 'train.batch', 'type': 'train.batch', 'value': {}, 'source_node': 'example'}, 'train.optimizer': {'key': 'train.optimizer', 'type': 'train.optimizer', 'value': {}, 'source_node': 'example'}}, 'params': {}},),
    )

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
    NODE_INFO = NodeInfo('sandbox.batch_metrics', 'Batch Metrics', 'training', 'Emits metrics directly from a non-JSON batch object.', '0.1.0', 'process')
    CONTRACT = NodeContract(requires=(REQ('train.batch'),), provides=(PROV('train.metrics'),), input_semantics={'train.batch': ('batch object',)}, output_semantics={'train.metrics': ('non-JSON metrics',)}, output_schema={'train.metrics': {'type': 'object'}}, examples=({'inputs': {'train.batch': {'key': 'train.batch', 'type': 'train.batch', 'value': {}, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        batch = VALUE(inputs, 'train.batch')
        if isinstance(batch, dict):
            return {'train.metrics': {'size': 1}}
        items = batch.items if hasattr(batch, 'items') and (not isinstance(batch, dict)) else [1]
        return {'train.metrics': {'items': set(items), 'unstable': float('nan'), 'batch': batch}}

class TrainingMetricsEndNode:
    NODE_INFO = NodeInfo('sandbox.training_metrics_end', 'Training Metrics End', 'training', 'Ends after training metrics are available.', '0.1.0', 'terminal')
    CONTRACT = NodeContract(requires=(REQ('train.metrics'),), input_semantics={'train.metrics': ('training metrics',)}, examples=({'inputs': {'train.metrics': {'key': 'train.metrics', 'type': 'train.metrics', 'value': {'loss': 1}, 'source_node': 'example'}}, 'params': {}},))

    def run_pure(self, inputs, params):
        return {}
