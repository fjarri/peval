import ast
import operator
import typing

from peval.tools import Dispatcher, immutableadict, ast_equal, replace_fields
from peval.core.gensym import GenSym
from peval.core.reify import KnownValue, is_known_value, reify
from peval.wisdom import is_pure, get_signature
from peval.core.callable import inspect_callable
from peval.typing import ConstsDictT
from peval.tools import immutabledict, fold_and, map_accum
from peval.tags import pure
import peval.tools.immutable


UNARY_OPS = {
    ast.UAdd: KnownValue(operator.pos),
    ast.USub: KnownValue(operator.neg),
    ast.Not: KnownValue(operator.not_),
    ast.Invert: KnownValue(operator.invert),
}

BIN_OPS = {
    ast.Add: KnownValue(operator.add),
    ast.Sub: KnownValue(operator.sub),
    ast.Mult: KnownValue(operator.mul),
    ast.Div: KnownValue(operator.truediv),
    ast.FloorDiv: KnownValue(operator.floordiv),
    ast.Mod: KnownValue(operator.mod),
    ast.Pow: KnownValue(operator.pow),
    ast.LShift: KnownValue(operator.lshift),
    ast.RShift: KnownValue(operator.rshift),
    ast.BitOr: KnownValue(operator.or_),
    ast.BitXor: KnownValue(operator.xor),
    ast.BitAnd: KnownValue(operator.and_),
}

# Wrapping ``contains``, because its parameters
# do not follow the pattern (left operand, right operand).


@pure
def in_(x, y):
    return operator.contains(y, x)


@pure
def not_in(x, y):
    return not operator.contains(y, x)


COMPARE_OPS = {
    ast.Eq: KnownValue(operator.eq),
    ast.NotEq: KnownValue(operator.ne),
    ast.Lt: KnownValue(operator.lt),
    ast.LtE: KnownValue(operator.le),
    ast.Gt: KnownValue(operator.gt),
    ast.GtE: KnownValue(operator.ge),
    ast.Is: KnownValue(operator.is_),
    ast.IsNot: KnownValue(operator.is_not),
    ast.In: KnownValue(in_),
    ast.NotIn: KnownValue(not_in),
}


def _reify_func(acc, value, create_binding):
    if is_known_value(value):
        # For ``reify()`` we do not need to pass through
        # the whole state, only ``gen_sym``.
        gen_sym, bindings = acc
        node, gen_sym, binding = reify(value, gen_sym, create_binding=create_binding)
        return (gen_sym, bindings.update(binding)), node
    else:
        # Should be an AST node
        return acc, value


def map_reify(state: immutableadict, container, create_binding: bool = False):
    acc = (state.gen_sym, immutabledict())
    acc, new_container = map_accum(_reify_func, acc, container, create_binding)
    gen_sym, bindings = acc

    new_state = state.update(gen_sym=gen_sym, temp_bindings=state.temp_bindings.update(bindings))

    return new_state, new_container


def map_peval_expression(state: immutableadict, container, ctx: immutableadict):
    return map_accum(_peval_expression, state, container, ctx)


def map_get_value(container):
    _, new_container = map_accum(lambda acc, kvalue: (acc, kvalue.value), None, container)
    return new_container


def all_known_values(container):
    return fold_and(is_known_value, container)


def all_known_values_or_none(container) -> bool:
    return fold_and(lambda val: (val is None or is_known_value(val)), container)


def try_call(obj, args=(), kwds={}):
    # The only entry point for function calls.
    callable_ = inspect_callable(obj)

    if callable_.self_obj is not None:
        args = (callable_.self_obj,) + args
    obj = callable_.func_obj

    if not is_pure(obj):
        return False, None

    try:
        sig = get_signature(obj)
    except ValueError:
        return False, None

    try:
        sig.bind(*args, **kwds)
    except TypeError:
        # binding failed
        return False, None

    try:
        value = obj(*args, **kwds)
    except Exception:
        return False, None

    return True, value


def try_get_attribute(obj, name):
    return try_call(getattr, args=(obj, name))


def try_call_method(obj, name, args=(), kwds={}):
    success, attr = try_get_attribute(obj, name)
    if not success:
        return False, None
    return try_call(attr, args=args, kwds=kwds)


def peval_call(state, ctx, func, args=[], keywords=[]):

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

    return state, ast.Call(**nodes)


