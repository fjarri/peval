# Need these to detect them in function objects
import __future__

import sys
import ast
import copy
import inspect
from functools import reduce
from types import FunctionType
from collections import OrderedDict
import typing

import astunparse

from peval.tools import unindent, replace_fields, immutableadict, ast_inspector, ast_transformer
from peval.core.gensym import GenSym
from peval.core.reify import reify_unwrapped
from peval.core.scope import analyze_scope
from peval.typing import ConstsDictT, NodeTypeIsInstanceCriteriaT


SOURCE_ATTRIBUTE = "_peval_source"

if sys.version_info[:2] >= (3, 5):
    FUTURE_NAMES = ("generator_stop",)
else:
    # peval supports Python 3.5+, but readthedocs runs Python 3.4,
    # and needs to import our module in order to pick up docstrings,
    # and ``generator_stop`` did not exist back then.
    FUTURE_NAMES = ()

FUTURE_FEATURES = dict((name, getattr(__future__, name)) for name in FUTURE_NAMES)

FUTURE_FLAGS = reduce(
    lambda x, y: x | y, [feature.compiler_flag for feature in FUTURE_FEATURES.values()], 0
)


def eval_function_def(
    function_def: typing.Union[ast.AsyncFunctionDef, ast.FunctionDef],
    globals_=None,
    flags: typing.Optional[int] = None,
) -> typing.Callable:
    """
    Evaluates an AST of a function definition with an optional dictionary of globals.
    Returns a callable function (a ``types.FunctionType`` object).
    """

    assert type(function_def) in (ast.FunctionDef, ast.AsyncFunctionDef)

    # Making a copy before mutating
    module = ast.Module(body=[copy.deepcopy(function_def)], type_ignores=[])

    ast.fix_missing_locations(module)

    if flags is not None:
        kwds = dict(dont_inherit=True, flags=flags)
    else:
        kwds = {}
    code_object = compile(module, "<nofile>", "exec", **kwds)

    locals_ = {}
    eval(code_object, globals_, locals_)
    return locals_[function_def.name]


def eval_function_def_as_closure(
    function_def: ast.FunctionDef,
    closure_names: typing.List[str],
    globals_: typing.Optional[ConstsDictT] = None,
    flags: typing.Optional[int] = None,
) -> typing.Callable:
    """
    Evaluates an AST of a function definition inside a closure with the variables
    from ``closure_names`` set to ``None``, and an optional dictionary of globals.
    Returns a callable function (a ``types.FunctionType`` object).

    .. warning::

        Before the returned function can be actually called, the "fake" closure cells
        (filled with ``None``) must be substituted by actual closure cells
        that will be used during the call.
    """
    def_type = type(function_def)
    assert def_type in (ast.FunctionDef, ast.AsyncFunctionDef)

    none = ast.NameConstant(value=None)

    # We can't possibly recreate ASTs of existing closure variables
    # (because all we have are their values).
    # So we create fake closure variables for the function to attach to,
    # and then substitute the closure cells with the ones obtained from
    # the "prototype" of this function (a ``types.FunctionType`` object
    # from which this tree was extracted).
    fake_closure_vars = [
        ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=none)
        for name in closure_names
    ]

    empty_args = ast.arguments(
        posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kwarg=None, defaults=[], kw_defaults=[]
    )

    wrapper_def = def_type(
        name="__peval_wrapper",
        args=empty_args,
        decorator_list=[],
        body=(
            fake_closure_vars
            + [function_def]
            + [ast.Return(value=ast.Name(id=function_def.name, ctx=ast.Load()))]
        ),
    )

    wrapper = eval_function_def(wrapper_def, globals_=globals_, flags=flags)
    return wrapper()


def get_closure(func: typing.Callable) -> OrderedDict:
    """
    Extracts names and values of closure variables from a function.
    Returns a tuple ``(names, cells)``, where ``names`` is a tuple of strings
    and ``cells`` is a tuple of ``Cell`` objects (containing the actual value
    in the attribute ``cell_contents``).
    """
    closure_names = func.__code__.co_freevars
    closure_vals = func.__closure__
    if len(closure_names) == 0:
        closure_vals = tuple()
    return OrderedDict((name, val) for name, val in zip(closure_names, closure_vals))


def filter_arglist(args: typing.Iterable[ast.arg], defaults, bound_argnames: typing.Set[str]):
    """
    Filters a list of function argument nodes (``ast.arg``)
    and corresponding defaults to exclude all arguments with the names
    present in ``bound_arguments``.
    Returns a pair of new arguments and defaults.
    """
    new_args = []
    new_defaults = []
    required_args = len(args) - len(defaults)
    for i, arg in enumerate(args):
        if arg.arg not in bound_argnames:
            new_args.append(arg)
            if i >= required_args:
                new_defaults.append(defaults[i - required_args])

    return new_args, new_defaults


