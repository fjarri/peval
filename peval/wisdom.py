import operator
import inspect
import builtins

from peval.tags import get_pure_tag


_KNOWN_SIGNATURES = {
    bool: inspect.signature(lambda obj: None),
    isinstance: inspect.signature(lambda obj, tp: None),
    getattr: inspect.signature(lambda obj, name, default=None: None),
    iter: inspect.signature(lambda obj: None),

    str.__getitem__: inspect.signature(lambda self, index: None),
    range: inspect.signature(lambda *args: None),
    repr: inspect.signature(lambda *obj: None),

    operator.pos: inspect.signature(lambda a: None),
    operator.neg: inspect.signature(lambda a: None),
    operator.not_: inspect.signature(lambda a: None),
    operator.invert: inspect.signature(lambda a: None),

    operator.add: inspect.signature(lambda a, b: None),
    operator.sub: inspect.signature(lambda a, b: None),
    operator.mul: inspect.signature(lambda a, b: None),
    operator.truediv: inspect.signature(lambda a, b: None),
    operator.floordiv: inspect.signature(lambda a, b: None),
    operator.mod: inspect.signature(lambda a, b: None),
    operator.pow: inspect.signature(lambda a, b: None),
    operator.lshift: inspect.signature(lambda a, b: None),
    operator.rshift: inspect.signature(lambda a, b: None),
    operator.or_: inspect.signature(lambda a, b: None),
    operator.xor: inspect.signature(lambda a, b: None),
    operator.and_: inspect.signature(lambda a, b: None),

    operator.eq: inspect.signature(lambda a, b: None),
    operator.ne: inspect.signature(lambda a, b: None),
    operator.lt: inspect.signature(lambda a, b: None),
    operator.le: inspect.signature(lambda a, b: None),
    operator.gt: inspect.signature(lambda a, b: None),
    operator.ge: inspect.signature(lambda a, b: None),
    operator.is_: inspect.signature(lambda a, b: None),
    operator.is_not: inspect.signature(lambda a, b: None),
}


_BUILTIN_CALLABLES = set(
    getattr(builtins, name) for name in dir(builtins)
    if callable(getattr(builtins, name)))
_BUILTIN_PURE_CALLABLES = _BUILTIN_CALLABLES.difference([
    delattr, setattr, eval, exec, input, print, next, open])


def get_signature(func):
    # built-in functions and operators in CPython cannot be inspected,
    # so we use a predefined signature
    if func in _KNOWN_SIGNATURES:
        return _KNOWN_SIGNATURES[func]

    return inspect.signature(func)


def is_pure(func):
    pure_tag = get_pure_tag(func)
    if pure_tag is not None:
        return pure_tag

    if func in _BUILTIN_PURE_CALLABLES or func in _KNOWN_SIGNATURES:
        return True

    return False
