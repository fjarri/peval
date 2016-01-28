import pytest

from peval.tools import immutabledict, immutableadict, immutableset


# Immutable dictionary

def test_dict_clear():
    d = immutabledict(a=1)
    nd = d.clear()
    assert nd == {}
    assert d == dict(a=1)


def test_dict_copy():
    d = immutabledict(a=1)
    nd = d.copy()
    assert d is nd
    assert nd == dict(a=1)


def test_dict_pop():
    d = immutabledict(a=1)
    val, nd = d.pop('a')
    assert nd == {}
    assert d == dict(a=1)
    assert val == 1


def test_dict_popitem():
    d = immutabledict(a=1)
    val, nd = d.popitem()
    assert nd == {}
    assert d == dict(a=1)
    assert val == ('a', 1)


def test_dict_setdefault():
    d = immutabledict(a=1)
    val, nd = d.setdefault('a', 10)
    assert d == dict(a=1)
    assert nd is d
    assert val == 1

    d = immutabledict(a=1)
    val, nd = d.setdefault('b', 10)
    assert nd == dict(a=1, b=10)
    assert d == dict(a=1)
    assert val == 10


def test_del_syntax():
    d = immutabledict(a=1)
    with pytest.raises(AttributeError):
        del d['a']


def test_del():
    d = immutabledict(a=1)
    nd = d.del_('b')
    assert nd is d

    d = immutabledict(a=1)
    nd = d.del_('a')
    assert nd == {}
    assert d == dict(a=1)


def test_set_syntax():
    d = immutabledict(a=1)
    with pytest.raises(AttributeError):
        d['b'] = 2


def test_set():
    d = immutabledict(a=1)
    nd = d.set('a', 1)
    assert nd is d

    d = immutabledict(a=1)
    nd = d.set('b', 2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)


def test_update():
    d = immutabledict(a=1)
    nd = d.update()
    assert nd is d

    d = immutabledict(a=1)
    nd = d.update(('b', 2))
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)

    d = immutabledict(a=1)
    nd = d.update(b=2)
    assert nd == dict(a=1, b=2)
    assert d == dict(a=1)

    d = immutabledict(a=1)
    nd = d.update(('b', 2), c=3)
    assert nd == dict(a=1, b=2, c=3)
    assert d == dict(a=1)

    d = immutabledict(a=1)
    nd = d.update(dict(b=2), b=3)
    assert nd == dict(a=1, b=3)
    assert d == dict(a=1)

    d = immutabledict(a=1)
    nd = d.update(a=1)
    assert nd is d


def test_dict_repr():
    d = immutabledict(a=1)
    nd = eval(repr(d))
    assert type(nd) == type(d)
    assert nd == d


# Immutable attribute dictionary

def test_adict_getattr():
    d = immutableadict(a=1)
    assert d.a == 1


def test_adict_setattr():
    d = immutableadict(a=1)
    with pytest.raises(AttributeError):
        d.a = 2


def test_adict_repr():
    d = immutableadict(a=1)
    nd = eval(repr(d))
    assert type(nd) == type(d)
    assert nd == d


# Immutable set

def test_set_add():
    s = immutableset([1])
    ns = s.add(1)
    assert ns is s

    s = immutableset([1])
    ns = s.add(2)
    assert ns == set([1, 2])
    assert s == set([1])


def test_set_clear():
    s = immutableset([1])
    ns = s.clear()
    assert ns == set()
    assert s == set([1])


def test_set_copy():
    s = immutableset([1])
    ns = s.copy()
    assert ns is s


def test_set_discard():

    s = immutableset([1])
    ns = s.discard(3)
    assert ns is s

    s = immutableset([1, 2])
    ns = s.discard(2)
    assert ns == set([1])
    assert s == set([1, 2])


def test_set_remove():
    s = immutableset([1, 2])
    ns = s.remove(2)
    assert ns == set([1])
    assert s == set([1, 2])


def test_set_pop():
    s = immutableset([1])
    elem, ns = s.pop()
    assert ns == set()
    assert s == set([1])
    assert elem == 1


def test_difference():
    s1 = immutableset([1, 2])
    s2 = immutableset([2])
    s3 = immutableset([3])

    ns = s1 - s2
    assert ns == set([1])
    assert type(ns) == immutableset

    ns = s1 - s3
    assert ns is s1

    ns = s1.difference_update(s2)
    assert ns == set([1])
    assert type(ns) == immutableset

    with pytest.raises(AttributeError):
        s1 -= s2


def test_union():
    s1 = immutableset([1, 2])
    s2 = immutableset([2])
    s3 = immutableset([3])

    ns = s1 | s3
    assert ns == set([1, 2, 3])
    assert type(ns) == immutableset

    ns = s1 | s2
    assert ns is s1

    ns = s1.update(s3)
    assert ns == set([1, 2, 3])
    assert type(ns) == immutableset

    with pytest.raises(AttributeError):
        s1 |= s3


def test_intersection():
    s1 = immutableset([1, 2])
    s2 = immutableset([1, 2])
    s3 = immutableset([1])

    ns = s1 & s3
    assert ns == set([1])
    assert type(ns) == immutableset

    ns = s1 & s2
    assert ns is s1

    ns = s1.intersection_update(s3)
    assert ns == set([1])
    assert type(ns) == immutableset

    with pytest.raises(AttributeError):
        s1 &= s3


def test_symmetric_difference():
    s1 = immutableset([1, 2])
    s2 = immutableset([2, 3])
    s3 = immutableset([3])

    ns = s1 ^ s2
    assert ns == set([1, 3])
    assert type(ns) == immutableset

    ns = s1 ^ set()
    assert ns is s1

    ns = s1.symmetric_difference_update(s2)
    assert ns == set([1, 3])
    assert type(ns) == immutableset

    with pytest.raises(AttributeError):
        s1 ^= s2


def test_set_repr():
    s = immutableset([1])
    ns = eval(repr(s))
    assert type(ns) == type(s)
    assert ns == s
