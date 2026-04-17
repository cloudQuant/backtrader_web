"""Deprecation decorator for marking deprecated functions."""

import warnings
from functools import wraps

__all__ = ["deprecated"]


def deprecated(msg=None, stacklevel=2):
    """
    Used to mark a function as deprecated.
    Parameters
    ----------
    msg : str
        The message to display in the deprecation warning.
    stacklevel : int
        How far up the stack the warning needs to go, before
        showing the relevant calling lines.
    -----
    @deprecated(msg='function_a is deprecated! Use function_b instead.')
    def function_a(*args, **kwargs):
    """

    def deprecated_dec(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            warnings.warn(
                msg or "Function %s is deprecated." % fn.__name__, category=DeprecationWarning, stacklevel=stacklevel
            )
            return fn(*args, **kwargs)

        return wrapper

    return deprecated_dec
