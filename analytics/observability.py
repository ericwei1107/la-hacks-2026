from functools import wraps

import sentry_sdk


def traced(op):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            with sentry_sdk.start_span(op=op, name=function.__qualname__):
                return function(*args, **kwargs)
        return run
    return decorate
