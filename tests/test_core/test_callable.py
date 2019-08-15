import types
import sys

from peval.core.callable import inspect_callable, Callable


def test_builtin_function():
    assert inspect_callable(isinstance) == Callable(isinstance)

def test_builtin_constructor():
    assert inspect_callable(str) == Callable(str, init=True)

def test_builtin_unbound_method():
    assert inspect_callable(str.__getitem__) == Callable(str.__getitem__)

def test_builtin_bound_method():
    assert inspect_callable("a".__getitem__) == Callable(str.__getitem__, self_obj="a")


class mystr1(str):
    pass


class mystr2(str):
    def __getitem__(self, idx):
        return str.__getitem__(self, idx)


def test_builtin_method_in_derived():
    s1 = mystr1("a")
    assert (inspect_callable(s1.__getitem__) == Callable(str.__getitem__, self_obj=s1))

def test_builtin_method_overloaded_in_derived():
    s2 = mystr2("a")
    assert (inspect_callable(s2.__getitem__) == Callable(mystr2.__getitem__, self_obj=s2))


def dummy():
    pass


class OldStyleDummyInit:

    def __init__(self):
        pass


class OldStyleDummy:

    def __call__(self):
        pass

    def method(self):
        pass

    @classmethod
    def classmethod(cls):
        pass

    @staticmethod
    def staticmethod():
        pass


class OldStyleDerivedDummy(OldStyleDummy):
    pass


class NewStyleDummy(object):

    def __call__(self):
        pass

    def method(self):
        pass

    @classmethod
    def classmethod(cls):
        pass

    @staticmethod
    def staticmethod():
        pass


class NewStyleDerivedDummy(NewStyleDummy):
    pass


def pytest_generate_tests(metafunc):
    if 'cls' in metafunc.fixturenames:
        clss = [{'base': NewStyleDummy, 'derived': NewStyleDerivedDummy}]
        ids = ['new style']
        metafunc.parametrize('cls', clss, ids=ids)


def test_function():
    assert inspect_callable(dummy) == Callable(dummy)

def test_constructor(cls):
    assert inspect_callable(cls['base']) == Callable(cls['base'], init=True)

def test_unbound_method(cls):
    assert inspect_callable(cls['base'].method) == Callable(cls['base'].method)

def test_bound_method(cls):
    d = cls['base']()
    assert inspect_callable(d.method) == Callable(cls['base'].method, self_obj=d)

def test_bound_method_in_derived(cls):
    d = cls['derived']()
    assert inspect_callable(d.method) == Callable(cls['base'].method, self_obj=d)

def test_call_method(cls):
    d = cls['base']()
    assert inspect_callable(d) == Callable(cls['base'].__call__, self_obj=d)

def test_static_method(cls):
    d = cls['base']()
    assert inspect_callable(d.staticmethod) == Callable(cls['base'].staticmethod)

def test_class_method(cls):
    d = cls['base']()
    classmethod_func = cls['base'].classmethod.__func__
    assert inspect_callable(d.classmethod) == Callable(classmethod_func, self_obj=cls['base'])

def test_class_method_in_derived(cls):
    d = cls['derived']()
    classmethod_func = cls['base'].classmethod.__func__
    assert inspect_callable(d.classmethod) == Callable(classmethod_func, self_obj=cls['derived'])
