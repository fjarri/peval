import types
import sys

from peval.tags import pure
from peval.wisdom import is_pure_callable


class StrPure(str):
    pass


class StrImpureMethod(str):
    def __getitem__(self, idx):
        return str.__getitem__(self, idx)


class StrPureMethod(str):
    @pure
    def __getitem__(self, idx):
        return str.__getitem__(self, idx)


@pure
def dummy_pure():
    pass


def dummy_impure():
    pass


class DummyPureInit:
    @pure
    def __init__(self):
        pass


class DummyPureCall:
    @pure
    def __call__(self):
        pass


class DummyImpureInit:
    def __init__(self):
        pass


class DummyImpureCall:
    def __call__(self):
        pass


class Dummy:
    @pure
    def pure_method(self):
        pass

    def impure_method(self):
        pass

    @classmethod
    @pure
    def pure_classmethod(cls):
        pass

    @classmethod
    def impure_classmethod(cls):
        pass

    @staticmethod
    @pure
    def pure_staticmethod():
        pass

    @staticmethod
    def impure_staticmethod():
        pass


def test_is_pure():
    # a builtin function
    assert is_pure_callable(isinstance)

    # a builtin type
    assert is_pure_callable(str)

    # an unbound method of a built-in type
    assert is_pure_callable(str.__getitem__)

    # a bound method of a built-in type
    assert is_pure_callable("a".__getitem__)

    # a class derived from a builtin type
    assert is_pure_callable(StrPure)
    assert is_pure_callable(StrPure("a").__getitem__)

    # Overridden methods need to be explicitly marked as pure
    assert is_pure_callable(StrPureMethod("a").__getitem__)
    assert not is_pure_callable(StrImpureMethod("a").__getitem__)

    # A function
    assert is_pure_callable(dummy_pure)
    assert not is_pure_callable(dummy_impure)

    # A class
    assert is_pure_callable(DummyPureInit)
    assert not is_pure_callable(DummyImpureInit)

    # A callable object
    assert is_pure_callable(DummyPureCall())
    assert not is_pure_callable(DummyImpureCall())

    # Various methods
    assert is_pure_callable(Dummy().pure_method)
    assert is_pure_callable(Dummy.pure_method)
    assert is_pure_callable(Dummy().pure_classmethod)
    assert is_pure_callable(Dummy.pure_classmethod)
    assert is_pure_callable(Dummy().pure_staticmethod)
    assert is_pure_callable(Dummy.pure_staticmethod)
    assert not is_pure_callable(Dummy().impure_method)
    assert not is_pure_callable(Dummy.impure_method)
    assert not is_pure_callable(Dummy().impure_classmethod)
    assert not is_pure_callable(Dummy.impure_classmethod)
    assert not is_pure_callable(Dummy().impure_staticmethod)
    assert not is_pure_callable(Dummy.impure_staticmethod)

    # a non-callable
    assert not is_pure_callable("a")
