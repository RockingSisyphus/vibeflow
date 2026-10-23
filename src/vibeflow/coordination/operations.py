"""Bind a native Node cancellation signal to a protocol operation."""
class Operation:
    def __init__(self, callback, signal=None):
        self.callback, self.signal = callback, signal

    def with_signal(self, signal):
        return type(self)(self.callback, signal)

    def __call__(self, request=None):
        return self.callback(request or {}, self.signal)
