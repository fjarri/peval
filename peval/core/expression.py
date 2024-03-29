import ast
import operator
from typing import Tuple, NamedTuple, Optional, Mapping, Any, Union

from peval.tools import Dispatcher, ImmutableADict, ast_equal, replace_fields
from peval.core.gensym import GenSym
from peval.core.reify import KnownValue, reify
from peval.wisdom import is_pure_callable
from peval.typing import ConstsDictT
from peval.tools import ImmutableDict, fold_and, map_accum
from peval.tags import pure
from peval.tools.immutable import ImmutableADict, ImmutableADict


UNARY_OPS_NAMES = {
    ast.UAdd: "__pos__",
    ast.USub: "__neg__",
    ast.Invert: "__invert__",
}

BIN_OPS_NAMES = {
    ast.Add: ("__add__", "__radd__"),
    ast.Sub: ("__sub__", "__rsub__"),
    ast.Mult: ("__mul__", "__rmul__"),
    ast.Div: ("__truediv__", "__rtruediv__"),
    ast.FloorDiv: ("__floordiv__", "__rfloordiv__"),
    ast.Mod: ("__mod__", "__rmod__"),
    ast.Pow: ("__pow__", "__rpow__"),
    ast.LShift: ("__lshift__", "__rlshift__"),
    ast.RShift: ("__rshift__", "__rrshift__"),
    ast.BitOr: ("__or__", "__ror__"),
    ast.BitXor: ("__xor__", "__rxor__"),
    ast.BitAnd: ("__and__", "__rand__"),
}

COMPARE_OPS_NAMES = {
    ast.Eq: "__eq__",
    ast.NotEq: "__ne__",
    ast.Lt: "__lt__",
    ast.LtE: "__le__",
    ast.Gt: "__gt__",
    ast.GtE: "__ge__",
}


@pure
def not_(val):
    return not val


class State(NamedTuple):
    gen_sym: GenSym
    temp_bindings: ImmutableDict[str, Any]


class Context(NamedTuple):
    bindings: Mapping[str, Any]


def _reify_func(acc, value, create_binding):
    if isinstance(value, KnownValue):
        # For ``reify()`` we do not need to pass through
        # the whole state, only ``gen_sym``.
        gen_sym, bindings = acc
        node, gen_sym, binding = reify(value, gen_sym, create_binding=create_binding)
        return (gen_sym, bindings | binding), node
    else:
        # Should be an AST node
        return acc, value


def map_reify(state: State, container, create_binding: bool = False):
    acc = (state.gen_sym, ImmutableDict())
    acc, new_container = map_accum(_reify_func, acc, container, create_binding)
    gen_sym, bindings = acc

    new_state = State(gen_sym=gen_sym, temp_bindings=state.temp_bindings | bindings)

    return new_state, new_container


def map_peval_expression(state: State, container, ctx: Context):
    return map_accum(_peval_expression, state, container, ctx)


def map_get_value(container):
    _, new_container = map_accum(lambda acc, kvalue: (acc, kvalue.value), None, container)
    return new_container


def all_known_values(container):
    return fold_and(lambda val: isinstance(val, KnownValue), container)


def all_known_values_or_none(container) -> bool:
    return fold_and(lambda val: (val is None or isinstance(val, KnownValue)), container)


def try_call(obj, args=(), kwds={}):
    # The only entry point for function calls.
    if not is_pure_callable(obj):
        return False, None

    try:
        value = obj(*args, **kwds)
    except Exception as exc:
        return False, None

    return True, value


def try_get_attribute(obj, name):
    return try_call(getattr, args=(obj, name))


def try_call_method(obj, name, args=(), kwds={}):
    success, attr = try_get_attribute(obj, name)
    if not success:
        return False, None
    return try_call(attr, args=args, kwds=kwds)


def peval_call(state: State, ctx: Context, func, args=[], keywords=[]):
    assert all(type(arg) != ast.Starred for arg in args)
    assert all(kw.arg is not None for kw in keywords)

    keyword_expressions = [kw.value for kw in keywords]

    state, results = map_peval_expression(
        state, dict(func=func, args=args, keywords=keyword_expressions), ctx
    )

    if all_known_values_or_none(results):
        values = map_get_value(results)
        kwds = {kw.arg: value for kw, value in zip(keywords, values["keywords"])}
        success, value = try_eval_call(values["func"], args=values["args"], keywords=kwds)
        if success:
            return state, KnownValue(value=value)

    state, nodes = map_reify(state, results)

    # restoring the keyword list
    nodes["keywords"] = [
        ast.keyword(arg=kw.arg, value=expr) for kw, expr in zip(keywords, nodes["keywords"])
    ]

    # TODO: why are we returning a new node?
    # Should't we start from passing a `Call` to this function?
    return state, ast.Call(**nodes)


