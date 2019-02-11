import ast

from peval.core.gensym import GenSym
from peval.tools import replace_fields, ast_walker, immutabledict
from peval.core.expression import peval_expression

from astunparse import dump


@ast_walker
class _peval_function_header:

    @staticmethod
    def handle_arg(state, node, ctx, **_):
        result, gen_sym = peval_expression(node.annotation, state.gen_sym, ctx.constants)
        new_bindings = state.new_bindings.update(result.temp_bindings)

        state = state.update(gen_sym=gen_sym, new_bindings=new_bindings)
        node = replace_fields(node, annotation=result.node)

        return state, node

    @staticmethod
    def handle_FunctionDef(state, node, ctx, skip_fields, walk_field, **_):

        # Avoid walking the body of the function
        skip_fields()

        # Walk function arguments
        state, new_args = walk_field(state, node.args)
        node = replace_fields(node, args=new_args)

        # Evaluate the return annotation
        result, gen_sym = peval_expression(node.returns, state.gen_sym, ctx.constants)
        new_bindings = state.new_bindings.update(result.temp_bindings)
        node = replace_fields(node, returns=result.node)
        state = state.update(gen_sym=gen_sym, new_bindings=new_bindings)

        return state, node


def peval_function_header(tree, constants):
    """
    Partially evaluate argument annotations and return annotation of a function.
    """
    gen_sym = GenSym.for_tree(tree)
    state, new_tree = _peval_function_header(
        dict(new_bindings=immutabledict(), gen_sym=gen_sym),
        tree,
        ctx=dict(constants=constants))
    return new_tree, state.new_bindings