def try_eval_call(function, args=[], keywords=[]):

    args = args
    kwds = dict(keywords)
    return try_call(function, args=args, kwds=kwds)


def peval_boolop(state: immutableadict, ctx: immutableadict, op, values):
    assert type(op) in (ast.And, ast.Or)

    new_values = []
    for value in values:
        state, new_value = _peval_expression(state, value, ctx)

        # Short circuit
        if is_known_value(new_value):
            success, bool_value = try_call(bool, args=(new_value.value,))
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


def peval_binop(state: immutableadict, ctx: immutableadict, op: ast.operator, left, right):
    func = BIN_OPS[type(op)]
    state, result = peval_call(state, ctx, func, args=[left, right])
    if not is_known_value(result):
        state = state.update(temp_bindings=state.temp_bindings.del_(result.func.id))
        result = ast.BinOp(op=op, left=result.args[0], right=result.args[1])
    return state, result


def peval_single_compare(state: immutableadict, ctx: immutableadict, op, left, right):

    func = COMPARE_OPS[type(op)]

    state, result = peval_call(state, ctx, func, args=[left, right])
    if not is_known_value(result):
        state = state.update(temp_bindings=state.temp_bindings.del_(result.func.id))
        result = ast.Compare(left=result.args[0], ops=[op], comparators=[result.args[1]])
    return state, result


def peval_compare(state: immutableadict, ctx: immutableadict, node: ast.Compare):

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

    if is_known_value(result):
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
    elt_ctx = ctx.update(bindings=elt_bindings)

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
        if is_known_value(joint_ifs_result):
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
    masked_ctx = ctx.set("bindings", masked_bindings)

    state, ifs_result = _peval_comprehension_ifs(state, generator.ifs, masked_ctx)

    if is_known_value(ifs_result):
        success, bool_value = try_call(bool, args=(ifs_result.value,))
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
        success, it = try_call(iter, args=(seq,))
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
    masked_ctx = ctx.set("bindings", masked_bindings)

    state, ifs_result = _peval_comprehension_ifs(state, generator.ifs, masked_ctx)

    if is_known_value(iter_result):
        iterable = iter_result.value
        iterator_evaluated, iterator = try_call(iter, args=(iterable,))
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
        iter_ctx = ctx.set("bindings", iter_bindings)

        state, ifs_value = _peval_expression(state, ifs_result, iter_ctx)
        if not is_known_value(ifs_value):
            raise CannotEvaluateComprehension

        success, bool_value = try_call(bool, args=(ifs_value.value,))
        if not success:
            raise CannotEvaluateComprehension
        if success and not bool_value:
            continue

        if len(next_generators) == 0:
            state, elt_result = _peval_expression(state, elt, iter_ctx)
            if not is_known_value(elt_result):
                raise CannotEvaluateComprehension
            accum.add_elem(elt_result.value)
        else:
            state, part = _peval_comprehension(state, accum_cls, elt, next_generators, iter_ctx)
            accum.add_part(part)

    return state, accum.get_accum()


