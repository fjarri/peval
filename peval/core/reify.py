import ast
import sys


if sys.version_info[:2] >= (3, 8):
    NONE_NODE = ast.Constant(value=None, kind=None)
    FALSE_NODE = ast.Constant(value=False, kind=None)
    TRUE_NODE = ast.Constant(value=True, kind=None)
else:
    NONE_NODE = ast.NameConstant(value=None)
    FALSE_NODE = ast.NameConstant(value=False)
    TRUE_NODE = ast.NameConstant(value=True)


class KnownValue(object):

    def __init__(self, value, preferred_name=None):
        self.value = value
        self.preferred_name = preferred_name

    def __str__(self):
        return (
            "<" + str(self.value)
            + (" (" + self.preferred_name + ")" if self.preferred_name is not None else "")
            + ">")

    def __repr__(self):
        return "KnownValue({value}, preferred_name={name})".format(
            value=repr(self.value), name=repr(self.preferred_name))


def is_known_value(node_or_kvalue):
    return type(node_or_kvalue) == KnownValue


def reify(kvalue, gen_sym, create_binding=False):

    value = kvalue.value

    if value is True or value is False or value is None:
        if sys.version_info[:2] >= (3, 8):
            return ast.Constant(value=value, kind=None), gen_sym, {}
        else:
            return ast.NameConstant(value=value), gen_sym, {}
    elif type(value) == str:
        if sys.version_info[:2] >= (3, 8):
            return ast.Constant(value=value, kind=None), gen_sym, {}
        else:
            return ast.Str(s=value), gen_sym, {}
    elif type(value) == bytes:
        if sys.version_info[:2] >= (3, 8):
            return ast.Constant(value=value, kind=None), gen_sym, {}
        else:
            return ast.Bytes(s=value), gen_sym, {}
    elif type(value) in (int, float, complex):
        if sys.version_info[:2] >= (3, 8):
            return ast.Constant(value=value, kind=None), gen_sym, {}
        else:
            return ast.Num(n=value), gen_sym, {}
    else:
        if kvalue.preferred_name is None or create_binding:
            name, gen_sym = gen_sym('temp')
        else:
            name = kvalue.preferred_name
        return ast.Name(id=name, ctx=ast.Load()), gen_sym, {name: value}


def reify_unwrapped(value, gen_sym):
    return reify(KnownValue(value), gen_sym)
