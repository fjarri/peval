from typing import Callable, Optional

from peval.core.function import Function, has_nested_definitions, is_a_generator, is_async


def pure(func: Callable) -> Callable:
    """
    Marks the function as pure (not having any side effects, except maybe argument mutation).

    Note that for class- and staticmethods ``@pure`` must be declared
    within the corresponding decorator.
    """
    func.__peval_pure__ = True
    return func


def get_pure_tag(func: Callable) -> Optional[bool]:
    return getattr(func, "__peval_pure__", None)


def inline(func: Callable) -> Callable:
    """
    Marks the function for inlining.
    """
    function = Function.from_object(func, ignore_decorators=True)

    if has_nested_definitions(function):
        raise ValueError("An inlined function cannot have nested function or class definitions")

    if is_a_generator(function):
        raise ValueError("An inlined function cannot be a generator")

    if is_async(function):
        raise ValueError("An inlined function cannot be an async coroutine")

    if len(function.closure_vals) > 0:
        raise ValueError("An inlined function cannot have a closure")

    func.__peval_inline__ = True
    return func


def get_inline_tag(func: Callable) -> Optional[bool]:
    return getattr(func, "__peval_inline__", None)
