import ast


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


def reify(kvalue, gen_sym):

    value = kvalue.value

    if value is True or value is False or value is None:
        return ast.NameConstant(value=value), gen_sym, {}
    elif type(value) == str:
        return ast.Str(s=value), gen_sym, {}
    elif type(value) == bytes:
        return ast.Bytes(s=value), gen_sym, {}
    elif type(value) in (int, float, complex):
        return ast.Num(n=value), gen_sym, {}
    else:
        if kvalue.preferred_name is None:
            name, gen_sym = gen_sym('temp')
        else:
            name = kvalue.preferred_name
        return ast.Name(id=name, ctx=ast.Load()), gen_sym, {name: value}


def reify_unwrapped(value, gen_sym):
    return reify(KnownValue(value), gen_sym)
