import ast
from collections import namedtuple

from peval.tools import immutableset, ast_inspector


Scope = namedtuple("Scope", "locals locals_used globals")


@ast_inspector
class _analyze_scope:
    @staticmethod
    def handle_arg(state, node: ast.AST, **_):
        return state.update(locals=state.locals.add(node.arg))

    @staticmethod
    def handle_Name(state, node: ast.AST, **_):
        name = node.id
        if type(node.ctx) == ast.Store:
            state = state.update(locals=state.locals.add(name))
            if name in state.globals:
                state = state.update(globals=state.globals.remove(name))
        elif type(node.ctx) == ast.Load:
            if name in state.locals:
                state = state.update(locals_used=state.locals_used.add(name))
            else:
                state = state.update(globals=state.globals.add(name))

        return state

    @staticmethod
    def handle_alias(state, node: ast.AST, **_):
        name = node.asname if node.asname else node.name
        if "." in name:
            name = name.split(".", 1)[0]
        return state.update(locals=state.locals.add(name))


def analyze_scope(node: ast.AST) -> Scope:
    state = _analyze_scope(
        dict(locals=immutableset(), locals_used=immutableset(), globals=immutableset()),
        node,
    )
    return Scope(locals=state.locals, locals_used=state.locals_used, globals=state.globals)
