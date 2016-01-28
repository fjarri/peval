from __future__ import print_function, division

import ast
import sys

import pytest

from peval.core.gensym import GenSym
from peval.tags import inline
from peval.components.inline import (
    inline_functions, _replace_returns, _wrap_in_loop, _build_parameter_assignments)

from tests.utils import check_component, unindent, assert_ast_equal


def _test_replace_returns(source, expected_source, expected_returns_ctr, expected_returns_in_loops):

    nodes = ast.parse(unindent(source)).body

    return_var = 'return_var'
    return_flag_var = 'return_flag'

    expected_source = expected_source.format(
        return_var=return_var, return_flag=return_flag_var)
    expected_nodes = ast.parse(unindent(expected_source)).body

    new_nodes, returns_ctr, returns_in_loops = _replace_returns(
        nodes, return_var, return_flag_var)

    assert_ast_equal(new_nodes, expected_nodes)
    assert returns_ctr == expected_returns_ctr
    assert returns_in_loops == expected_returns_in_loops


class TestReplaceReturns:

    def test_single_return(self):
        _test_replace_returns(
            source="""
                b = y + list(x)
                return b
                """,
            expected_source="""
                b = y + list(x)
                {return_var} = b
                break
                """,
            expected_returns_ctr=1,
            expected_returns_in_loops=False)


    def test_several_returns(self):
        _test_replace_returns(
            source="""
                if a:
                    return y + list(x)
                elif b:
                    return b
                return c
                """,
            expected_source="""
                if a:
                    {return_var} = y + list(x)
                    break
                elif b:
                    {return_var} = b
                    break
                {return_var} = c
                break
                """,
            expected_returns_ctr=3,
            expected_returns_in_loops=False)


    def test_returns_in_loops(self):
        _test_replace_returns(
            source="""
                for x in range(10):
                    for y in range(10):
                        if x + y > 10:
                            return 2
                    else:
                        return 3

                if x:
                    return 1

                while z:
                    if z:
                        return 3

                return 0
                """,
            expected_source="""
                for x in range(10):
                    for y in range(10):
                        if ((x + y) > 10):
                            {return_var} = 2
                            {return_flag} = True
                            break
                    else:
                        {return_var} = 3
                        {return_flag} = True
                        break
                    if {return_flag}:
                        break
                if {return_flag}:
                    break
                if x:
                    {return_var} = 1
                    break
                while z:
                    if z:
                        {return_var} = 3
                        {return_flag} = True
                        break
                if {return_flag}:
                    break
                {return_var} = 0
                break
                """,
            expected_returns_ctr=5,
            expected_returns_in_loops=True)


    def test_returns_in_loop_else(self):
        _test_replace_returns(
            source="""
                for y in range(10):
                    x += y
                else:
                    return 1

                return 0
                """,
            expected_source="""
                for y in range(10):
                    x += y
                else:
                    {return_var} = 1
                    break

                {return_var} = 0
                break
                """,
            expected_returns_ctr=2,
            expected_returns_in_loops=False)


def _test_build_parameter_assignments(call_str, signature_str, expected_assignments):

    call_node = ast.parse("func(" + call_str + ")").body[0].value
    signature_node = ast.parse("def func(" + signature_str + "):\n\tpass").body[0]

    assignments = _build_parameter_assignments(call_node, signature_node)

    expected_assignments = ast.parse(unindent(expected_assignments)).body

    assert_ast_equal(assignments, expected_assignments)


class TestBuildParameterAssignments:

    def test_positional_args(self):
        _test_build_parameter_assignments(
            "a, b, 1, 3",
            "c, d, e, f",
            """
            c = a
            d = b
            e = 1
            f = 3
            """)


def _test_wrap_in_loop(body_src, expected_src, format_kwds={}, expected_bindings={}):
    gen_sym = GenSym.for_tree()

    body_nodes = ast.parse(unindent(body_src)).body

    return_name = '_return_val'

    gen_sym, inlined_body, new_bindings = _wrap_in_loop(gen_sym, body_nodes, return_name)

    expected_body = ast.parse(unindent(expected_src.format(
        return_val=return_name, **format_kwds))).body

    assert_ast_equal(inlined_body, expected_body)

    assert new_bindings == expected_bindings


class TestWrapInLoop:

    def test_no_return(self):
        _test_wrap_in_loop(
            """
            do_something()
            do_something_else()
            """,
            """
            do_something()
            do_something_else()
            {return_val} = None
            """)

    def test_single_return(self):
        _test_wrap_in_loop(
            """
            do_something()
            do_something_else()
            return 1
            """,
            """
            do_something()
            do_something_else()
            {return_val} = 1
            """
            )

    def test_several_returns(self):
        _test_wrap_in_loop(
            """
            if a > 4:
                do_something()
                return 2
            do_something_else()
            return 1
            """,
            """
            while True:
                if a > 4:
                    do_something()
                    {return_val} = 2
                    break
                do_something_else()
                {return_val} = 1
                break
            """)


    def test_returns_in_loops(self):
        _test_wrap_in_loop(
            """
            for x in range(10):
                do_something()
                if b:
                    return 2
            do_something_else()
            return 1
            """,
            """
            {return_flag} = False
            while True:
                for x in range(10):
                    do_something()
                    if b:
                        {return_val} = 2
                        {return_flag} = True
                        break
                if {return_flag}:
                    break
                do_something_else()
                {return_val} = 1
                break
            """,
            dict(return_flag='__peval_return_flag_1'))



def test_component():

    @inline
    def inlined(y):
        l = []
        for _ in range(y):
            l.append(y.do_stuff())
        return l

    def outer(x):
        a = x.foo()
        if a:
            b = a * 10
        a = b + inlined(x)
        return a

    check_component(
        inline_functions, outer,
        expected_source="""
            def outer(x):
                a = x.foo()
                if a:
                    b = (a * 10)
                __peval_mangled_1 = x
                __peval_mangled_2 = []
                for __peval_mangled_3 in range(__peval_mangled_1):
                    __peval_mangled_2.append(__peval_mangled_1.do_stuff())
                __peval_return_1 = __peval_mangled_2
                a = (b + __peval_return_1)
                return a
        """)