@Dispatcher
class _peval_expression_dispatcher:
    @staticmethod
    def handle(state: peval.tools.immutable.immutabledict, node: ast.AST, _: immutableadict):
        # Pass through in case of type(node) == KnownValue
        return state, node

    @staticmethod
    def handle_Name(
        state: peval.tools.immutable.immutabledict, node: ast.Name, ctx: immutableadict
    ):
        name = node.id
        if name in ctx.bindings:
            return state, KnownValue(ctx.bindings[name], preferred_name=name)
        else:
            return state, node

    @staticmethod
    def handle_Num(state: peval.tools.immutable.immutabledict, node: ast.Num, _: immutableadict):
        return state, KnownValue(node.n)

    @staticmethod
    def handle_Str(state: peval.tools.immutable.immutabledict, node: ast.Str, _: immutableadict):
        return state, KnownValue(node.s)

    @staticmethod
    def handle_Bytes(
        state: peval.tools.immutable.immutabledict, node: ast.Bytes, _: immutableadict
    ):
        return state, KnownValue(node.s)

    @staticmethod
    def handle_NameConstant(
        state: peval.tools.immutable.immutabledict,
        node: ast.NameConstant,
        _: immutableadict,
    ):
        return state, KnownValue(node.value)

    @staticmethod
    def handle_Constant(
        state: peval.tools.immutable.immutabledict,
        node: ast.Constant,
        _: immutableadict,
    ):
        return state, KnownValue(node.value)

    @staticmethod
    def handle_BoolOp(
        state: peval.tools.immutable.immutabledict,
        node: ast.BoolOp,
        ctx: immutableadict,
    ):
        return peval_boolop(state, ctx, node.op, node.values)

    @staticmethod
    def handle_BinOp(
        state: peval.tools.immutable.immutabledict, node: ast.BinOp, ctx: immutableadict
    ):
        return peval_binop(state, ctx, node.op, node.left, node.right)

    @staticmethod
    def handle_UnaryOp(
        state: peval.tools.immutable.immutabledict,
        node: ast.UnaryOp,
        ctx: immutableadict,
    ):
        state, result = peval_call(state, ctx, UNARY_OPS[type(node.op)], args=[node.operand])
        if not is_known_value(result):
            state = state.update(temp_bindings=state.temp_bindings.del_(result.func.id))
            result = ast.UnaryOp(op=node.op, operand=result.args[0])
        return state, result

    @staticmethod
    def handle_Lambda(
        state: peval.tools.immutable.immutabledict,
        node: ast.Lambda,
        ctx: immutableadict,
    ):
        raise NotImplementedError

    @staticmethod
    def handle_IfExp(
        state: peval.tools.immutable.immutabledict, node: ast.IfExp, ctx: immutableadict
    ):
        state, test_value = _peval_expression(state, node.test, ctx)
        if is_known_value(test_value):
            success, bool_value = try_call(bool, args=(test_value.value,))
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
    def handle_Dict(
        state: peval.tools.immutable.immutabledict, node: ast.Dict, ctx: immutableadict
    ):

        state, pairs = map_peval_expression(state, zip(node.keys, node.values), ctx)
        can_eval = all_known_values(pairs)

        if can_eval:
            new_dict = dict((key.value, value.value) for key, value in pairs)
            return state, KnownValue(value=new_dict)
        else:
            state, keys_values = map_reify(state, zip(*pairs))
            new_node = replace_fields(node, keys=list(keys_values[0]), values=list(keys_values[1]))
            return state, new_node

    @staticmethod
    def handle_List(
        state: peval.tools.immutable.immutabledict, node: ast.List, ctx: immutableadict
    ):

        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_list = [elt.value for elt in elts]
            return state, KnownValue(value=new_list)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_Tuple(
        state: peval.tools.immutable.immutabledict, node: ast.Tuple, ctx: immutableadict
    ):

        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_list = tuple(elt.value for elt in elts)
            return state, KnownValue(value=new_list)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_Set(state: peval.tools.immutable.immutabledict, node: ast.Set, ctx: immutableadict):

        state, elts = map_peval_expression(state, node.elts, ctx)
        can_eval = all_known_values(elts)

        if can_eval:
            new_set = set(elt.value for elt in elts)
            return state, KnownValue(value=new_set)
        else:
            state, new_elts = map_reify(state, elts)
            return state, replace_fields(node, elts=new_elts)

    @staticmethod
    def handle_ListComp(
        state: peval.tools.immutable.immutabledict,
        node: ast.ListComp,
        ctx: immutableadict,
    ):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_SetComp(
        state: peval.tools.immutable.immutabledict,
        node: ast.SetComp,
        ctx: immutableadict,
    ):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_DictComp(
        state: peval.tools.immutable.immutabledict,
        node: ast.DictComp,
        ctx: immutableadict,
    ):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_GeneratorExp(
        state: peval.tools.immutable.immutabledict,
        node: ast.GeneratorExp,
        ctx: immutableadict,
    ):
        return peval_comprehension(state, node, ctx)

    @staticmethod
    def handle_Yield(
        state: peval.tools.immutable.immutabledict, node: ast.Yield, ctx: immutableadict
    ):
        state, result = _peval_expression(state, node.value, ctx)

        # We cannot evaluate a yield expression,
        # so just wrap whatever we've got in a node and return.
        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_YieldFrom(
        state: peval.tools.immutable.immutabledict,
        node: ast.YieldFrom,
        ctx: immutableadict,
    ):
        state, result = _peval_expression(state, node.value, ctx)

        # We cannot evaluate a yield expression,
        # so just wrap whatever we've got in a node and return.
        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_Compare(
        state: peval.tools.immutable.immutabledict,
        node: ast.Compare,
        ctx: immutableadict,
    ):
        return peval_compare(state, ctx, node)

    @staticmethod
    def handle_Call(
        state: peval.tools.immutable.immutabledict, node: ast.Call, ctx: immutableadict
    ):
        return peval_call(state, ctx, node.func, args=node.args, keywords=node.keywords)

    @staticmethod
    def handle_Attribute(
        state: peval.tools.immutable.immutabledict,
        node: ast.Attribute,
        ctx: immutableadict,
    ):
        state, result = _peval_expression(state, node.value, ctx)
        if is_known_value(result):
            success, attr = try_get_attribute(result.value, node.attr)
            if success:
                return state, KnownValue(value=attr)

        state, new_value = map_reify(state, result)
        return state, replace_fields(node, value=new_value)

    @staticmethod
    def handle_Subscript(
        state: peval.tools.immutable.immutabledict,
        node: ast.Subscript,
        ctx: immutableadict,
    ):
        state, value_result = _peval_expression(state, node.value, ctx)
        state, slice_result = _peval_expression(state, node.slice, ctx)
        if is_known_value(value_result) and is_known_value(slice_result):
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
    def handle_Index(
        state: peval.tools.immutable.immutabledict, node: ast.Index, ctx: immutableadict
    ):
        state, result = _peval_expression(state, node.value, ctx)
        if is_known_value(result):
            return state, KnownValue(value=result.value)
        else:
            return state, result

    @staticmethod
    def handle_Slice(
        state: peval.tools.immutable.immutabledict, node: ast.Slice, ctx: immutableadict
    ):
        state, results = map_peval_expression(state, (node.lower, node.upper, node.step), ctx)
        # how do we handle None values in nodes? Technically, they are known values
        if all_known_values_or_none(results):
            lower, upper, step = [result if result is None else result.value for result in results]
            return state, KnownValue(value=slice(lower, upper, step))
        state, new_nodes = map_reify(state, results)
        new_node = replace_fields(node, lower=new_nodes[0], upper=new_nodes[1], step=new_nodes[2])
        return state, new_node

    @staticmethod
    def handle_ExtSlice(
        state: peval.tools.immutable.immutabledict,
        node: ast.ExtSlice,
        ctx: immutableadict,
    ):
        state, results = map_peval_expression(state, node.dims, ctx)
        if all_known_values(results):
            return state, KnownValue(value=tuple(result.value for result in results))
        state, new_nodes = map_reify(state, results)
        return state, replace_fields(node, dims=new_nodes)


