import pytest

from peval.tools import ImmutableDict, ImmutableADict


# Immutable dictionary


def test_dict_clear():
    d = ImmutableDict(a=1)
    nd = d.clear()
    assert nd == {}
    assert d == dict(a=1)


def test_dict_copy():
    d = ImmutableDict(a=1)
    nd = d.copy()
    assert d is nd
    assert nd == dict(a=1)


def test_dict_pop():
    d = ImmutableDict(a=1)
    val, nd = d.pop("a")
    assert nd == {}
    assert d == dict(a=1)
    assert val == 1


def test_dict_popitem():
    d = ImmutableDict(a=1)
    val, nd = d.popitem()
    assert nd == {}
    assert d == dict(a=1)
    assert val == ("a", 1)


def test_dict_setdefault():
    d = ImmutableDict(a=1)
    val, nd = d.setdefault("a", 10)
    assert d == dict(a=1)
    assert nd is d
    assert val == 1

    d = ImmutableDict(a=1)
    val, nd = d.setdefault("b", 10)
    assert nd == dict(a=1, b=10)
    assert d == dict(a=1)
    assert val == 10


def test_del_syntax():
    d = ImmutableDict(a=1)
    with pytest.raises(AttributeError):
        del d["a"]


def test_del():
    d = ImmutableDict(a=1)
    nd = d.del_("b")
    assert nd is d

    d = ImmutableDict(a=1)
    nd = d.del_("a")
    assert nd == {}
    assert d == dict(a=1)


def test_set_syntax():
    d = ImmutableDict(a=1)
    with pytest.raises(AttributeError):
        d["b"] = 2


def test_set():
    d = ImmutableDict(a=1)
    nd = d.set("a", 1)
    assert nd is d

    d = ImmutableDict(a=1)
    nd = d.set("b", 2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)


def test_update():
    d = ImmutableDict(a=1)
    nd = d.update()
    assert nd is d

    d = ImmutableDict(a=1)
    nd = d.update(("b", 2))
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)

    d = ImmutableDict(a=1)
    nd = d.update(b=2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)

    d = ImmutableDict(a=1)
    nd = d.update(("b", 2), c=3)
    assert nd == dict(a=1, b=2, c=3)
    assert d == dict(a=1)

    d = ImmutableDict(a=1)
    nd = d.update(dict(b=2), b=3)
    assert nd == dict(a=1, b=3)
    assert d == dict(a=1)

    d = ImmutableDict(a=1)
    nd = d.update(a=1)
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


def test_adict_setattr():
    d = ImmutableADict(a=1)
    with pytest.raises(AttributeError):
        d.a = 2


def test_adict_repr():
    d = ImmutableADict(a=1)
    nd = eval(repr(d))
    assert type(nd) == type(d)
    assert nd == d
