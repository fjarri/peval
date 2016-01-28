import ast
import sys

import pytest

from peval.core.expression import peval_expression, try_peval_expression
from peval.core.gensym import GenSym
from peval.tags import pure

from tests.utils import assert_ast_equal


def expression_ast(source):
    return ast.parse(source).body[0].value


def check_peval_expression(source, bindings, expected_source,
        fully_evaluated=False, expected_value=None, expected_temp_bindings=None):

    source_tree = expression_ast(source)

    # In some cases we need to enforce the expected node,
    # because it cannot be obtained by parsing
    # (e.g. "-5" is parsed as "UnaryOp(op=USub(), Num(n=5))", not as "Num(n=-5)").
    # But we expect the latter from a fully evaluated expression.
    if isinstance(expected_source, str):
        expected_tree = expression_ast(expected_source)
    else:
        expected_tree = expected_source

    gen_sym = GenSym()
    result, gen_sym = peval_expression(source_tree, gen_sym, bindings)

    assert_ast_equal(result.node, expected_tree)

    assert result.fully_evaluated == fully_evaluated
    if fully_evaluated:
        assert result.value == expected_value

    if expected_temp_bindings is not None:
        for key, val in expected_temp_bindings.items():
            assert key in result.temp_bindings
            assert result.temp_bindings[key] == expected_temp_bindings[key]


def check_peval_expression_bool(source, bindings, expected_value):
    """
    Since prior to Py3.4 `True` and `False` are regular variables,
    these values will be bound to unique names by peval_expression.
    This helper function hides the corresponding logic fork.
    """
    assert expected_value is True or expected_value is False
    check_peval_expression(
        source, bindings, expected_source=str(expected_value),
        fully_evaluated=True, expected_value=expected_value)


def test_simple_cases():

    check_peval_expression('x', {}, 'x')
    check_peval_expression('1', {}, '1', fully_evaluated=True, expected_value=1)
    check_peval_expression('"a"', {}, '"a"', fully_evaluated=True, expected_value='a')

    s = bytes('abc', encoding='ascii')
    check_peval_expression(
        'b"abc"', dict(b=s), 'b"abc"', fully_evaluated=True, expected_value=s)

    check_peval_expression('True', {}, 'True', fully_evaluated=True, expected_value=True)


def test_preferred_name():
    class Dummy(): pass
    x = Dummy()
    check_peval_expression('y', dict(y=x), 'y')


def test_try_peval_expression():
    class Dummy(): pass
    x = Dummy()
    evaluated, value = try_peval_expression(ast.Name(id='x', ctx=ast.Load()), dict(x=x))
    assert evaluated
    assert value is x

    node = ast.Name(id='y', ctx=ast.Load())
    evaluated, value = try_peval_expression(node, dict(x=x))
    assert not evaluated
    assert value is node


def test_bin_op_support():
    """
    Check that all possible binary operators are handled by the evaluator.
    """
    check_peval_expression("1 + 2", {}, "3", fully_evaluated=True, expected_value=3)
    check_peval_expression("2 - 1", {}, "1", fully_evaluated=True, expected_value=1)
    check_peval_expression("2 * 3", {}, "6", fully_evaluated=True, expected_value=6)
    check_peval_expression("9 / 2", {}, "4.5", fully_evaluated=True, expected_value=4.5)
    check_peval_expression("9 // 2", {}, "4", fully_evaluated=True, expected_value=4)
    check_peval_expression("9 % 2", {}, "1", fully_evaluated=True, expected_value=1)
    check_peval_expression("2 ** 4", {}, "16", fully_evaluated=True, expected_value=16)
    check_peval_expression("3 << 2", {}, "12", fully_evaluated=True, expected_value=12)
    check_peval_expression("64 >> 3", {}, "8", fully_evaluated=True, expected_value=8)
    check_peval_expression("17 | 3", {}, "19", fully_evaluated=True, expected_value=19)
    check_peval_expression("17 ^ 3", {}, "18", fully_evaluated=True, expected_value=18)
    check_peval_expression("17 & 3", {}, "1", fully_evaluated=True, expected_value=1)


def test_unary_op_support():
    """
    Check that all possible unary operators are handled by the evaluator.
    """
    check_peval_expression("+(2)", {}, "2", fully_evaluated=True, expected_value=2)
    check_peval_expression("-(-3)", {}, "3", fully_evaluated=True, expected_value=3)
    check_peval_expression_bool("not 0", {}, True)
    check_peval_expression("~(-4)", {}, "3", fully_evaluated=True, expected_value=3)


