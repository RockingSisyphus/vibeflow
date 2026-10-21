from base_lib.sandbox_arithmetic import add as resource_add, subtract as resource_subtract, multiply as resource_multiply, divide as resource_divide
from plugins.value_shift.plugin import private_math

class ResourceArithmeticNode:

    def run_pure(self, inputs, params):
        value = resource_add(inputs['calc.sum']['value'], params.get('addend', 0))
        value = resource_multiply(value, params.get('multiplier', 1))
        value = resource_subtract(value, params.get('subtrahend', 0))
        value = resource_divide(value, params.get('divisor', 1))
        return {'calc.resource': private_math(value)}
