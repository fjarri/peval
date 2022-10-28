from __future__ import print_function

import pytest

from peval.components.prune_cfg import prune_cfg
from tests.utils import check_component


def test_if_true():
    """
    Eliminate if test, if the value is known at compile time
    """

    true_values = [True, 1, 2.0, object(), "foo", int]
    assert all(true_values)

    def f_if():
        if x:
            print("x is True")

    for x in true_values:
        check_component(
            prune_cfg,
            f_if,
            additional_bindings=dict(x=x),
            expected_source="""
                def f_if():
                    print('x is True')
                """,
        )

    def f_if_else():
        if x:
            print("x is True")
        else:
            print("x is False")

    check_component(
        prune_cfg,
        f_if_else,
        additional_bindings=dict(x=2),
        expected_source="""
            def f_if_else():
                print("x is True")
            """,
    )


def test_if_false_elimination():
    """
    Eliminate if test, when test is false
    """

    class Falsy:
        def __bool__(self):
            # For Python 3
            return False

    false_values = [0, "", [], {}, set(), False, None, Falsy()]
    assert not any(false_values)

    def f_if():
        if x:
            print("x is True")

    for x in false_values:
        check_component(
            prune_cfg,
            f_if,
            additional_bindings=dict(x=x),
            expected_source="""
                def f_if():
                    pass
                """,
        )

    def f_if_else():
        if x:
            print("x is True")
        else:
            print("x is False")

    check_component(
        prune_cfg,
        f_if_else,
        additional_bindings=dict(x=False),
        expected_source="""
            def f_if_else():
                print("x is False")
            """,
    )


def test_if_no_elimination():
    """
    Test that there is no unneeded elimination of if test
    """

    def f(x):
        if x:
            a = 1
        else:
            a = 2

    check_component(prune_cfg, f, dict(y=2))


def test_visit_all_branches():
    def f():
        if x > 0:
            if True:
                x += 1
        else:
            if False:
                return 0

    check_component(
        prune_cfg,
        f,
        {},
        expected_source="""
            def f():
                if x > 0:
                    x += 1
                else:
                    pass
            """,
    )


def test_remove_pass():
    def f(x):
        x += 1
        pass
        x += 1

    check_component(
        prune_cfg,
        f,
        {},
        expected_source="""
            def f(x):
                x += 1
                x += 1
            """,
    )


def test_not_remove_pass():
    def f(x):
        pass

    check_component(prune_cfg, f, {})


def test_remove_code_after_jump():
    def f(x):
        x += 1
        return x
        x += 1

    check_component(
        prune_cfg,
        f,
        {},
        expected_source="""
            def f(x):
                x += 1
                return x
            """,
    )


def test_not_simplify_while():
    def f(x):
        while x > 1:
            x += 1
        else:
            x = 10

    check_component(prune_cfg, f, {})


def test_simplify_while():
    def f(x):
        while x > 1:
            x += 1
            raise Exception
        else:
            x = 10

    check_component(
        prune_cfg,
        f,
        {},
        expected_source="""
            def f(x):
                if x > 1:
                    x += 1
                    raise Exception
                else:
                    x = 10
            """,
    )


def test_simplify_while_with_break():
    def f(x):
        while x > 1:
            x += 1
            break
        else:
            x = 10

    check_component(
        prune_cfg,
        f,
        {},
        expected_source="""
            def f(x):
                if x > 1:
                    x += 1
                else:
                    x = 10
            """,
    )