def test_comparison_op_support():
    """
    Check that all possible comparison operators are handled by the evaluator.
    """
    check_peval_expression_bool("1 == 2", {}, False)
    check_peval_expression_bool("2 != 3", {}, True)
    check_peval_expression_bool("1 < 10", {}, True)
    check_peval_expression_bool("1 <= 1", {}, True)
    check_peval_expression_bool("2 > 5", {}, False)
    check_peval_expression_bool("4 >= 6", {}, False)

    class Foo: pass
    x = Foo()
    y = Foo()
    check_peval_expression_bool("a is b", dict(a=x, b=x), True)
    check_peval_expression_bool("a is not b", dict(a=x, b=y), True)

    check_peval_expression_bool("1 in (3, 4, 5)", {}, False)
    check_peval_expression_bool("'a' not in 'abcd'", {}, False)


def test_and():
    check_peval_expression_bool('a and b', dict(a=True, b=True), True)
    check_peval_expression_bool('a and b', dict(a=False), False)
    check_peval_expression('a and b', dict(a=True), 'b')
    check_peval_expression('a and b and c and d', dict(a=True, c=True), 'b and d')


def test_and_short_circuit():

    global_state = dict(cnt=0)

    @pure
    def inc():
        global_state['cnt'] += 1
        return True

    check_peval_expression_bool('a and inc()', dict(a=False, inc=inc), False)
    assert global_state['cnt'] == 0

    check_peval_expression_bool('a and inc()', dict(a=True, inc=inc), True)
    assert global_state['cnt'] == 1


def test_or():
    check_peval_expression_bool('a or b', dict(a=False, b=False), False)
    check_peval_expression('a or b', dict(a=False), 'b')
    check_peval_expression_bool('a or b', dict(a=True), True)
    check_peval_expression('a or b or c or d', dict(a=False, c=False), 'b or d')


def test_or_short_circuit():

    global_state = dict(cnt=0)

    @pure
    def inc():
        global_state['cnt'] += 1
        return True

    check_peval_expression_bool('a or inc()', dict(a=True, inc=inc), True)
    assert global_state['cnt'] == 0

    check_peval_expression_bool('a or inc()', dict(a=False, inc=inc), True)
    assert global_state['cnt'] == 1


def test_compare():
    check_peval_expression_bool('0 == 0', {}, True)
    check_peval_expression_bool('0 == 1', {}, False)
    check_peval_expression('a == b', dict(a=1), '1 == b')
    check_peval_expression('a == b', dict(b=1), 'a == 1')
    check_peval_expression_bool('a == b', dict(a=1, b=1), True)
    check_peval_expression_bool('a == b', dict(a=2, b=1), False)
    check_peval_expression('a == b == c == d', dict(a=2, c=2), '2 == b == 2 == d')
    check_peval_expression_bool('a < b >= c', dict(a=0, b=1, c=1), True)
    check_peval_expression_bool('a <= b > c', dict(a=0, b=1, c=1), False)


def test_ifexp():
    check_peval_expression('x if (not a) else y', dict(a=False), 'x')
    check_peval_expression('x if a else y', dict(a=False), 'y')
    check_peval_expression('(x + y) if a else (y + 4)', dict(x=1, y=2), '3 if a else 6')


def test_ifexp_short_circuit():

    global_state = dict(cnt=0)

    @pure
    def inc():
        global_state['cnt'] += 1
        return True

    check_peval_expression('x if a else inc()', dict(a=True, inc=inc), 'x')
    assert global_state['cnt'] == 0

    check_peval_expression('inc() if a else x', dict(a=False, inc=inc), 'x')
    assert global_state['cnt'] == 0

    check_peval_expression_bool('inc() if a else x', dict(a=True, inc=inc), True)
    assert global_state['cnt'] == 1


def test_dict():
    check_peval_expression('{a: b, c: d}', dict(a=2, d=1), '{2: b, c: 1}')
    check_peval_expression(
        '{a: b, c: d}', dict(a=1, b=2, c=3, d=4), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1={1: 2, 3: 4}),
        fully_evaluated=True, expected_value={1: 2, 3: 4})


def test_list():
    check_peval_expression('[a, b, c, d]', dict(a=2, d=1), '[2, b, c, 1]')
    check_peval_expression(
        '[a, b, c, d]', dict(a=1, b=2, c=3, d=4), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=[1, 2, 3, 4]),
        fully_evaluated=True, expected_value=[1, 2, 3, 4])


def test_set():
    check_peval_expression('{a, b, c, d}', dict(a=2, d=1), '{2, b, c, 1}')
    check_peval_expression(
        '{a, b, c, d}', dict(a=1, b=2, c=3, d=4), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=set([1, 2, 3, 4])),
        fully_evaluated=True, expected_value=set([1, 2, 3, 4]))


