from .scalar import multiply

def affine(value, gain, shift):
    return multiply(value + shift, gain)

def subtract(value, amount):
    return value - amount
