"""
Immutable data structures.

The classes in this module have the prefix 'immutable' to avoid confusion
with the built-in ``frozenset``, which does not have any modification methods,
even pure ones.
"""
from typing import Any, TypeVar, Mapping, Iterator


_Key = TypeVar("_Key")
_Val = TypeVar("_Val")


class ImmutableDict(Mapping[_Key, _Val]):
    """
    An immutable version of ``dict``.

    TODO: switch to `frozendict` when it fixes its typing problems
    (see https://github.com/Marco-Sulla/python-frozendict/issues/39)

    Mutating syntax (``del d[k]``, ``d[k] = v``) is prohibited,
    pure methods ``del_`` and ``set`` are available instead.
    Mutating methods are overridden to return the new dictionary
    (or a tuple ``(value, new_dict)`` where applicable)
    without mutating the source dictionary.
    If a mutating method does not change the dictionary,
    the source dictionary itself is returned as the new dictionary.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._dict = dict(*args, **kwargs)

    def __getitem__(self, key: object) -> _Val:
        return self._dict[key]

    def __contains__(self, key: object) -> bool:
        return key in self._dict

    def __iter__(self) -> Iterator[_Key]:
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __or__(self, other: Mapping[_Key, _Val]) -> "ImmutableDict[_Key, _Val]":
        new = dict(self._dict)
        new.update(other)
        return self.__class__(new)

    def with_item(self, key: _Key, val: _Val) -> "ImmutableDict[_Key, _Val]":
        if key in self._dict and self._dict[key] is val:
            return self
        new = dict(self._dict)
        new[key] = val
        return self.__class__(new)

    def without(self, key: _Key) -> "ImmutableDict[_Key, _Val]":
        new = dict(self._dict)
        del new[key]
        return self.__class__(new)

    def __repr__(self):
        return f"ImmutableDict({repr(self._dict)})"


class ImmutableADict(ImmutableDict[str, _Val]):
    """
    A subclass of ``ImmutableDict`` with values being accessible as attributes
    (e.g. ``d['a']`` is equivalent to ``d.a``).
    """

    def __getattr__(self, attr: str) -> _Val:
        return self._dict[attr]

    def with_(self, **kwds: Mapping[str, _Val]) -> "ImmutableADict[_Val]":
        # TODO: need to think this over again.
        # In some places we check if the dicts were updated or not with `is`,
        # to avoid a lengthy equality check.
        # But e.g. equal strings are not guaranteed to be the same object in Python.
        # Is this fine?
        if all(key in self._dict and self._dict[key] is val for key, val in kwds.items()):
            return self
        new = dict(self._dict)
        new.update(**kwds)
        return self.__class__(new)

    def __repr__(self):
        return f"ImmutableADict({repr(self._dict)})"