def test_attribute():

    class Dummy:
        a = 1

    d = Dummy()

    check_peval_expression('x.a', dict(x=d), '1', fully_evaluated=True, expected_value=1)
    check_peval_expression('(x + y).a', dict(x=1), '(1 + y).a')


def test_subscript():

    # Simple indices

    check_peval_expression(
        'x[a]', dict(x="abc", a=1), '"b"', fully_evaluated=True, expected_value='b')
    check_peval_expression('x[a + 4]', dict(a=1), 'x[5]')
    check_peval_expression('x[a + 4]', dict(x='abc'), '"abc"[a + 4]')

    # Slices

    check_peval_expression(
        'x[a+b:c:d]', dict(x="abcdef", a=0, b=1, c=3, d=1), '"bc"',
        fully_evaluated=True, expected_value='bc')
    check_peval_expression(
        'x[a+b:c]', dict(x="abcdef", a=0, b=1, c=3), '"bc"',
        fully_evaluated=True, expected_value='bc')
    check_peval_expression(
        'x[a + 4: 10]', dict(a=1), 'x[__peval_temp_1]',
        expected_temp_bindings=dict(__peval_temp_1=slice(5, 10)))
    check_peval_expression('x[a + 4:10]', dict(x='abc'), '"abc"[a + 4: 10]')

    # Extended slices

    check_peval_expression(
        'x[a+4:10, :b:c]', dict(a=1, b=10, c=3), 'x[__peval_temp_1]',
        expected_temp_bindings=dict(__peval_temp_1=(slice(5, 10), slice(None, 10, 3))))
    check_peval_expression('x[a:b,c::d]', dict(x='abc'), '"abc"[a:b,c::d]')


def test_function_call():

    @pure
    def fn_args(x, y):
        return x, y

    check_peval_expression('fn(x + z, y + 5)', dict(fn=fn_args, x=10, z=20), 'fn(30, y + 5)')
    check_peval_expression(
        'fn(x + 10, y + 5)', dict(fn=fn_args, x=10, y=20), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=(20, 25)),
        fully_evaluated=True, expected_value=(20, 25))

    @pure
    def fn_args_kwds(x, y, z=5):
        return x, y, z

    check_peval_expression('fn(x, y, z=a + 1)', dict(fn=fn_args_kwds, a=10), 'fn(x, y, z=11)')
    check_peval_expression(
        'fn(x, y, z=a + 1)', dict(fn=fn_args_kwds, x=1, y=2, a=10), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=(1, 2, 11)),
        fully_evaluated=True, expected_value=(1, 2, 11))

    # TODO: need support for starred argument evaluation
    """
    @pure
    def fn_varargs(x, y, *args):
        return x, y, args

    check_peval_expression(
        'fn(x, y, *(a + b))', dict(fn=fn_varargs, a=(3, 4), b=(5,)), 'fn(x, y, *__peval_temp_1)',
        expected_temp_bindings=dict(__peval_temp_1=(3, 4, 5)))
    check_peval_expression(
        'fn(x, y, *(a + b))', dict(fn=fn_varargs, x=1, y=2, a=(3, 4), b=(5,)), '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=(1, 2, (3, 4, 5))),
        fully_evaluated=True, expected_value=(1, 2, (3, 4, 5)))

    @pure
    def fn_varkwds(*args, **kwds):
        return args, kwds

    @pure
    def get_kwds(x):
        return {'a': x}

    check_peval_expression(
        'fn(*a, **get_kwds(b))', dict(fn=fn_varkwds, get_kwds=get_kwds, b=5),
        'fn(*a, **__peval_temp_1)',
        expected_temp_bindings=dict(__peval_temp_1={'a': 5}))
    check_peval_expression(
        'fn(*a, **get_kwds(b))', dict(fn=fn_varkwds, get_kwds=get_kwds, a=(3, 4), b=5),
        '__peval_temp_1',
        expected_temp_bindings=dict(__peval_temp_1=((3, 4), {'a': 5})),
        fully_evaluated=True, expected_value=((3, 4), {'a': 5}))
    """

def test_yield():
    check_peval_expression('yield a + b', dict(a=1), 'yield 1 + b')
    check_peval_expression('yield a + b', dict(a=1, b=2), 'yield 3')


def test_yield_from():
    check_peval_expression('yield from iter(a)', dict(a=1), 'yield from iter(1)')


