import ast
import sys
from typing import Any, Optional, Tuple, Dict

from peval.core.gensym import GenSym
from peval.typing import ConstantOrNameNodeT, ConsantOrASTNodeT


NONE_NODE = ast.Constant(value=None, kind=None)
FALSE_NODE = ast.Constant(value=False, kind=None)
TRUE_NODE = ast.Constant(value=True, kind=None)


class KnownValue:
    def __init__(self, value: Any, preferred_name: Optional[str] = None) -> None:
        self.value = value
        self.preferred_name = preferred_name

    def __str__(self):
        return (
            "<"
            + str(self.value)
            + (" (" + self.preferred_name + ")" if self.preferred_name is not None else "")
            + ">"
        )

    def __repr__(self):
        return "KnownValue({value}, preferred_name={name})".format(
            value=repr(self.value), name=repr(self.preferred_name)
        )


ReifyResT = Tuple[ConstantOrNameNodeT, GenSym, Dict[str, ConsantOrASTNodeT]]


def reify(kvalue: KnownValue, gen_sym: GenSym, create_binding: bool = False) -> ReifyResT:
    value = kvalue.value

    # TODO: add a separate reify_constant() method that guarantees not to change the bindings
    if value is True or value is False or value is None:
        return ast.Constant(value=value, kind=None), gen_sym, {}
    elif type(value) == str:
        return ast.Constant(value=value, kind=None), gen_sym, {}
    elif type(value) == bytes:
        return ast.Constant(value=value, kind=None), gen_sym, {}
    elif type(value) in (int, float, complex):
        return ast.Constant(value=value, kind=None), gen_sym, {}
    else:
        if kvalue.preferred_name is None or create_binding:
            name, gen_sym = gen_sym("temp")
        else:
            name = kvalue.preferred_name
        return ast.Name(id=name, ctx=ast.Load()), gen_sym, {name: value}


def reify_unwrapped(value: ConstantOrNameNodeT, gen_sym: GenSym) -> ReifyResT:
    return reify(KnownValue(value), gen_sym)
