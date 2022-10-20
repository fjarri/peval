from __future__ import print_function

import sys
import ast
import functools
import unittest
from pathlib import Path

from peval.core.function import Function
from peval import partial_eval, partial_apply, specialize_on, getsource, inline
from peval.tools import unindent

thisDir = Path(__file__).parent
sys.path.insert(0, str(thisDir))
sys.path.insert(1, str(thisDir.parent))

from utils import assert_ast_equal, function_from_source


@inline
def smart_power(n, x):
    if not isinstance(n, int) or n < 0:
        raise ValueError("Base should be a positive integer")
    elif n == 0:
        return 1
    elif n % 2 == 0:
        v = smart_power(n // 2, x)
        return v * v
    else:
        return x * smart_power(n - 1, x)


@inline
def stupid_power(n, x):
    if not isinstance(n, int) or n < 0:
        raise ValueError("Base should be a positive integer")
    else:
        if n == 0:
            return 1
        if n == 1:
            return x
        v = 1
        for _ in range(n):
            v = v * x
        return v


def for_specialize(a, b, c=4, d=5):
    return a + b + c + d


class TestStringMethods(unittest.TestCase):
    def assert_func_equal_on(self, fn1, fn2, *args, **kwargs):
        """
        Check that functions are the same, or raise the same exception
        """
        v1 = v2 = e1 = e2 = None
        try:
            v1 = fn1(*args, **kwargs)
        except Exception as _e1:
            e1 = _e1
        try:
            v2 = fn2(*args, **kwargs)
        except Exception as _e2:
            e2 = _e2
        if e1 or e2:
            # reraise exception, if there is only one
            if e1 is None:
                fn2(*args, **kwargs)
            if e2 is None:
                fn1(*args, **kwargs)
            if type(e1) != type(e2):
                # assume that fn1 is more correct, so raise exception from fn2
                fn2(*args, **kwargs)
            assert type(e1) == type(e2)
            assert e1.args == e2.args
        else:
            assert e1 is None
            assert e2 is None
            assert v1 == v2

    def check_partial_apply(
        self, func, args=None, kwds=None, expected_source=None, expected_new_bindings=None
    ):
        """
        Test that with given constants, optimized_ast transforms
        source to expected_source.
        It :expected_new_bindings: is given, we check that they
        are among new bindings returned by optimizer.
        """

        if args is None:
            args = tuple()
        if kwds is None:
            kwds = {}

        new_func = partial_apply(func, *args, **kwds)
        function = Function.from_object(new_func)

        if expected_source is not None:
            assert_ast_equal(function.tree, ast.parse(unindent(expected_source)).body[0])

        if expected_new_bindings is not None:
            for k in expected_new_bindings:
                if k not in function.globals:
                    print("Expected binding missing:", k)

                binding = function.globals[k]
                expected_binding = expected_new_bindings[k]

                assert binding == expected_binding

    def check_partial_fn(self, base_fn, get_partial_kwargs, get_kwargs):
        """
        Check that partial evaluation of base_fn with partial_args
        gives the same result on args_list
        as functools.partial(base_fn, partial_args)
        """
        fn = partial_apply(base_fn, **get_partial_kwargs())
        partial_fn = functools.partial(base_fn, **get_partial_kwargs())
        # call two times to check for possible side-effects
        self.assert_func_equal_on(partial_fn, fn, **get_kwargs())  # first
        self.assert_func_equal_on(partial_fn, fn, **get_kwargs())  # second

    def test_args_handling(self):
        def args_kwargs(a, b, c=None):
            return 1.0 * a / b * (c or 3)

        assert partial_apply(args_kwargs, 1)(2) == 1.0 / 2 * 3
        assert partial_apply(args_kwargs, 1, 2, 1)() == 1.0 / 2 * 1

    def test_kwargs_handling(self):
        def args_kwargs(a, b, c=None):
            return 1.0 * a / b * (c or 3)

        assert partial_apply(args_kwargs, c=4)(1, 2) == 1.0 / 2 * 4
        assert partial_apply(args_kwargs, 2, c=4)(6) == 2.0 / 6 * 4

    def test_if_on_stupid_power(self):
        for n in ("foo", 0, 1, 2, 3):
            for x in [0, 1, 0.01, 5e10]:
                self.check_partial_fn(stupid_power, lambda: dict(n=n), lambda: {"x": x})

    def test_if_on_recursive_power(self):
        for n in ("foo", 0, 1, 2, 3):
            for x in [0, 1, 0.01, 5e10]:
                self.check_partial_fn(smart_power, lambda: dict(n=n), lambda: {"x": x})

    def test_specialize_on(self):
        for names in ["b", "d", ("a", "b"), ("b", "c"), ("c", "d")]:
            with self.subTest(names=names):
                f = specialize_on(names)(for_specialize)
                assert f(1, 2) == for_specialize(1, 2)
                assert f(1, 2, d=10) == for_specialize(1, 2, d=10)
                assert f(a=3, b=4, d=2) == for_specialize(a=3, b=4, d=2)

    def test_specialize_on_missing_names(self):
        with self.assertRaises(ValueError):
            f = specialize_on("k")(for_specialize)

    def test_peval_closure(self):

        a = 1
        b = 2

        def f(x):
            return x + (a + b)

        ff = partial_eval(f)

        assert ff(1) == 1 + a + b

    def test_peval_prohibit_nested_definitions(self):
        def f(x):
            g = lambda y: x + y
            return g(x)

        with self.assertRaises(ValueError):
            ff = partial_eval(f)

    def test_peval_prohibit_async(self):

        f = function_from_source(
            """
            async def f(x):
                return x
            """
        ).eval()

        with self.assertRaises(ValueError):
            ff = partial_eval(f)


if __name__ == "__main__":
    unittest.main()
