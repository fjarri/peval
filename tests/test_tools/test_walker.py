import copy
import ast
import inspect
import sys

import pytest

from peval.tools import (
    unindent,
    replace_fields,
    ast_inspector,
    ast_transformer,
    ast_walker,
)
from peval.tools.walker import _Walker

from utils import assert_ast_equal


def get_ast(function):
    if isinstance(function, str):
        return ast.parse(unindent(function))
    else:
        return ast.parse(inspect.getsource(function))


def check_mutation(node, walker):
    node_ref = copy.deepcopy(node)
    new_node = walker(node)
    assert ast.dump(node) != ast.dump(new_node)
    assert_ast_equal(node, node_ref)
    return new_node


def dummy(x, y):
    c = 4
    a = 1


def dummy_blocks(x, y):
    a = 1
    if x:
        b = 2
    c = 3


def dummy_nested(x, y):
    def inner_function(z):
        return z

    return inner_function


def dummy_if():
    if a:
        if b:
            pass


global_var = 1


def dummy_globals():
    global global_var
    return global_var


def test_inspector():
    @ast_inspector
    def collect_numbers(state, node, **kwds):
        if isinstance(node, ast.Num):
            return state.with_(numbers=state.numbers | {node.n})
        else:
            return state

    node = get_ast(dummy)
    state = collect_numbers(dict(numbers=frozenset()), node)
    assert state.numbers == set([1, 4])


def test_walk_list():
    @ast_inspector
    def collect_numbers(state, node, **kwds):
        if isinstance(node, ast.Num):
            return state.with_(numbers=state.numbers | {node.n})
        else:
            return state

    node = get_ast(dummy)
    state = collect_numbers(dict(numbers=frozenset()), node.body)
    assert state.numbers == set([1, 4])


def test_walker():
    @ast_walker
    def process_numbers(state, node, **kwds):
        if isinstance(node, ast.Num):
            return state.with_(numbers=state.numbers | {node.n}), ast.Num(n=node.n + 1)
        else:
            return state, node

    node = get_ast(dummy)
    state, new_node = process_numbers(dict(numbers=frozenset()), node)

    assert state.numbers == set([1, 4])
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 5
            a = 2
        """
        ),
    )


# Transformations


def test_change_node():
    @ast_transformer
    def change_name(node, **kwds):
        if isinstance(node, ast.Name) and node.id == "a":
            return ast.Name(id="b", ctx=node.ctx)
        else:
            return node

    node = get_ast(dummy)
    new_node = check_mutation(node, change_name)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 4
            b = 1
        """
        ),
    )


def test_add_statement():
    @ast_transformer
    def add_statement(node, **kwds):
        if isinstance(node, ast.Assign):
            return [node, ast.parse("b = 2").body[0]]
        else:
            return node

    node = get_ast(dummy)
    new_node = check_mutation(node, add_statement)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 4
            b = 2
            a = 1
            b = 2
        """
        ),
    )


def test_list_element():
    """
    Tests the removal of an AST node that is an element of a list
    referenced by a field of the parent node.
    """

    @ast_transformer
    def remove_list_element(node, **kwds):
        if isinstance(node, ast.Assign) and node.targets[0].id == "a":
            return None
        else:
            return node

    node = get_ast(dummy)
    new_node = check_mutation(node, remove_list_element)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 4
        """
        ),
    )