def try_eval_call(function, args=[], keywords=[]):
    args = args
    kwds = dict(keywords)
    return try_call(function, args=args, kwds=kwds)


def peval_boolop(state: State, ctx: Context, op, values):
    assert type(op) in (ast.And, ast.Or)

    new_values = []
    for value in values:
        state, new_value = _peval_expression(state, value, ctx)

        # Short circuit
        if isinstance(new_value, KnownValue):
            success, bool_value = try_call_method(new_value.value, "__bool__")
            # TODO: the following may raise an exception if __bool__() returns something weird.
            short_circuit_applicable = success and (
                (type(op) == ast.And and not bool_value) or (type(op) == ast.Or and bool_value)
            )
            if short_circuit_applicable:
                return state, new_value
            # Just skip it, it won't change the BoolOp result.
        else:
            new_values.append(new_value)

    if len(new_values) == 0:
        return state, KnownValue(type(op) == ast.And)
    elif len(new_values) == 1:
        return state, new_values[0]
    else:
        return state, ast.BoolOp(op=op, values=new_values)


def peval_binop(state: State, ctx: Context, op: ast.operator, left, right):
    state, (peval_left, peval_right) = map_peval_expression(state, [left, right], ctx)
    unevaled_state, [unevaled_left, unevaled_right] = map_reify(state, [peval_left, peval_right])
    unevaled_node = ast.BinOp(op=op, left=unevaled_left, right=unevaled_right)
    if not isinstance(peval_left, KnownValue) or not isinstance(peval_right, KnownValue):
        return unevaled_state, unevaled_node

    attr, rattr = BIN_OPS_NAMES[type(op)]

    lval = peval_left.value
    rval = peval_right.value

    if hasattr(lval, attr):
        success, result = try_call_method(lval, attr, [rval])
        if not success:
            return unevaled_state, unevaled_node
        if result is not NotImplemented:
            return state, KnownValue(result)

    if hasattr(rval, rattr):
        success, result = try_call_method(rval, rattr, [lval])
        if not success:
            return unevaled_state, unevaled_node
        if result is not NotImplemented:
            return state, KnownValue(result)

    return unevaled_state, unevaled_node


def peval_single_compare(state: State, ctx: Context, op, left, right):
    state, (peval_left, peval_right) = map_peval_expression(state, [left, right], ctx)
    unevaled_state, [unevaled_left, unevaled_right] = map_reify(state, [peval_left, peval_right])
    unevaled_node = ast.Compare(ops=[op], left=unevaled_left, comparators=[unevaled_right])
    if not isinstance(peval_left, KnownValue) or not isinstance(peval_right, KnownValue):
        return unevaled_state, unevaled_node

    lval = peval_left.value
    rval = peval_right.value

    if type(op) in COMPARE_OPS_NAMES:
        attr = COMPARE_OPS_NAMES[type(op)]
        success, result = try_call_method(lval, attr, [rval])
        if not success:
            return unevaled_state, unevaled_node

    # These nodes will require a special approach
    # since they are not just desugared to a dunder method call.

    elif type(op) == ast.Is:
        result = lval is rval

    elif type(op) == ast.IsNot:
        result = lval is not rval

    elif type(op) == ast.In:
        # TODO: Python also calls __iter__ and then __getitem__ if __contains__ is not present.
        success, result = try_call_method(rval, "__contains__", [lval])
        if not success:
            return unevaled_state, unevaled_node
        success, result = try_call_method(result, "__bool__")
        if not success:
            return unevaled_state, unevaled_node

    elif type(op) == ast.NotIn:
        success, result = try_call_method(rval, "__contains__", [lval])
        if not success:
            return unevaled_state, unevaled_node
        success, result = try_call_method(result, "__bool__")
        if not success:
            return unevaled_state, unevaled_node
        success, result = try_call(not_, [result])
        if not success:
            return unevaled_state, unevaled_node

    return state, KnownValue(result)