class EvaluationResult:
    def __init__(
        self, fully_evaluated: bool, node, temp_bindings: immutableadict, value=None
    ) -> None:
        self.fully_evaluated = fully_evaluated
        if fully_evaluated:
            self.value = value
        self.temp_bindings = temp_bindings
        self.node = node


def _peval_expression(state: immutableadict, node, ctx: immutableadict):
    return _peval_expression_dispatcher(node, state, node, ctx)


def peval_expression(
    node, gen_sym: GenSym, bindings: ConstsDictT, create_binding: bool = False
) -> typing.Tuple[EvaluationResult, GenSym]:

    ctx = immutableadict(bindings=bindings)
    state = immutableadict(gen_sym=gen_sym, temp_bindings=immutableadict())

    state, result = _peval_expression(state, node, ctx)
    if is_known_value(result):
        state, result_node = map_reify(state, result, create_binding)
        eval_result = EvaluationResult(
            fully_evaluated=True,
            value=result.value,
            node=result_node,
            temp_bindings=state.temp_bindings,
        )
    else:
        eval_result = EvaluationResult(
            fully_evaluated=False, node=result, temp_bindings=state.temp_bindings
        )

    return eval_result, state.gen_sym


def try_peval_expression(node, bindings):
    """
    Try to partially evaluate the AST expression ``node`` using the dictionary ``bindings``.
    Returns a pair ``(evaluated, result)``, where ``evaluated`` is a boolean
    and ``result`` is the evaulation result if ``evaluated`` is ``True``,
    and an AST expression otherwise.
    """

    gen_sym = GenSym()
    eval_result, gen_sym = peval_expression(node, gen_sym, bindings)
    if eval_result.fully_evaluated:
        return True, eval_result.value
    else:
        return False, node
