from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class PrepareValueNode:

    def run_pure(self, inputs, params):
        return {'value.prepared': VALUE(inputs, 'value.in') + params.get('offset', 0)}

class ConfigureRuntimeModeNode:

    def run_pure(self, inputs, params):
        global COMPREHENSIVE_RUNTIME_MODE
        COMPREHENSIVE_RUNTIME_MODE = 'configured'
        return {'value.in.runtime': VALUE(inputs, 'value.in')}

class CoreComputeNode:

    def run_pure(self, inputs, params):
        return {'value.out': VALUE(inputs, 'value.prepared') * params.get('factor', 2)}

class RouteDecisionNode:

    def run_pure(self, inputs, params):
        return {'flow.route': 'again' if VALUE(inputs, 'value.out') < params.get('threshold', 10) else 'external'}

class LoopBackNode:

    def run_pure(self, inputs, params):
        return {'value.in.loop': VALUE(inputs, 'value.out')}

class ExternalBoostNode:

    def run_pure(self, inputs, params):
        return {'value.final': VALUE(inputs, 'value.out') + params.get('bonus', 5)}

class AuditStoreNode:

    def run_pure(self, inputs, params):
        return {'effects.request': {'final': VALUE(inputs, 'value.final')}}

class ReportDocumentNode:

    def run_pure(self, inputs, params):
        return {'document.report': f"final={VALUE(inputs, 'value.final')};request={VALUE(inputs, 'effects.request')['final']}"}

class ReportOutputNode:

    def run_pure(self, inputs, params):
        return {'io.output': VALUE(inputs, 'document.report')}

class ReportEndNode:

    def run_pure(self, inputs, params):
        return {}