def peval_compare(state: State, ctx: Context, node: ast.Compare):
    if len(node.ops) == 1:
        return peval_single_compare(state, ctx, node.ops[0], node.left, node.comparators[0])

    values = []
    for value_node in [node.left] + node.comparators:
        state, value = _peval_expression(state, value_node, ctx)
        values.append(value)

    pair_values = []
    lefts = [node.left] + node.comparators[:-1]
    rights = node.comparators
    for left, op, right in zip(lefts, node.ops, rights):
        state, pair_value = peval_single_compare(state, ctx, op, left, right)
        pair_values.append(pair_value)

    state, result = peval_boolop(state, ctx, ast.And(), pair_values)

    if isinstance(result, KnownValue):
        return state, result

    if type(result) != ast.BoolOp:
        return state, result

    # Glueing non-evaluated comparisons back together.
    nodes = [result.values[0]]
    for value in result.values[1:]:
        last_node = nodes[-1]
        if (
            type(last_node) == ast.Compare
            and type(value) == ast.Compare
            and ast_equal(last_node.comparators[-1], value.left)
        ):
            nodes[-1] = ast.Compare(
                left=last_node.left,
                ops=last_node.ops + value.ops,
                comparators=last_node.comparators + value.comparators,
            )
        else:
            nodes.append(value)

    if len(nodes) == 1:
        return state, nodes[0]
    else:
        return state, ast.BoolOp(op=ast.And(), values=nodes)


class CannotEvaluateComprehension(Exception):
    pass


class ListAccumulator:
    def __init__(self):
        self.accum = []

    def add_elem(self, elem):
        self.accum.append(elem)

    def add_part(self, part):
        self.accum.extend(part)

    def get_accum(self):
        return self.accum


class SetAccumulator:
    def __init__(self):
        self.accum = set()

    def add_elem(self, elem):
        self.accum.add(elem)

    def add_part(self, part):
        self.accum.update(part)

    def get_accum(self):
        return self.accum


class DictAccumulator:
    def __init__(self):
        self.accum = {}

    def add_elem(self, elem):
        self.accum[elem[0]] = elem[1]

    def add_part(self, part):
        self.accum.update(part)

    def get_accum(self):
        return self.accum


class GeneratorExpAccumulator:
    """
    This is just a list that presents itself as a generator expression
    (to preserve the type after partial evaluation).
    Since we are evaluating each of its elements before returning it anyway,
    it does not really matter.
    """

    def __init__(self):
        self.accum = []

    def add_elem(self, elem):
        self.accum.append(elem)

    def add_part(self, part):
        self.accum.extend(list(part))

    def get_accum(self):
        return (x for x in self.accum)


def peval_comprehension(state, node, ctx):
    accum_cls = {
        ast.ListComp: ListAccumulator,
        ast.GeneratorExp: GeneratorExpAccumulator,
        ast.SetComp: SetAccumulator,
        ast.DictComp: DictAccumulator,
    }

    # variables from generators temporary mask bindings
    target_names = set()
    for generator in node.generators:
        if type(generator.target) == ast.Name:
            target_names.add(generator.target.id)
        else:
            target_names.update([elt.id for elt in generator.target.elts])

    # pre-evaluate the expression
    elt_bindings = dict(ctx.bindings)
    for name in target_names:
        if name in elt_bindings:
            del elt_bindings[name]
    elt_ctx = Context(bindings=elt_bindings)

    if type(node) == ast.DictComp:
        elt = ast.Tuple(elts=[node.key, node.value])
    else:
        elt = node.elt
    state, new_elt = _peval_expression(state, elt, elt_ctx)

    try:
        state, container = _peval_comprehension(
            state, accum_cls[type(node)], new_elt, node.generators, ctx
        )
        evaluated = True
    except CannotEvaluateComprehension:
        evaluated = False

    if evaluated:
        return state, KnownValue(value=container)
    else:
        state, new_elt = map_reify(state, new_elt)
        state, new_generators = _peval_comprehension_generators(state, node.generators, ctx)
        if type(node) == ast.DictComp:
            key, value = new_elt.elts
            return state, replace_fields(node, key=key, value=value, generators=new_generators)
        else:
            return state, replace_fields(node, elt=new_elt, generators=new_generators)


def _peval_comprehension_ifs(state, ifs, ctx):
    if len(ifs) > 0:
        joint_ifs = ast.BoolOp(op=ast.And(), values=ifs)
        state, joint_ifs_result = _peval_expression(state, joint_ifs, ctx)
        if isinstance(joint_ifs_result, KnownValue):
            return state, joint_ifs_result
        else:
            if isinstance(joint_ifs_result, ast.BoolOp):
                return state, joint_ifs_result.values
            else:
                return state, [joint_ifs_result]
    else:
        return state, KnownValue(value=True)


