import ast
from functools import reduce

from peval.tools import replace_fields, ast_transformer
from peval.core.gensym import GenSym
from peval.core.cfg import build_cfg
from peval.core.expression import peval_expression


class Value:

    def __init__(self, value=None, undefined=False):
        if undefined:
            self.defined = False
            self.value = None
        else:
            self.defined = True
            self.value = value

    def __str__(self):
        if not self.defined:
            return "<undefined>"
        else:
            return "<" + str(self.value) + ">"

    def __eq__(self, other):
        return self.defined == other.defined and self.value == other.value

    def __ne__(self, other):
        return self.defined != other.defined or self.value != other.value

    def __repr__(self):
        if not self.defined:
            return "Value(undefined=True)"
        else:
            return "Value(value={value})".format(value=repr(self.value))


def meet_values(val1, val2):
    if not val1.defined or not val2.defined:
        return Value(undefined=True)

    v1 = val1.value
    v2 = val2.value

    if v1 is v2:
        return Value(value=v1)

    eq = False
    try:
        eq = (v1 == v2)
    except Exception:
        pass

    if eq:
        return Value(value=v1)
    else:
        return Value(undefined=True)


class Environment:

    def __init__(self, values=None):
        self.values = values if values is not None else {}

    @classmethod
    def from_dict(cls, values):
        return cls(values=dict((name, Value(value=value)) for name, value in values.items()))

    def known_values(self):
        return dict((name, value.value) for name, value in self.values.items() if value.defined)

    def __eq__(self, other):
        return self.values == other.values

    def __ne__(self, other):
        return self.values != other.values

    def __repr__(self):
        return "Environment(values={values})".format(values=self.values)


def meet_envs(env1, env2):

    lhs = env1.values
    rhs = env2.values
    lhs_keys = set(lhs.keys())
    rhs_keys = set(rhs.keys())
    result = {}

    for var in lhs_keys - rhs_keys:
        result[var] = lhs[var]

    for var in rhs_keys - lhs_keys:
        result[var] = rhs[var]

    for var in lhs_keys & rhs_keys:
        result[var] = meet_values(lhs[var], rhs[var])

    return Environment(values=result)


def my_reduce(func, seq):
    if len(seq) == 1:
        return seq[0]
    else:
        return reduce(func, seq[1:], seq[0])


class CachedExpression:

    def __init__(self, path, node):
        self.node = node
        self.path = path


def forward_transfer(gen_sym, in_env, statement):

    if isinstance(statement, ast.Assign):
        target = statement.targets[0].id
        result, gen_sym = peval_expression(statement.value, gen_sym, in_env.known_values())

        new_values = dict(in_env.values)

        if result.fully_evaluated:
            new_value = Value(value=result.value)
        else:
            new_value = Value(undefined=True)
        new_values[target] = new_value

        out_env = Environment(values=new_values)
        new_exprs = [CachedExpression(path=['value'], node=result.node)]

        return gen_sym, out_env, new_exprs, result.temp_bindings

    elif isinstance(statement, (ast.Expr, ast.Return)):
        result, gen_sym = peval_expression(statement.value, gen_sym, in_env.known_values())

        new_values = dict(in_env.values)

        new_exprs = [CachedExpression(path=['value'], node=result.node)]
        out_env = Environment(values=new_values)

        return gen_sym, out_env, new_exprs, result.temp_bindings

    elif isinstance(statement, ast.If):
        result, gen_sym = peval_expression(statement.test, gen_sym, in_env.known_values())

        new_values = dict(in_env.values)

        out_env = Environment(values=new_values)

        new_exprs = [CachedExpression(path=['test'], node=result.node)]

        return gen_sym, out_env, new_exprs, result.temp_bindings

    else:
        return gen_sym, in_env, [], {}


class State:

    def __init__(self, out_env, exprs, temp_bindings):
        self.out_env = out_env
        self.exprs = exprs
        self.temp_bindings = temp_bindings


def get_sorted_nodes(graph, enter):
    sorted_nodes = []
    todo_list = [enter]
    visited = set()

    while len(todo_list) > 0:
        src_id = todo_list.pop()
        if src_id in visited:
            continue
        sorted_nodes.append(src_id)
        visited.add(src_id)

        for dest_id in sorted(graph.children_of(src_id)):
            todo_list.append(dest_id)

    return sorted_nodes


def maximal_fixed_point(gen_sym, graph, enter, bindings):

    states = dict(
        (node_id, State(Environment.from_dict(bindings), [], {}))
        for node_id in graph.nodes)
    enter_env = Environment.from_dict(bindings)

    # First make a pass over each basic block
    # The todo list is sorted to make the names of the final bindings deterministic
    todo_forward = get_sorted_nodes(graph, enter)
    todo_forward_set = set(todo_forward)

    while len(todo_forward) > 0:
        node_id = todo_forward.pop(0)
        todo_forward_set.remove(node_id)
        state = states[node_id]

        # compute the environment at the entry of this BB
        if node_id == enter:
            new_in_env = enter_env
        else:
            parent_envs = [states[parent_id].out_env for parent_id in graph.parents_of(node_id)]
            new_in_env = my_reduce(meet_envs, parent_envs)

        # propagate information for this basic block
        gen_sym, new_out_env, new_exprs, temp_bindings = \
            forward_transfer(gen_sym, new_in_env, graph.nodes[node_id].ast_node)

        states[node_id].exprs = new_exprs
        states[node_id].temp_bindings = temp_bindings

        if new_out_env != states[node_id].out_env:
            states[node_id] = State(new_out_env, new_exprs, temp_bindings)
            for dest_id in sorted(graph.children_of(node_id)):
                if dest_id not in todo_forward_set:
                    todo_forward_set.add(dest_id)
                    todo_forward.append(dest_id)

    # Converged
    new_exprs = {}
    temp_bindings = {}
    for node_id, state in states.items():
        new_exprs[node_id] = state.exprs
        temp_bindings.update(state.temp_bindings)

    return new_exprs, temp_bindings


def replace_exprs(tree, new_exprs):
    return _replace_exprs(tree, ctx=dict(new_exprs=new_exprs))


def replace_by_path(obj, path, new_value):

    ptr = path[0]

    if len(path) > 1:
        if isinstance(ptr, str):
            sub_obj = getattr(obj, ptr)
        elif isinstance(ptr, int):
            sub_obj = obj[ptr]
        new_value = replace_by_path(sub_obj, path[1:], new_value)

    if isinstance(ptr, str):
        return replace_fields(obj, **{ptr: new_value})
    elif isinstance(ptr, int):
        return obj[:ptr] + [new_value] + obj[ptr+1:]


@ast_transformer
def _replace_exprs(node, ctx, walk_field, **_):
    if id(node) in ctx.new_exprs:
        exprs = ctx.new_exprs[id(node)]
        visited_fields = set()
        for expr in exprs:
            visited_fields.add(expr.path[0])
            node = replace_by_path(node, expr.path, expr.node)

        for attr, value in ast.iter_fields(node):
            if attr not in visited_fields:
                setattr(node, attr, walk_field(value))
        return node
    else:
        return node


def fold(tree, constants):
    statements = tree.body
    cfg = build_cfg(statements)
    gen_sym = GenSym.for_tree(tree)
    new_nodes, temp_bindings = maximal_fixed_point(gen_sym, cfg.graph, cfg.enter, constants)
    constants = dict(constants)
    constants.update(temp_bindings)
    new_tree = replace_exprs(tree, new_nodes)
    return new_tree, constants
