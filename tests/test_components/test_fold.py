import sys

import pytest

from peval.components import fold
from peval import pure

from tests.utils import check_component


def dummy(x):
    a = 1
    if a > 2:
        b = 3
        c = 4 + 6
    else:
        b = 2
        c = 3 + a
    return a + b + c + x


def test_fold():
    check_component(
        fold, dummy,
        expected_source="""
            def dummy(x):
                a = 1
                if False:
                    b = 3
                    c = 10
                else:
                    b = 2
                    c = 4
                return 1 + b + c + x
            """)


def test_if_visit_only_true_branch():

    # This optimization can potentially save some time during constant propagation
    # (by not evaluating the functions that will be eliminated anyway).
    # Not implemented at the moment.

    pytest.xfail()

    global_state = dict(cnt=0)

    @pure
    def inc():
        global_state['cnt'] += 1
        return True

    def if_body():
        if a:
            inc()

    def if_else():
        if a:
            dec()
        else:
            inc()

    check_component(
        fold, if_body, additional_bindings=dict(a=False, inc=inc),
        expected_source="""
            def if_body():
                if False:
                    inc()
            """)
    assert global_state['cnt'] == 0

    check_component(
        fold, if_else, additional_bindings=dict(a=False, inc=inc),
        expected_source="""
            def if_else():
                if False:
                    dec()
                else:
                    inc()
            """)
    assert global_state['cnt'] == 1


@pure
def int32():
    return int


def func_annotations():
    x = int
    a: x
    x = float
    b: x
    c: int32()


def test_variable_annotation():
    print()
    check_component(
        fold, func_annotations,
        expected_source="""
            def func_annotations():
                x = int
                a: __peval_temp_1
                x = float
                b: __peval_temp_2
                c: __peval_temp_3
            """,
        expected_new_bindings=dict(
            __peval_temp_1=int,
            __peval_temp_2=float,
            __peval_temp_3=int))