def _get_masked_bindings(target, bindings):
    if type(target) == ast.Name:
        target_names = [target.id]
    else:
        target_names = [elt.id for elt in target.elts]

    new_bindings = dict(bindings)
    for name in target_names:
        if name in new_bindings:
            del new_bindings[name]

    return new_bindings


def _peval_comprehension_generators(state, generators, ctx):
    if len(generators) == 0:
        return state, []

    generator = generators[0]
    next_generators = generators[1:]

    state, iter_result = _peval_expression(state, generator.iter, ctx)

    masked_bindings = _get_masked_bindings(generator.target, ctx.bindings)
    masked_ctx = Context(bindings=masked_bindings)

    state, ifs_result = _peval_comprehension_ifs(state, generator.ifs, masked_ctx)

    if isinstance(ifs_result, KnownValue):
        success, bool_value = try_call_method(ifs_result.value, "__bool__")
        if success and bool_value:
            ifs_result = []

    state, new_generator_kwds = map_reify(
        state, dict(target=generator.target, iter=iter_result, ifs=ifs_result)
    )
    new_generator = ast.comprehension(**new_generator_kwds)

    state, new_generators = _peval_comprehension_generators(state, next_generators, ctx)

    return state, [new_generator] + new_generators


def _try_unpack_sequence(seq, node):
    # node is either a Name, a Tuple of Names, or a List of Names
    if type(node) == ast.Name:
        return True, {node.id: seq}
    elif type(node) in (ast.Tuple, ast.List):
        if not all(type(elt) == ast.Name for elt in node.elts):
            return False, None
        bindings = {}
        success, it = try_call_method(seq, "__iter__")
        if not success:
            return False, None

        if it is seq:
            return False, None

        for elt in node.elts:
            try:
                elem = next(it)
            except StopIteration:
                return False, None
            bindings[elt.id] = elem

        try:
            elem = next(it)
        except StopIteration:
            return True, bindings

        return False, None

    else:
        return False, None


def _peval_comprehension(state, accum_cls, elt, generators, ctx):
    generator = generators[0]
    next_generators = generators[1:]

    state, iter_result = _peval_expression(state, generator.iter, ctx)

    masked_bindings = _get_masked_bindings(generator.target, ctx.bindings)
    masked_ctx = Context(bindings=masked_bindings)

    state, ifs_result = _peval_comprehension_ifs(state, generator.ifs, masked_ctx)

    if isinstance(iter_result, KnownValue):
        iterable = iter_result.value
        iterator_evaluated, iterator = try_call_method(iterable, "__iter__")
    else:
        iterator_evaluated = False

    if not iterator_evaluated or iterator is iterable:
        raise CannotEvaluateComprehension

    accum = accum_cls()

    for targets in iterable:
        unpacked, target_bindings = _try_unpack_sequence(targets, generator.target)
        if not unpacked:
            raise CannotEvaluateComprehension

        iter_bindings = dict(ctx.bindings)
        iter_bindings.update(target_bindings)
        iter_ctx = Context(bindings=iter_bindings)

        state, ifs_value = _peval_expression(state, ifs_result, iter_ctx)
        if not isinstance(ifs_value, KnownValue):
            raise CannotEvaluateComprehension

        success, bool_value = try_call_method(ifs_value.value, "__bool__")
        if not success:
            raise CannotEvaluateComprehension
        if success and not bool_value:
            continue

        if len(next_generators) == 0:
            state, elt_result = _peval_expression(state, elt, iter_ctx)
            if not isinstance(elt_result, KnownValue):
                raise CannotEvaluateComprehension
            accum.add_elem(elt_result.value)
        else:
            state, part = _peval_comprehension(state, accum_cls, elt, next_generators, iter_ctx)
            accum.add_part(part)

    return state, accum.get_accum()


