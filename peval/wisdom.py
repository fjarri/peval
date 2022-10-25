import operator
import inspect
import builtins
from typing import Callable
import types

from peval.tags import get_pure_tag


_KNOWN_OPERATORS = {
    operator.pos,
    operator.neg,
    operator.not_,
    operator.invert,
    operator.add,
    operator.sub,
    operator.mul,
    operator.truediv,
    operator.floordiv,
    operator.mod,
    operator.pow,
    operator.lshift,
    operator.rshift,
    operator.or_,
    operator.xor,
    operator.and_,
    operator.eq,
    operator.ne,
    operator.lt,
    operator.le,
    operator.gt,
    operator.ge,
    operator.is_,
    operator.is_not,
}

_IMPURE_BUILTINS = {delattr, setattr, eval, exec, input, print, next, open}
_BUILTIN_PURE_CALLABLES = _KNOWN_OPERATORS
for name in dir(builtins):
    builtin = getattr(builtins, name)
    if type(builtin) == type:
        _BUILTIN_PURE_CALLABLES.add(builtin.__init__)
    elif callable(builtin) and builtin not in _IMPURE_BUILTINS:
        _BUILTIN_PURE_CALLABLES.add(builtin)
for tp in (int, float, str, bytes, bool):
    for name in dir(tp):
        method = getattr(tp, name)
        if callable(method):
            _BUILTIN_PURE_CALLABLES.add(method)


def is_pure_callable(callable_) -> bool:

    if type(callable_) == type:
        # A regular class or a builtin type
        unbound_callable = callable_.__init__
    elif type(callable_) == types.FunctionType:
        unbound_callable = callable_
    elif type(callable_) == types.BuiltinFunctionType:
        # A builtin function (e.g. `isinstance`)
        unbound_callable = callable_
    elif type(callable_) == types.WrapperDescriptorType:
        # An unbound method of some builtin classes (e.g. `str.__getitem__`)
        unbound_callable = callable_
    elif type(callable_) == types.MethodWrapperType:
        # An bound method of some builtin classes (e.g. `"a".__getitem__`)
        unbound_callable = getattr(callable_.__objclass__, callable_.__name__)
    elif type(callable_) == types.MethodType:
        unbound_callable = callable_.__func__
    elif hasattr(callable_, "__call__") and callable(callable_.__call__):
        unbound_callable = callable_.__call__
    else:
        return False

    if unbound_callable in _BUILTIN_PURE_CALLABLES:
        return True

    pure_tag = get_pure_tag(unbound_callable)
    if pure_tag is not None:
        return pure_tag

    return False
