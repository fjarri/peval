import ast
from typing import Tuple

from peval.tools import immutabledict, ast_walker
from peval.core.scope import analyze_scope
from peval.tools.immutable import immutableset, immutableadict
from peval.core.gensym import GenSym
from peval.typing import NameNodeT
import peval.tools.immutable


def _visit_local(
    gen_sym: GenSym, node: NameNodeT, to_mangle: immutableset, mangled: immutableadict
) -> Tuple[GenSym, NameNodeT, peval.tools.immutable.immutabledict]:
    """
    Replacing known variables with literal values
    """
    is_name = type(node) == ast.Name

    node_id = node.id if is_name else node.arg

    if node_id in to_mangle:

        if node_id in mangled:
            mangled_id = mangled[node_id]
        else:
            mangled_id, gen_sym = gen_sym("mangled")
            mangled = mangled.set(node_id, mangled_id)

        if is_name:
            new_node = ast.Name(id=mangled_id, ctx=node.ctx)
        else:
            new_node = ast.arg(arg=mangled_id, annotation=node.annotation)

    else:
        new_node = node

    return gen_sym, new_node, mangled


@ast_walker
class _mangle:
    """
    Mangle all variable names, returns.
    """

    @staticmethod
    def handle_arg(state, node, ctx, **_):
        gen_sym, new_node, mangled = _visit_local(state.gen_sym, node, ctx.fn_locals, state.mangled)
        new_state = state.update(gen_sym=gen_sym, mangled=mangled)
        return new_state, new_node

    @staticmethod
    def handle_Name(state, node, ctx, **_):
        gen_sym, new_node, mangled = _visit_local(state.gen_sym, node, ctx.fn_locals, state.mangled)
        new_state = state.update(gen_sym=gen_sym, mangled=mangled)
        return new_state, new_node


def mangle(gen_sym: GenSym, node: ast.FunctionDef) -> Tuple[GenSym, ast.FunctionDef]:
    fn_locals = analyze_scope(node).locals
    state, new_node = _mangle(
        dict(gen_sym=gen_sym, mangled=immutabledict()),
        node,
        ctx=dict(fn_locals=fn_locals),
    )
    return state.gen_sym, new_node
