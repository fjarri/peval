import ast
import typing

from peval.tools import replace_fields, ast_transformer, ast_inspector
from peval.core.expression import try_peval_expression
from peval.tools import ast_equal
from peval.typing import ConstsDictT, PassOutputT

def prune_cfg(node: ast.AST, bindings: ConstsDictT) -> PassOutputT:

    while True:

        new_node = node

        for func in (remove_unreachable_statements, simplify_loops, remove_unreachable_branches):
            new_node = func(new_node, ctx=dict(bindings=bindings))

        if ast_equal(new_node, node):
            break

        node = new_node

    return new_node, bindings


@ast_transformer
def remove_unreachable_statements(node, walk_field, **kwds):
    for attr in ('body', 'orelse'):
        if hasattr(node, attr):
            old_list = getattr(node, attr)
            not_list = isinstance(node, ast.AST)
            if not_list:
                old_list = [old_list]
            new_list = filter_block(old_list)
            if new_list is not old_list:
                new_list = walk_field(new_list, block_context=True)
                if not_list:
                    new_list = new_list[0]
                kwds = {attr: new_list}
                node = replace_fields(node, **kwds)
    return node


def filter_block(node_list: typing.List[ast.AST]) -> typing.List[ast.AST]:
    """
    Remove no-op code (``pass``), or any code after
    an unconditional jump (``return``, ``break``, ``continue``, ``raise``).
    """
    if len(node_list) == 1:
        return node_list

    new_list = []
    for node in node_list:
        if type(node) == ast.Pass:
            continue
        new_list.append(node)
        if type(node) in (ast.Return, ast.Break, ast.Continue, ast.Raise):
            break
    if len(new_list) == len(node_list):
        return node_list
    else:
        return new_list


@ast_inspector
class _find_jumps:

    @staticmethod
    def handle_FunctionDef(skip_fields, **_):
        skip_fields()

    @staticmethod
    def handle_ClassDef(skip_fields, **_):
        skip_fields()

    @staticmethod
    def handle_Break(state, **_):
        return state.update(jumps_counter=state.jumps_counter + 1)

    @staticmethod
    def handle_Raise(state, **_):
        return state.update(jumps_counter=state.jumps_counter + 1)

    @staticmethod
    def handle_Return(state, **_):
        return state.update(jumps_counter=state.jumps_counter + 1)


def find_jumps(node: typing.List[ast.AST]) -> int:
    return _find_jumps(dict(jumps_counter=0), node).jumps_counter


@ast_transformer
class simplify_loops:

    @staticmethod
    def handle_While(node, **_):
        last_node = node.body[-1]
        unconditional_jump = type(last_node) in (ast.Break, ast.Raise, ast.Return)
        if unconditional_jump and find_jumps(node.body) == 1:
            if type(last_node) == ast.Break:
                new_body = node.body[:-1]
            else:
                new_body = node.body
            return ast.If(test=node.test, body=new_body, orelse=node.orelse)
        else:
            return node


@ast_transformer
class remove_unreachable_branches:

    @staticmethod
    def handle_If(node, ctx, walk_field, **_):
        evaluated, test = try_peval_expression(node.test, ctx.bindings)
        if evaluated:
            taken_node = node.body if test else node.orelse
            new_node = walk_field(taken_node, block_context=True)
            return new_node
        else:
            return node