@Dispatcher
class _peval_expression_dispatcher:
    @staticmethod
    def handle(state: State, node: ast.AST, ctx: Context):
        # Pass through in case of type(node) == KnownValue
        return state, node

    @staticmethod
    def handle_Name(state: State, node: ast.Name, ctx: Context):
        name = node.id
        if name in ctx.bindings:
            return state, KnownValue(ctx.bindings[name], preferred_name=name)
        else:
            return state, node

    @staticmethod
    def handle_Num(state: State, node: ast.Num, ctx: Context):
        return state, KnownValue(node.n)

    @staticmethod
    def handle_Str(state: State, node: ast.Str, ctx: Context):
        return state, KnownValue(node.s)

    @staticmethod
    def handle_Bytes(state: State, node: ast.Bytes, ctx: Context):
        return state, KnownValue(node.s)

    @staticmethod
    def handle_NameConstant(state: State, node: ast.NameConstant, ctx: Context):
        return state, KnownValue(node.value)

    @staticmethod
    def handle_Constant(state: State, node: ast.Constant, ctx: Context):
        return state, KnownValue(node.value)

    @staticmethod
    def handle_BoolOp(state: State, node: ast.BoolOp, ctx: Context):
        return peval_boolop(state, ctx, node.op, node.values)

    @staticmethod
    def handle_BinOp(state: State, node: ast.BinOp, ctx: Context):
        return peval_binop(state, ctx, node.op, node.left, node.right)

    @staticmethod
    def handle_UnaryOp(state: State, node: ast.UnaryOp, ctx: Context):
        state, peval_node = _peval_expression(state, node.operand, ctx)
        unevaled_state, unevaled_node = map_reify(state, peval_node)
        unevaled_result = ast.UnaryOp(op=node.op, operand=unevaled_node)
        if not isinstance(peval_node, KnownValue):
            return unevaled_state, unevaled_result

        if type(node.op) == ast.Not:
            # A special case since it cannot be translated to a single method call.
            # So we're reusing the rest of the method as if it was a `bool()` call,
            # with some post-processing afterwards.
            attr = "__bool__"
        else:
            attr = UNARY_OPS_NAMES[type(node.op)]

        success, result = try_call_method(peval_node.value, attr)
        if not success:
            return unevaled_state, unevaled_result

        if type(node.op) == ast.Not:
            success, result = try_call(not_, [result])
            if not success:
                return unevaled_state, unevaled_result

        result = KnownValue(result)

        return state, result

    @staticmethod
    def handle_Lambda(state: State, node: ast.Lambda, ctx: Context):
        raise NotImplementedError

    @staticmethod
    def handle_IfExp(state: State, node: ast.IfExp, ctx: Context):
        state, test_value = _peval_expression(state, node.test, ctx)
        if isinstance(test_value, KnownValue):
            success, bool_value = try_call_method(test_value.value, "__bool__")
            if success:
                taken_node = node.body if bool_value else node.orelse
                return _peval_expression(state, taken_node, ctx)

        state, new_body = _peval_expression(state, node.body, ctx)
        state, new_orelse = _peval_expression(state, node.orelse, ctx)

        state, new_body_node = map_reify(state, new_body)
        state, new_orelse_node = map_reify(state, new_orelse)
        return state, replace_fields(
            node, test=test_value, body=new_body_node, orelse=new_orelse_node
        )

    @staticmethod
    def handle_Dict(state: State, node: ast.Dict, ctx: Context):
        state, pevaled = map_peval_expression(state, [node.keys, node.values], ctx)
        can_eval = all_known_values(pevaled)

        if can_eval:
            new_dict = dict((key.value, value.value) for key, value in zip(*pevaled))
            return state, KnownValue(value=new_dict)
        else:
            state, nodes = map_reify(state, pevaled)
            keys, values = nodes
            new_node = replace_fields(node, keys=keys, values=values)
            return state, new_node

    @staticmethod
    def handle_List(state: State, node: ast.List, ctx: Context):
        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_list = [elt.value for elt in elts]
            return state, KnownValue(value=new_list)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_Tuple(state: State, node: ast.Tuple, ctx: Context):
        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_list = tuple(elt.value for elt in elts)
            return state, KnownValue(value=new_list)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_Set(state: State, node: ast.Set, ctx: Context):
        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_set = set(elt.value for elt in elts)
            return state, KnownValue(value=new_set)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_ListComp(state: State, node: ast.ListComp, ctx: Context):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_SetComp(state: State, node: ast.SetComp, ctx: Context):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_DictComp(state: State, node: ast.DictComp, ctx: Context):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_GeneratorExp(state: State, node: ast.GeneratorExp, ctx: Context):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_Yield(state: State, node: ast.Yield, ctx: Context):
        state, result = _peval_expression(state, node.value, ctx)

        # We cannot evaluate a yield expression,
        # so just wrap whatever we've got in a node and return.
        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_YieldFrom(state: State, node: ast.YieldFrom, ctx: Context):
        state, result = _peval_expression(state, node.value, ctx)

        # We cannot evaluate a yield expression,
        # so just wrap whatever we've got in a node and return.
        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_Compare(state: State, node: ast.Compare, ctx: Context):
        return peval_compare(state, ctx, node)

    @staticmethod
    def handle_Call(state: State, node: ast.Call, ctx: Context):
        return peval_call(state, ctx, node.func, args=node.args, keywords=node.keywords)

    @staticmethod
    def handle_Attribute(state: State, node: ast.Attribute, ctx: Context):
        state, result = _peval_expression(state, node.value, ctx)
        if isinstance(result, KnownValue):
            success, attr = try_get_attribute(result.value, node.attr)
            if success:
                return state, KnownValue(value=attr)

        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_Subscript(state: State, node: ast.Subscript, ctx: Context):
        state, value_result = _peval_expression(state, node.value, ctx)
        state, slice_result = _peval_expression(state, node.slice, ctx)
        if isinstance(value_result, KnownValue) and isinstance(slice_result, KnownValue):
            success, elem = try_call_method(
                value_result.value, "__getitem__", args=(slice_result.value,)
            )
            if success:
                return state, KnownValue(value=elem)

        state, new_value = map_reify(state, value_result)
        state, new_slice = map_reify(state, slice_result)
        if type(new_slice) not in (ast.Index, ast.Slice, ast.ExtSlice):
            new_slice = ast.Index(value=new_slice)
        return state, replace_fields(node, value=new_value, slice=new_slice)

    @staticmethod
    def handle_Index(state: State, node: ast.Index, ctx: Context):
        state, result = _peval_expression(state, node.value, ctx)
        if isinstance(result, KnownValue):
            return state, KnownValue(value=result.value)
        else:
            return state, result

    @staticmethod
    def handle_Slice(state: State, node: ast.Slice, ctx: Context):
        state, results = map_peval_expression(state, (node.lower, node.upper, node.step), ctx)
        # how do we handle None values in nodes? Technically, they are known values
        if all_known_values_or_none(results):
            lower, upper, step = [result if result is None else result.value for result in results]
            return state, KnownValue(value=slice(lower, upper, step))
        state, new_nodes = map_reify(state, results)
        new_node = replace_fields(node, lower=new_nodes[0], upper=new_nodes[1], step=new_nodes[2])
        return state, new_node

    @staticmethod
    def handle_ExtSlice(state: State, node: ast.ExtSlice, ctx: Context):
        state, results = map_peval_expression(state, node.dims, ctx)
        if all_known_values(results):
            return state, KnownValue(value=tuple(result.value for result in results))
        state, new_nodes = map_reify(state, results)
        return state, replace_fields(node, dims=new_nodes)