def filter_arguments(arguments: ast.arguments, bound_argnames: typing.Set[str]) -> ast.arguments:
    """
    Filters a node containing function arguments (an ``ast.arguments`` object)
    to exclude all arguments with the names present in ``bound_arguments``.
    Returns the new ``ast.arguments`` node.
    """

    assert type(arguments) == ast.arguments

    new_params = dict(ast.iter_fields(arguments))

    new_params["args"], new_params["defaults"] = filter_arglist(
        arguments.args, arguments.defaults, bound_argnames
    )

    new_params["kwonlyargs"], new_params["kw_defaults"] = filter_arglist(
        arguments.kwonlyargs, arguments.kw_defaults, bound_argnames
    )

    vararg_name = arguments.vararg.arg if arguments.vararg is not None else None
    kwarg_name = arguments.kwarg.arg if arguments.kwarg is not None else None

    if vararg_name is not None and vararg_name in bound_argnames:
        new_params["vararg"] = None

    if kwarg_name is not None and kwarg_name in bound_argnames:
        new_params["kwarg"] = None

    return ast.arguments(**new_params)


def filter_function_def(
    function_def: ast.FunctionDef, bound_argnames: typing.Set[str]
) -> ast.FunctionDef:
    """
    Filters a node containing a function definition
    (an ``ast.FunctionDef`` or an ``ast.AsyncFunctionDef`` object)
    to exclude all arguments with the names present in ``bound_arguments``.
    Returns the new ``ast.arguments`` node.
    """
    def_type = type(function_def)
    assert def_type in (ast.FunctionDef, ast.AsyncFunctionDef)

    new_args = filter_arguments(function_def.args, bound_argnames)

    return def_type(
        name=function_def.name,
        args=new_args,
        body=function_def.body,
        decorator_list=function_def.decorator_list,
        returns=function_def.returns,
    )


@ast_transformer
def parse_annotations(node, **_):
    if isinstance(node, ast.arg) and isinstance(node.annotation, ast.Str):
        annotation = ast.parse(node.annotation.s).body[0].value
        node = replace_fields(node, annotation=annotation)
    return node


