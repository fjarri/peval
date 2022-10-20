import ast
import typing

from peval.tools import ast_transformer, replace_fields
from peval.core.scope import analyze_scope
from peval.typing import ConstsDictT, PassOutputT


def prune_assignments(node: ast.AST, constants: ConstsDictT) -> PassOutputT:
    scope = analyze_scope(node.body)
    node = remove_unused_assignments(node, ctx=dict(locals_used=scope.locals_used))
    node = remove_simple_assignments(node)
    return node, constants


@ast_transformer
class remove_unused_assignments:
    @staticmethod
    def handle_Assign(node, ctx, **_):
        if all(type(target) == ast.Name for target in node.targets):
            names = set(target.id for target in node.targets)
            if ctx.locals_used.isdisjoint(names):
                return None
            else:
                return node
        else:
            return node


def remove_simple_assignments(node: typing.Union[ast.FunctionDef, ast.Module]) -> typing.Union[ast.FunctionDef, ast.Module]:
    """
    Remove one assigment of the form `<variable> = <variable>` at a time,
    touching only the top level statements of the block.
    """

    remaining_nodes = list(node.body)
    new_nodes = []

    while len(remaining_nodes) > 0:
        cur_node = remaining_nodes.pop(0)
        if type(cur_node) == ast.Assign:
            can_remove, dest_name, src_name = _can_remove_assignment(cur_node, remaining_nodes)
            if can_remove:
                remaining_nodes = replace_name(
                    remaining_nodes, ctx=dict(dest_name=dest_name, src_name=src_name))
            else:
                new_nodes.append(cur_node)
        else:
            new_nodes.append(cur_node)

    if len(new_nodes) == len(node.body):
        return node

    return replace_fields(node, body=new_nodes)


def _can_remove_assignment(assign_node: ast.Assign, node_list: typing.List[ast.AST]) -> typing.Union[typing.Tuple[bool, str, str], typing.Tuple[bool, None, None]]:
    """
    Can remove it if:
    * it is "simple"
    * result it not used in "Store" context elsewhere
    """
    if (len(assign_node.targets) == 1 and type(assign_node.targets[0]) == ast.Name
            and type(assign_node.value) == ast.Name):
        src_name = assign_node.value.id
        dest_name = assign_node.targets[0].id
        if dest_name not in analyze_scope(node_list).locals:
            return True, dest_name, src_name
    return False, None, None


@ast_transformer
class replace_name:
    @staticmethod
    def handle_Name(node, ctx, **_):
        if type(node.ctx) == ast.Load and node.id == ctx.dest_name:
            return replace_fields(node, id=ctx.src_name)
        else:
            return node
