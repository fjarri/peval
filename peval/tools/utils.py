import ast
import re
import sys
from typing import Callable, Any, Iterable, Tuple, Sequence, Union, TypeVar, List, Dict, cast
from typing_extensions import ParamSpec, Concatenate


def unparse(tree: ast.AST) -> str:
    if sys.version_info >= (3, 9):
        return ast.unparse(tree)

    # TODO: as long as we're supporting Python 3.8 we have to rely on third-party unparsers.
    # Clean it up when Py3.8 is dropped.

    # Enabled by the `astunparse` feature.
    try:
        import astunparse

        return astunparse.unparse(tree)
    except ImportError:
        pass

    # Enabled by the `astor` feature.
    try:
        import astor

        return astor.to_source(tree)
    except ImportError as exc:
        raise ImportError(
            "Unparsing functionality is not available; switch to Python 3.9+, "
            "install with 'astunparse' feature, or install with 'astor' feature."
        ) from exc


def unindent(source: str) -> str:
    """
    Shift source to the left so that it starts with zero indentation.
    """
    source = source.rstrip("\n ").lstrip("\n")
    # Casting to Match here because this particular regex always matches
    indent = cast(re.Match, re.match(r"([ \t])*", source)).group(0)
    lines = source.split("\n")
    shifted_lines = []
    for line in lines:
        line = line.rstrip()
        if len(line) > 0:
            if not line.startswith(indent):
                raise ValueError("Inconsistent indent at line " + repr(line))
            shifted_lines.append(line[len(indent) :])
        else:
            shifted_lines.append(line)
    return "\n".join(shifted_lines)


def replace_fields(node: ast.AST, **kwds) -> ast.AST:
    """
    Return a node with several of its fields replaced by the given values.
    """
    new_kwds = dict(ast.iter_fields(node))
    for key, value in kwds.items():
        if value is not new_kwds[key]:
            break
    else:
        return node
    new_kwds.update(kwds)
    return type(node)(**new_kwds)


def _ast_equal(node1: Any, node2: Any):
    if node1 is node2:
        return True

    if type(node1) != type(node2):
        return False
    if isinstance(node1, list):
        if len(node1) != len(node2):
            return False
        for elem1, elem2 in zip(node1, node2):
            if not _ast_equal(elem1, elem2):
                return False
    elif isinstance(node1, ast.AST):
        for attr, value1 in ast.iter_fields(node1):
            value2 = getattr(node2, attr)
            if not _ast_equal(value1, value2):
                return False
    else:
        if node1 != node2:
            return False

    return True


def ast_equal(node1: ast.AST, node2: ast.AST) -> bool:
    """
    Test two AST nodes or two lists of AST nodes for equality.
    """
    # Type-gating it to make sure it's applied to AST nodes only.
    return _ast_equal(node1, node2)


_Accum = TypeVar("_Accum")
_Elem = TypeVar("_Elem")
_Container = TypeVar("_Container")
_Params = ParamSpec("_Params")


def map_accum(
    func: Callable[Concatenate[_Accum, _Elem, _Params], Tuple[_Accum, _Elem]],
    acc: _Accum,
    container: _Container,
    *args: _Params.args,
    **kwargs: _Params.kwargs,
) -> Tuple[_Accum, _Container]:
    # Unfortunately we have to do some casting, because mypy does not support higher-ranked types
    # (what we want here is to make the type of `func` something like
    # `forall[_Elem] Callable[Concatenate[_Accum, _Elem, _Params], Tuple[_Accum, _Elem]]`).
    if container is None:
        return acc, None
    elif isinstance(container, (tuple, list)):
        new_list = []
        for elem in container:
            acc, new_elem = map_accum(func, acc, elem, *args, **kwargs)
            new_list.append(new_elem)
        return acc, cast(_Container, type(container)(new_list))
    elif isinstance(container, dict):
        new_dict = {}
        for key, elem in container.items():
            acc, new_dict[key] = map_accum(func, acc, elem, *args, **kwargs)
        return acc, cast(_Container, new_dict)
    else:
        acc, new_container = func(acc, cast(_Elem, container), *args, **kwargs)
        return acc, cast(_Container, new_container)


def fold_and(func: Callable[[Any], bool], container: Union[List, Tuple, Dict, Any]) -> bool:
    if type(container) in (list, tuple):
        return all(fold_and(func, elem) for elem in container)
    elif type(container) == dict:
        return all(fold_and(func, elem) for elem in container.values())
    else:
        return func(container)