class EvaluationResult(NamedTuple):
    known_value: Optional[KnownValue]
    node: ast.AST
    temp_bindings: Mapping[str, Any]


def _peval_expression(
    state: State, node: ast.AST, ctx: Context
) -> Tuple[State, Union[KnownValue, ast.AST]]:
    return _peval_expression_dispatcher(node, state, node, ctx)


def peval_expression(
    node: ast.AST, gen_sym: GenSym, bindings: Mapping[str, Any], create_binding: bool = False
) -> Tuple[EvaluationResult, GenSym]:
    ctx = Context(bindings=bindings)
    state = State(gen_sym=gen_sym, temp_bindings=ImmutableADict())

    state, result = _peval_expression(state, node, ctx)
    if isinstance(result, KnownValue):
        known_value = result
        state, result_node = map_reify(state, result, create_binding)
    else:
        known_value = None
        result_node = result

    eval_result = EvaluationResult(
        known_value=known_value,
        node=result_node,
        temp_bindings=state.temp_bindings,
    )

    return eval_result, state.gen_sym


def try_peval_expression(node: ast.AST, bindings: Mapping[str, Any]) -> Tuple[bool, ast.AST]:
    """
    Try to partially evaluate the AST expression ``node`` using the dictionary ``bindings``.
    Returns a pair ``(evaluated, result)``, where ``evaluated`` is a boolean
    and ``result`` is the evaulation result if ``evaluated`` is ``True``,
    and an AST expression otherwise.
    """

    gen_sym = GenSym()
    eval_result, gen_sym = peval_expression(node, gen_sym, bindings)
    if eval_result.known_value is not None:
        return True, eval_result.known_value.value
    else:
        return False, node
