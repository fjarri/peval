import inspect
from functools import lru_cache

from peval.core.function import Function, has_nested_definitions, is_async
from peval.components import inline_functions, prune_cfg, prune_assignments, fold
from peval.tools import ast_equal


def _run_components(tree, constants):
    while True:
        new_tree = tree
        new_constants = constants

        for func in (inline_functions, fold, prune_cfg, prune_assignments):
            new_tree, new_constants = func(new_tree, new_constants)

        if ast_equal(new_tree, tree) and new_constants == constants:
            break

        tree = new_tree
        constants = new_constants

    return new_tree, new_constants


def partial_apply(func, *args, **kwds):
    """
    Same as :func:`partial_eval`, but in addition uses the provided values of
    positional and keyword arguments in the partial evaluation.
    """
    function = Function.from_object(func, ignore_decorators=True)

    if has_nested_definitions(function):
        raise ValueError(
            "A partially evaluated function cannot have nested function or class definitions")

    if is_async(function):
        raise ValueError("A partially evaluated function cannot be an async coroutine")

    if len(args) > 0 or len(kwds) > 0:
        bound_function = function.bind_partial(*args, **kwds)
    else:
        bound_function = function

    new_tree, bindings = _run_components(
        bound_function.tree,
        bound_function.get_external_variables())

    globals_ = dict(bound_function.globals)
    globals_.update(bindings)

    new_function = bound_function.replace(tree=new_tree, globals_=globals_)

    return new_function.eval()


def partial_eval(func):
    """
    Returns a partially evaluated version of ``func``, using the values of
    associated global and closure variables.
    """
    return partial_apply(func)


def specialize_on(names, maxsize=None):
    """
    A decorator that wraps a function, partially evaluating it with the parameters
    defined by ``names`` (can be a string or an iterable of strings) being fixed.
    The partially evaluated versions are cached based on the values of these parameters
    using ``functools.lru_cache`` with the provided ``maxsize``
    (consequently, these values should be hashable).
    """
    if isinstance(names, str):
        names = [names]
    names_set = set(names)

    def _specializer(func):

        signature = inspect.signature(func)

        if not names_set.issubset(signature.parameters):
            missing_names = names_set.intersection(signature.parameters)
            raise ValueError(
                "The provided function does not have parameters: "
                + ", ".join(missing_names))

        @lru_cache(maxsize=maxsize)
        def get_pevaled_func(args):
            return partial_apply(func, **{name:val for name, val in args})

        def _wrapper(*args, **kwds):
            bargs = signature.bind(*args, **kwds)
            call_arguments = bargs.arguments.copy()
            for name in list(bargs.arguments):
                if name not in names_set:
                    del bargs.arguments[name] # automatically changes .args and .kwargs
                else:
                    del call_arguments[name]

            cache_args = tuple((name, val) for name, val in bargs.arguments.items())
            pevaled_func = get_pevaled_func(cache_args)

            bargs.arguments = call_arguments # automatically changes .args and .kwargs

            return pevaled_func(*bargs.args, **bargs.kwargs)

        return _wrapper

    return _specializer
