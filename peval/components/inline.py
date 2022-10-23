import ast
from typing import List, Tuple, Dict, Any, Union

from peval.tags import get_inline_tag
from peval.core.reify import NONE_NODE, FALSE_NODE, TRUE_NODE
from peval.core.expression import try_peval_expression
from peval.core.function import Function
from peval.core.mangler import mangle
from peval.core.gensym import GenSym
from peval.tools import ast_walker, replace_fields
from peval.typing import ConstsDictT, PassOutputT


def inline_functions(tree: ast.AST, constants: ConstsDictT) -> PassOutputT:
    gen_sym = GenSym.for_tree(tree)
    constants = dict(constants)
    state, tree = _inline_functions_walker(dict(gen_sym=gen_sym, constants=constants), tree)
    return tree, state.constants


@ast_walker
class _inline_functions_walker:
    @staticmethod
    def handle_Call(state, node, prepend, **_):
        gen_sym = state.gen_sym
        constants = state.constants

        evaluated, fn = try_peval_expression(node.func, constants)

        if not evaluated or not get_inline_tag(fn):
            return state, node

        return_name, gen_sym = gen_sym("return")
        inlined_body, gen_sym, constants = _inline(node, gen_sym, return_name, constants)
        prepend(inlined_body)
        new_state = state.update(gen_sym=gen_sym, constants=constants)

        return new_state, ast.Name(id=return_name, ctx=ast.Load())


def _inline(node, gen_sym, return_name, constants):
    """
    Return a list of nodes, representing inlined function call.
    """
    fn = constants[node.func.id]
    fn_ast = Function.from_object(fn).tree

    gen_sym, new_fn_ast = mangle(gen_sym, fn_ast)

    parameter_assignments = _build_parameter_assignments(node, new_fn_ast)

    body_nodes = new_fn_ast.body

    gen_sym, inlined_body, new_bindings = _wrap_in_loop(gen_sym, body_nodes, return_name)
    constants = dict(constants)
    constants.update(new_bindings)

    return parameter_assignments + inlined_body, gen_sym, constants


def _wrap_in_loop(
    gen_sym: GenSym, body_nodes: List[ast.If], return_name: str
) -> Tuple[GenSym, List[ast.While], Dict[Any, Any]]:

    new_bindings = dict()

    return_flag, gen_sym = gen_sym("return_flag")

    # Adding an explicit return at the end of the function, if it's not present.
    if type(body_nodes[-1]) != ast.Return:
        body_nodes = body_nodes + [ast.Return(value=NONE_NODE)]

    inlined_code, returns_ctr, returns_in_loops = _replace_returns(
        body_nodes, return_name, return_flag
    )

    if returns_ctr == 1:
        # A shortcut for a common case with a single return at the end of the function.
        # No loop is required.
        inlined_body = inlined_code[:-1]
    else:
        # Multiple returns - wrap in a `while` loop.

        if returns_in_loops:
            # `return_flag` value will be used to detect returns from nested loops
            inlined_body = [
                ast.Assign(targets=[ast.Name(return_flag, ast.Store())], value=FALSE_NODE)
            ]
        else:
            inlined_body = []

        inlined_body.append(ast.While(test=TRUE_NODE, body=inlined_code, orelse=[]))

    return gen_sym, inlined_body, new_bindings


def _build_parameter_assignments(
    call_node: ast.Call, functiondef_node: ast.FunctionDef
) -> List[ast.Assign]:
    # currently variadic arguments are not supported
    assert all(type(arg) != ast.Starred for arg in call_node.args)
    assert all(kw.arg is not None for kw in call_node.keywords)
    parameter_assignments = []
    for callee_arg, fn_arg in zip(call_node.args, functiondef_node.args.args):
        parameter_assignments.append(
            ast.Assign(targets=[ast.Name(fn_arg.arg, ast.Store())], value=callee_arg)
        )
    return parameter_assignments


def _handle_loop(node, state, ctx, visit_after, visiting_after, walk_field, **_):
    if not visiting_after:
        # Need to traverse fields explicitly since for the purposes of _replace_returns(),
        # the body of `orelse` field is not inside a loop.
        state = state.update(loop_nesting_ctr=state.loop_nesting_ctr + 1)
        state, new_body = walk_field(state, node.body, block_context=True)
        state = state.update(loop_nesting_ctr=state.loop_nesting_ctr - 1)
        state, new_orelse = walk_field(state, node.orelse, block_context=True)

        visit_after()
        return state, replace_fields(node, body=new_body, orelse=new_orelse)
    else:
        # If there was a return inside a loop, append a conditional break
        # to propagate the return otside all nested loops
        if state.return_inside_a_loop:
            new_nodes = [
                node,
                ast.If(test=ast.Name(id=ctx.return_flag_var), body=[ast.Break()], orelse=[]),
            ]
        else:
            new_nodes = node

        # if we are at root level, reset the return-inside-a-loop flag
        if state.loop_nesting_ctr == 0:
            state = state.update(return_inside_a_loop=False)

        return state, new_nodes


@ast_walker
class _replace_returns_walker:
    """Replace returns with variable assignment + break."""

    @staticmethod
    def handle_For(state, node, ctx, visit_after, visiting_after, **kwds):
        return _handle_loop(node, state, ctx, visit_after, visiting_after, **kwds)

    @staticmethod
    def handle_While(state, node, ctx, visit_after, visiting_after, **kwds):
        return _handle_loop(node, state, ctx, visit_after, visiting_after, **kwds)

    @staticmethod
    def handle_Return(state, node, ctx, **_):

        state_update = dict(returns_ctr=state.returns_ctr + 1)

        new_nodes = [
            ast.Assign(targets=[ast.Name(id=ctx.return_var, ctx=ast.Store())], value=node.value)
        ]

        if state.loop_nesting_ctr > 0:
            new_nodes.append(
                ast.Assign(
                    targets=[ast.Name(id=ctx.return_flag_var, ctx=ast.Store())],
                    value=TRUE_NODE,
                )
            )
            state_update.update(return_inside_a_loop=True, returns_in_loops=True)

        new_nodes.append(ast.Break())

        return state.update(state_update), new_nodes


def _replace_returns(
    nodes: List[ast.AST], return_var: str, return_flag_var: str
) -> Tuple[List[Union[ast.If, ast.Assign, ast.Break]], int, bool]:
    state, new_nodes = _replace_returns_walker(
        dict(
            returns_ctr=0,
            loop_nesting_ctr=0,
            returns_in_loops=False,
            return_inside_a_loop=False,
        ),
        nodes,
        ctx=dict(return_var=return_var, return_flag_var=return_flag_var),
    )
    return new_nodes, state.returns_ctr, state.returns_in_loops
