import inspect
import builtins
from typing import Callable
import types

from peval.tags import get_pure_tag


_PURE_METHODS = {
    "__abs__",
    "__add__",
    "__and__",
    "__bool__",
    "__bool__",
    "__bytes__",
    "__ceil__",
    "__class_getitem__",
    "__complex__",
    "__contains__",
    "__dir__",
    "__eq__",
    "__float__",
    "__floor__",
    "__floordiv__",
    "__format__",
    "__ge__",
    "__get__",
    "__getattr__",
    "__getattribute__",
    "__getitem__",
    "__gt__",
    "__hash__",
    "__index__",
    "__init__",
    "__instancecheck__",
    "__int__",
    "__invert__",
    "__iter__",
    "__le__",
    "__len__",
    "__length_hint__",
    "__lshift__",
    "__lt__",
    "__matmul__",
    "__missing__",
    "__mod__",
    "__mul__",
    "__ne__",
    "__neg__",
    "__or__",
    "__pos__",
    "__pow__",
    "__radd__",
    "__rand__",
    "__repr__",
    "__reversed__",
    "__rfloordiv__",
    "__rlshift__",
    "__rmatmul__",
    "__rmod__",
    "__rmul__",
    "__ror__",
    "__round__",
    "__rpow__",
    "__rrshift__",
    "__rshift__",
    "__rsub__",
    "__rtruediv__",
    "__rxor__",
    "__str__",
    "__sub__",
    "__subclasscheck__",
    "__truediv__",
    "__trunc__",
    "__xor__",
}

_IMPURE_BUILTINS = {delattr, setattr, eval, exec, input, print, next, open}

_BUILTIN_PURE_CALLABLES = set()
for name in dir(builtins):
    builtin = getattr(builtins, name)
    if type(builtin) == type:
        for method in _PURE_METHODS:
            if hasattr(builtin, method):
                _BUILTIN_PURE_CALLABLES.add(getattr(builtin, method))
    elif callable(builtin) and builtin not in _IMPURE_BUILTINS:
        _BUILTIN_PURE_CALLABLES.add(builtin)


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
