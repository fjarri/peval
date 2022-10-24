import pytest

from peval.tools import ImmutableDict, ImmutableADict


# Immutable dictionary


def test_del():
    d = ImmutableDict(a=1)
    with pytest.raises(KeyError):
        nd = d.without("b")

    d = ImmutableDict(a=1)
    nd = d.without("a")
    assert nd == {}
    assert d == dict(a=1)


def test_with_item():
    d = ImmutableDict(a=1)
    nd = d.with_item("a", 1)
    assert nd is d

    d = ImmutableDict(a=1)
    nd = d.with_item("b", 2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)


def test_with():
    d = ImmutableADict(a=1)
    nd = d.with_(b=2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)

    d = ImmutableADict(a=1)
    nd = d.with_(a=1)
    assert nd is d


def test_dict_repr():
    d = ImmutableDict(a=1)
    nd = eval(repr(d))
    assert type(nd) == type(d)
    assert nd == d


# Immutable attribute dictionary


def test_adict_getattr():
    d = ImmutableADict(a=1)
    assert d.a == 1


def test_adict_repr():
    d = ImmutableADict(a=1)
    nd = eval(repr(d))
    assert type(nd) == type(d)
    assert nd == d