def test_list_comprehension():
    check_peval_expression(
        '[x + 1 for x in range(a)]', dict(a=10, range=range), '__peval_temp_2',
        expected_temp_bindings=dict(__peval_temp_2=list(range(1, 11))),
        fully_evaluated=True, expected_value=list(range(1, 11)))
    check_peval_expression(
        '[x + 1 for x in range(a)]', dict(a=10), '[x + 1 for x in range(10)]')

    check_peval_expression(
        '[x + y for x, y in [(1, 2), (2, 3)]]',
        dict(a=10, range=range, zip=zip), '__peval_temp_2',
        expected_temp_bindings=dict(__peval_temp_2=[3, 5]),
        fully_evaluated=True, expected_value=[3, 5])


def test_set_comprehension():
    check_peval_expression(
        '{x + 1 for x in range(a)}', dict(a=10, range=range), '__peval_temp_2',
        expected_temp_bindings=dict(__peval_temp_2=set(range(1, 11))),
        fully_evaluated=True, expected_value=set(range(1, 11)))
    check_peval_expression(
        '{x + 1 for x in range(a)}', dict(a=10), '{x + 1 for x in range(10)}')


def test_dict_comprehension():
    check_peval_expression(
        '{x+1:x+2 for x in range(a)}', dict(a=2, range=range), '__peval_temp_3',
        expected_temp_bindings=dict(__peval_temp_3={1:2, 2:3}),
        fully_evaluated=True, expected_value={1:2, 2:3})
    check_peval_expression(
        '{x+1:x+2 for x in range(a)}', dict(a=2), '{x+1:x+2 for x in range(2)}')


def test_generator_exp():

    # Need to do this manually, since we can't compare generator expressions
    # without changing their state.

    source_tree = expression_ast("(x + 1 for x in range(a))")
    expected_tree = expression_ast("__peval_temp_2")
    bindings = dict(a=10, range=range)

    gen_sym = GenSym()
    result, gen_sym = peval_expression(source_tree, gen_sym, bindings)

    assert_ast_equal(result.node, expected_tree)
    assert result.fully_evaluated

    expected_genexp = (x + 1 for x in range(10))

    assert type(result.value) == type(expected_genexp)
    assert list(result.value) == list(expected_genexp)

    # Since the binding contained the reference to the same genexp,
    # and we destroyed it, we need to do the evaluation again
    # in order to check the binding as well

    gen_sym = GenSym()
    result, gen_sym = peval_expression(source_tree, gen_sym, bindings)

    expected_genexp = (x + 1 for x in range(10))

    assert '__peval_temp_2' in result.temp_bindings
    binding = result.temp_bindings['__peval_temp_2']
    assert type(binding) == type(expected_genexp)
    assert list(binding) == list(expected_genexp)


    check_peval_expression(
        '(x + 1 for x in range(a))', dict(a=10), '(x + 1 for x in range(10))')


def test_partial_bin_op():
    check_peval_expression("5 + 6 + a", {}, "11 + a")


def test_full_bin_op():
    check_peval_expression("5 + 6 + a", dict(a=7), "18", fully_evaluated=True, expected_value=18)


def test_propagation_int():
    check_peval_expression(
        "a * n + (m - 2) * (n + 1)", dict(n=5),
        "a * 5 + (m - 2) * 6")


def test_propagation_float():
    check_peval_expression(
        'a * n + (m - 2) * (n + 1)', dict(n=5.0),
        'a * 5.0 + (m - 2) * 6.0')


def test_propagation_str():
    check_peval_expression(
        "a + foo", dict(foo="bar"),
        "a + 'bar'")


def test_preferred_name():
    """
    Test that when a non-literal value is transformed back into an AST node,
    it takes back the name it was bound to.
    """

    class Int(int): pass
    check_peval_expression(
        'm * n', dict(m=Int(2)),
        'm * n')


def test_exception():
    """
    A pure function which throws an exception during partial evaluation
    is left unevaluated.
    """

    @pure
    def fn():
        return 1 / 0
    check_peval_expression('fn()', dict(fn=fn), 'fn()')


def test_arithmetic():
    check_peval_expression(
        '1 + 1', {}, '2', fully_evaluated=True, expected_value=2)
    check_peval_expression(
        '1 + (1 * 67.0)', {}, '68.0', fully_evaluated=True, expected_value=68.0)
    check_peval_expression(
        '1 / 2.0', {}, '0.5', fully_evaluated=True, expected_value=0.5)
    check_peval_expression(
        '3 % 2', {}, '1', fully_evaluated=True, expected_value=1)
    check_peval_expression(
        'x / y', dict(x=1, y=2.0), '0.5', fully_evaluated=True, expected_value=0.5)