class Function(object):
    """
    A wrapper for functions providing transformations to and from AST
    and simplifying operations with associated global and closure variables.

    .. attribute:: tree

        An AST tree of the function (including the header and decorators, if any)

    .. attribute:: globals

        A dictionary of global variables associated with the function.

    .. attribute:: closure_vals

        A dictionary of closure variables associated with the function.
    """

    def __init__(
        self,
        tree: typing.Union[ast.AsyncFunctionDef, ast.FunctionDef],
        globals_,
        closure_vals,
        compiler_flags: int,
    ) -> None:

        self.tree = tree
        self.globals = globals_
        self.closure_vals = closure_vals

        # Extract enabled future features from compiler flags

        self._compiler_flags = compiler_flags
        future_features = {}
        for feature_name, feature in FUTURE_FEATURES.items():
            enabled_by_flag = compiler_flags & feature.compiler_flag != 0

            enabled_from = feature.getMandatoryRelease()
            enabled_by_default = enabled_from is not None and sys.version_info >= enabled_from

            future_features[feature_name] = enabled_by_flag or enabled_by_default

        self.future_features = immutableadict(future_features)

    def get_external_variables(self) -> ConstsDictT:
        """
        Returns a unified dictionary of external variables for this function
        (both globals and closure variables).
        """
        variables = dict(self.globals)
        for name, val in self.closure_vals.items():
            variables[name] = val.cell_contents
        return variables

    def get_source(self) -> str:
        """
        Generates the function's source code based on its tree.
        """
        return astunparse.unparse(self.tree)

    @classmethod
    def from_object(cls, func: typing.Callable, ignore_decorators: bool = False) -> "Function":
        """
        Creates a ``Function`` object from an evaluated function.
        """

        src = getsource(func)
        tree = ast.parse(src).body[0]

        # Annotations are always strings since Py3.8.
        # We need them as actual AST in order to know what bindings to leave in globals,
        # and to partially evaluate them later.
        tree = parse_annotations(tree)

        if ignore_decorators:
            tree = replace_fields(tree, decorator_list=[])

        global_values = func.__globals__

        closure_vals = get_closure(func)

        scope = analyze_scope(tree)
        func_name = func.__name__

        # Builtins can be either a dict or a module
        builtins = global_values["__builtins__"]
        if not isinstance(builtins, dict):
            builtins = dict(vars(builtins))

        globals_ = {}
        for name in scope.globals:
            if name == func_name:
                globals_[name] = func
            elif name in global_values:
                globals_[name] = global_values[name]
            elif name in builtins:
                globals_[name] = builtins[name]
            elif name in closure_vals:
                continue
            else:
                raise NameError(name)

        compiler_flags = func.__code__.co_flags

        # We only need the flags corresponding to future features.
        # Also, these are the only ones supported by compile().
        compiler_flags = compiler_flags & FUTURE_FLAGS

        return cls(tree, globals_, closure_vals, compiler_flags)

    def bind_partial(self, *args, **kwds) -> "Function":
        """
        Binds the provided positional and keyword arguments
        and returns a new ``Function`` object with an updated signature.
        """

        # We only need the signature, so clean the function body before eval'ing.
        empty_func = self.replace(tree=replace_fields(self.tree, body=[ast.Pass()]))
        signature = inspect.signature(empty_func.eval())
        bargs = signature.bind_partial(*args, **kwds)

        # Remove the bound arguments from the function AST
        bound_argnames = set(bargs.arguments.keys())
        new_tree = filter_function_def(self.tree, bound_argnames)

        # Add assignments for bound parameters
        assignments = []
        gen_sym = GenSym.for_tree(new_tree)
        new_bindings = {}
        for name, value in bargs.arguments.items():
            node, gen_sym, binding = reify_unwrapped(value, gen_sym)
            new_bindings.update(binding)
            assignments.append(ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=node))

        new_globals = dict(self.globals)
        new_globals.update(new_bindings)

        new_tree = replace_fields(new_tree, body=assignments + new_tree.body)

        return Function(new_tree, new_globals, self.closure_vals, self._compiler_flags)

    def eval(self) -> typing.Callable:
        """
        Evaluates and returns a callable function.
        """
        if len(self.closure_vals) > 0:
            func_fake_closure = eval_function_def_as_closure(
                self.tree,
                list(self.closure_vals),
                globals_=self.globals,
                flags=self._compiler_flags,
            )

            func = FunctionType(
                func_fake_closure.__code__,
                self.globals,
                func_fake_closure.__name__,
                func_fake_closure.__defaults__,
                tuple(self.closure_vals.values()),
            )

            for attr in ("__kwdefaults__", "__annotations__"):
                if hasattr(func_fake_closure, attr):
                    setattr(func, attr, getattr(func_fake_closure, attr))
        else:
            func = eval_function_def(self.tree, globals_=self.globals, flags=self._compiler_flags)

        # A regular function contains a file name and a line number
        # pointing to the location of its source.
        # I we wanted to trick ``inspect.getsource()`` into working with
        # this newly generated function, we could create a temporary file and write it there.
        # But it leads to other complications, and is unnecessary at this stage.
        # So we just save the source into an attribute for ``Function.from_object()``
        # to discover if we ever want to create a new ``Function`` object
        # out of this function.
        vars(func)[SOURCE_ATTRIBUTE] = self.get_source()

        return func

    def replace(
        self,
        tree: typing.Optional[ast.FunctionDef] = None,
        globals_: typing.Optional[ConstsDictT] = None,
    ) -> "Function":
        """
        Replaces the AST and/or globals and returns a new ``Function`` object.
        If some closure variables are not used by a new tree,
        adjusts the closure cells accordingly.
        """
        if tree is None:
            tree = self.tree
        if globals_ is None:
            globals_ = self.globals

        if len(self.closure_vals) > 0:
            func_fake_closure = eval_function_def_as_closure(
                tree, list(self.closure_vals), globals_=globals_, flags=self._compiler_flags
            )

            new_closure_vals = get_closure(func_fake_closure)
            for name in new_closure_vals:
                new_closure_vals[name] = self.closure_vals[name]
        else:
            new_closure_vals = self.closure_vals

        return Function(tree, globals_, new_closure_vals, self._compiler_flags)


def getsource(func: typing.Callable) -> str:
    """
    Returns the source of a function ``func``.
    Falls back to ``inspect.getsource()`` for regular functions,
    but can also return the source of a partially evaluated function.
    """

    if hasattr(func, SOURCE_ATTRIBUTE):
        # An attribute created in ``Function.eval()``
        return getattr(func, SOURCE_ATTRIBUTE)
    else:
        return unindent(inspect.getsource(func))


@ast_inspector
def _has_nodes(state, node, ctx, skip_fields, **_):
    if state.nodes_found:
        skip_fields()
        return state

    if type(node) in ctx.node_types:
        return state.update(nodes_found=True)
    else:
        return state


def has_nodes(node: ast.AST, node_types: NodeTypeIsInstanceCriteriaT) -> bool:
    return _has_nodes(dict(nodes_found=False), node, ctx=dict(node_types=node_types)).nodes_found


def has_nested_definitions(function: Function) -> bool:
    return has_nodes(
        function.tree.body, (ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef, ast.Lambda)
    )


def is_a_generator(function: Function) -> bool:
    return has_nodes(function.tree, (ast.Yield, ast.YieldFrom))


def is_async(function: Function) -> bool:
    return type(function.tree) == ast.AsyncFunctionDef
