import ast
import sys

import pytest

from peval.core.reify import KnownValue, is_known_value, reify, reify_unwrapped
from peval.core.gensym import GenSym

from tests.utils import assert_ast_equal


def check_reify(value, expected_ast, preferred_name=None, expected_binding=None):
    kvalue = KnownValue(value, preferred_name=preferred_name)
    gen_sym = GenSym()
    node, gen_sym, binding = reify(kvalue, gen_sym)

    assert_ast_equal(node, expected_ast)
    if expected_binding is not None:
        assert binding == expected_binding


def check_node_to_maybe_kvalue(node, bindings, expected_result, expected_preferred_name=None):
    node_or_kvalue = node_to_maybe_kvalue(node, bindings)

    if is_known_value(node_or_kvalue):
        assert node_or_kvalue.value == expected_result
        assert node_or_kvalue.preferred_name == expected_preferred_name
    else:
        assert_ast_equal(node_or_kvalue, expected_result)


def test_simple_reify():
    unified_constants = sys.version_info[:2] >= (3, 8)

    check_reify(
        True,
        ast.Constant(value=True, kind=None) if unified_constants else ast.NameConstant(value=True))
    check_reify(
        False,
        ast.Constant(value=False, kind=None) if unified_constants else ast.NameConstant(value=False))
    check_reify(
        None,
        ast.Constant(value=None, kind=None) if unified_constants else ast.NameConstant(value=None))

    class Dummy(): pass
    x = Dummy()
    check_reify(
        x, ast.Name(id='__peval_temp_1', ctx=ast.Load()),
        expected_binding=dict(__peval_temp_1=x))
    check_reify(
        x, ast.Name(id='y', ctx=ast.Load()),
        preferred_name='y', expected_binding=dict(y=x))

    check_reify(1, ast.Constant(value=1, kind=None) if unified_constants else ast.Num(n=1))
    check_reify(2.3, ast.Constant(value=2.3, kind=None) if unified_constants else ast.Num(n=2.3))
    check_reify(3+4j, ast.Constant(value=3+4j, kind=None) if unified_constants else ast.Num(n=3+4j))
    check_reify('abc', ast.Constant(value='abc', kind=None) if unified_constants else ast.Str(s='abc'))

    s = bytes('abc', encoding='ascii')
    check_reify(s, ast.Constant(value=s, kind=None) if unified_constants else ast.Bytes(s=s))


def test_reify_unwrapped():
    class Dummy(): pass
    x = Dummy()
    gen_sym = GenSym()
    node, gen_sym, binding = reify_unwrapped(x, gen_sym)
    assert_ast_equal(node, ast.Name(id='__peval_temp_1', ctx=ast.Load()))
    assert binding == dict(__peval_temp_1=x)


def test_str_repr():
    kv = KnownValue(1, preferred_name='x')
    s = str(kv)
    nkv = eval(repr(kv))
    assert nkv.value == kv.value
    assert nkv.preferred_name == kv.preferred_name