def test_remove_field():
    """
    Tests the removal of an AST node that is referenced by a field of the parent node.
    """

    @ast_transformer
    def remove_field(node, **kwds):
        if isinstance(node, ast.arg) and node.arg == "x":
            return None
        else:
            return node

    node = get_ast(dummy)
    new_node = check_mutation(node, remove_field)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(y):
            c = 4
            a = 1
        """
        ),
    )


# Error checks


def test_walker_contract():
    """
    Test that the backend _Walker cannot be created
    with both ``transform`` and ``inspect`` set to ``False``.
    """

    def pass_through(node, **kwds):
        pass

    with pytest.raises(ValueError):
        w = _Walker(pass_through)


def test_wrong_root_type():
    @ast_inspector
    def pass_through(node, **kwds):
        pass

    with pytest.raises(TypeError):
        pass_through(None, {})


def test_wrong_root_return_value():
    @ast_transformer
    def wrong_root_return_value(node, **kwds):
        return 1

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        wrong_root_return_value(node)


def test_wrong_field_return_value():
    @ast_transformer
    def wrong_field_return_value(node, **kwds):
        if isinstance(node, ast.Num):
            return 1
        else:
            return node

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        wrong_field_return_value(node)


def test_wrong_list_return_value():
    @ast_transformer
    def wrong_list_return_value(node, **kwds):
        if isinstance(node, ast.Assign):
            return 1
        else:
            return node

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        wrong_list_return_value(node)


def test_walker_call_signature():
    @ast_walker
    def pass_through(state, node, **kwds):
        return state, node

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        pass_through(node)


def test_inspector_call_signature():
    @ast_inspector
    def pass_through(state, node, **kwds):
        return state, node

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        pass_through(node)


def test_transformer_call_signature():
    @ast_transformer
    def pass_through(node, **kwds):
        return node

    node = get_ast(dummy)
    with pytest.raises(TypeError):
        pass_through({}, node)


# Handler dispatchers


def test_dispatched_walker():
    @ast_inspector
    class collect_numbers_with_default:
        @staticmethod
        def handle_Num(state, node, **kwds):
            return state.with_(numbers=state.numbers | {node.n})

        @staticmethod
        def handle_Constant(state, node, **kwds):
            return state.with_(numbers=state.numbers | {node.n})

        @staticmethod
        def handle(state, node, **kwds):
            return state

    @ast_inspector
    class collect_numbers:
        @staticmethod
        def handle_Num(state, node, **kwds):
            return state.with_(numbers=state.numbers | {node.n})

        @staticmethod
        def handle_Constant(state, node, **kwds):
            return state.with_(numbers=state.numbers | {node.n})

    node = get_ast(dummy)

    state = collect_numbers(dict(numbers=frozenset()), node)
    assert state.numbers == set([1, 4])

    state = collect_numbers_with_default(dict(numbers=frozenset()), node)
    assert state.numbers == set([1, 4])


# Advanced functionality


def test_walk_children():
    @ast_transformer
    def mangle_outer_functions(node, **kwds):
        if isinstance(node, ast.FunctionDef):
            return replace_fields(node, name="__" + node.name)
        else:
            return node

    @ast_transformer
    def mangle_all_functions(node, walk_field, **kwds):
        if isinstance(node, ast.FunctionDef):
            return replace_fields(
                node, name="__" + node.name, body=walk_field(node.body, block_context=True)
            )
        else:
            return node

    node = get_ast(dummy_nested)

    new_node = mangle_outer_functions(node)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def __dummy_nested(x, y):
            def inner_function(z):
                return z
            return inner_function
        """
        ),
    )

    new_node = mangle_all_functions(node)
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def __dummy_nested(x, y):
            def __inner_function(z):
                return z
            return inner_function
        """
        ),
    )


def test_global_context():
    @ast_transformer
    def rename(node, ctx, **kwds):
        if isinstance(node, ast.Name) and node.id == ctx.old_name:
            return ast.Name(id=ctx.new_name, ctx=node.ctx)
        else:
            return node

    node = get_ast(dummy)
    new_node = rename(node, ctx=dict(old_name="c", new_name="d"))

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            d = 4
            a = 1
        """
        ),
    )


