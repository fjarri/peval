from collections import defaultdict
import typing

from peval.core.scope import analyze_scope
from ast import FunctionDef
from peval.tools.immutable import immutableset


class GenSym(object):

    def __init__(self, taken_names: typing.Optional[immutableset]=None, counters: typing.Optional[typing.DefaultDict[str, int]]=None) -> None:
        self._taken_names = taken_names if taken_names is not None else set()

        # Keeping per-tag counters affects performance,
        # but the creation of new names happens quite rarely,
        # so it is not noticeable.
        # On the other hand, it makes it easier to compare resulting code with reference code,
        # since in Py3.4 and later we do not need to mangle True/False/None any more,
        # so the joint counter would produce different variable names.
        if counters is None:
            self._counters = defaultdict(lambda: 1)
        else:
            self._counters = counters.copy()

    @classmethod
    def for_tree(cls, tree: typing.Optional[FunctionDef]=None) -> "GenSym":
        if tree is not None:
            scope = analyze_scope(tree)
            taken_names = scope.locals | scope.globals
        else:
            taken_names = None
        return cls(taken_names=taken_names)

    def __call__(self, tag: str='sym') -> typing.Tuple[str, "GenSym"]:
        counter = self._counters[tag]
        while True:
            name = '__peval_' + tag + '_' + str(counter)
            counter += 1
            if name not in self._taken_names:
                break
        self._counters[tag] = counter

        return name, GenSym(taken_names=self._taken_names, counters=self._counters)
