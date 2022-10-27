from __future__ import print_function

import ast
import difflib
from ast import dump

from peval.tools import ast_equal, unindent
from peval.core.function import Function

try:
    # raise ImportError
    from ast import fix_missing_locations
    from ast import unparse as _unparse
except ImportError:
    from astunparse import unparse

    def _if_expr(a, b):
        return "if (" + str(a) + " > " + str(b) + "):"

else:

    def _if_expr(a, b):
        return "if " + str(a) + " > " + str(b) + ":"

    def unparse(n):
        fix_missing_locations(n)
        return _unparse(n)


def normalize_source(source):

    # trim newlines and trailing spaces --- some pretty printers add it

    # Note: this may change multiline string literals,
    # but we are assuming we won't have the ones susceptible to this in tests.
    source = "\n".join(line.rstrip() for line in source.split("\n"))

    source = source.strip("\n")

    return source


def print_diff(test, expected):

    print("\n" + "=" * 40 + " expected:\n\n" + expected)
    print("\n" + "=" * 40 + " result:\n\n" + test)
    print("\n")

    expected_lines = expected.split("\n")
    test_lines = test.split("\n")

    for line in difflib.unified_diff(
        expected_lines, test_lines, fromfile="expected", tofile="test"
    ):
        print(line)


def assert_ast_equal(test_ast, expected_ast, print_ast=True):
    """
    Check that test_ast is equal to expected_ast,
    printing helpful error message if they are not equal
    """

    equal = ast_equal(test_ast, expected_ast)
    if not equal:

        if print_ast:
            expected_ast_str = dump(expected_ast)
            test_ast_str = dump(test_ast)
            print_diff(test_ast_str, expected_ast_str)

        expected_source = normalize_source(unparse(expected_ast))
        test_source = normalize_source(unparse(test_ast))
        print_diff(test_source, expected_source)

    assert equal


def check_component(
    component,
    func,
    additional_bindings=None,
    expected_source=None,
    expected_new_bindings=None,
):

    function = Function.from_object(func)
    bindings = function.get_external_variables()
    if additional_bindings is not None:
        bindings.update(additional_bindings)

    new_tree, new_bindings = component(function.tree, bindings)

    if expected_source is None:
        expected_ast = function.tree
    else:
        expected_ast = ast.parse(unindent(expected_source)).body[0]

    assert_ast_equal(new_tree, expected_ast)

    if expected_new_bindings is not None:
        for k in expected_new_bindings:
            if k not in new_bindings:
                print("Expected binding missing:", k)

            binding = new_bindings[k]
            expected_binding = expected_new_bindings[k]
            assert binding == expected_binding


def function_from_source(source, globals_=None):
    """
    A helper function to construct a Function object from source.
    Helpful if you need to create a test function with syntax
    that's not supported by some of the Py versions
    that are used to run tests or build docs,
    or if you need a function with custom __future__ imports.
    """

    module = ast.parse(unindent(source))
    ast.fix_missing_locations(module)

    for stmt in module.body:
        if type(stmt) in (ast.FunctionDef, ast.AsyncFunctionDef):
            tree = stmt
            name = stmt.name
            break
    else:
        raise ValueError("No function definitions found in the provided source")

    code_object = compile(module, "<nofile>", "exec", dont_inherit=True)
    locals_ = {}
    eval(code_object, globals_, locals_)

    function_obj = locals_[name]
    function_obj._peval_source = unparse(tree)

    return Function.from_object(function_obj)