def test_prepend():
    @ast_transformer
    def prepender(node, prepend, **kwds):
        if isinstance(node, ast.Name):
            if node.id == "a":
                prepend(
                    [ast.Assign(targets=[ast.Name(id="k", ctx=ast.Store())], value=ast.Num(n=10))]
                )
                return node
            elif node.id == "b":
                prepend(
                    [ast.Assign(targets=[ast.Name(id="l", ctx=ast.Store())], value=ast.Num(n=20))]
                )
                return ast.Name(id="d", ctx=node.ctx)
            elif node.id == "c":
                prepend(
                    [ast.Assign(targets=[ast.Name(id="m", ctx=ast.Store())], value=ast.Num(n=30))]
                )
                return node
            else:
                return node
        else:
            return node

    node = get_ast(dummy_blocks)
    new_node = prepender(node)

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy_blocks(x, y):
            k = 10
            a = 1
            if x:
                l = 20
                d = 2
            m = 30
            c = 3
        """
        ),
    )


def test_visit_after():
    @ast_transformer
    def simplify(node, visit_after, visiting_after, **kwds):
        if isinstance(node, ast.If):
            if not visiting_after:
                visit_after()
                return node

            # This wouldn't work if we didn't simplify the child nodes first
            if len(node.orelse) == 0 and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                return ast.Pass()
            else:
                return node
        else:
            return node

    node = get_ast(dummy_if)
    new_node = simplify(node)

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy_if():
            pass
        """
        ),
    )


def test_block_autofix():
    # This transformer removes If nodes from statement blocks,
    # but it has no way to check whether the resulting body still has some nodes or not.
    # That's why the walker adds a Pass node automatically if after all the transformations
    # a statement block turns out to be empty.
    @ast_transformer
    def delete_ifs(node, **kwds):
        if isinstance(node, ast.If):
            return None
        else:
            return node

    node = get_ast(dummy_if)
    new_node = delete_ifs(node)

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy_if():
            pass
        """
        ),
    )


def test_walk_field_transform():
    @ast_transformer
    def increment(node, walk_field, **kwds):
        if isinstance(node, ast.Assign):
            return replace_fields(node, targets=node.targets, value=walk_field(node.value))
        elif isinstance(node, ast.Num):
            return ast.Num(n=node.n + 1)
        else:
            return node

    node = get_ast(dummy)
    new_node = increment(node)

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 5
            a = 2
        """
        ),
    )


def test_walk_field_inspect():
    @ast_inspector
    def names_and_nums(state, node, walk_field, **kwds):
        if isinstance(node, ast.Assign):
            state = walk_field(state, node.value)
            return state.with_(objs=state.objs | {node.targets[0].id})
        elif isinstance(node, ast.Num):
            return state.with_(objs=state.objs | {node.n})
        else:
            return state

    node = get_ast(dummy)
    state = names_and_nums(dict(objs=frozenset()), node)
    assert state.objs == set(["a", "c", 1, 4])


def test_walk_field_transform_inspect():
    @ast_walker
    def names_and_incremented_nums(state, node, walk_field, **kwds):
        if isinstance(node, ast.Assign):
            state, value_node = walk_field(state, node.value)
            new_node = replace_fields(node, targets=node.targets, value=value_node)
            new_state = state.with_(objs=state.objs | {node.targets[0].id})
            return new_state, new_node
        elif isinstance(node, ast.Num):
            return state.with_(objs=state.objs | {node.n}), ast.Num(n=node.n + 1)
        else:
            return state, node

    node = get_ast(dummy)
    state, new_node = names_and_incremented_nums(dict(objs=frozenset()), node)
    assert state.objs == set(["a", "c", 1, 4])
    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 5
            a = 2
        """
        ),
    )


def test_skip_fields():
    @ast_transformer
    def increment(node, skip_fields, **kwds):
        if isinstance(node, ast.Assign) and node.targets[0].id == "c":
            skip_fields()

        if isinstance(node, ast.Num):
            return ast.Num(n=node.n + 1)
        else:
            return node

    node = get_ast(dummy)
    new_node = increment(node)

    assert_ast_equal(
        new_node,
        get_ast(
            """
        def dummy(x, y):
            c = 4
            a = 2
        """
        ),
    )


def test_globals():
    """
    A regression test. The nodes for ``globals`` and ``nonlocals`` statements
    contain lists of strings, which confused the walker, which was expecting nodes there
    and tried to walk them.
    """

    @ast_inspector
    def pass_through(node, state, **kwds):
        return state

    node = get_ast(dummy_globals)
    state = pass_through({}, node)
