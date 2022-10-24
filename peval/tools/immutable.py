"""
Immutable data structures.

The classes in this module have the prefix 'immutable' to avoid confusion
with the built-in ``frozenset``, which does not have any modification methods,
even pure ones.
"""
from typing import Any


class ImmutableDict(dict):
    """
    An immutable version of ``dict``.

    Mutating syntax (``del d[k]``, ``d[k] = v``) is prohibited,
    pure methods ``del_`` and ``set`` are available instead.
    Mutating methods are overridden to return the new dictionary
    (or a tuple ``(value, new_dict)`` where applicable)
    without mutating the source dictionary.
    If a mutating method does not change the dictionary,
    the source dictionary itself is returned as the new dictionary.
    """

    def clear(self):
        return self.__class__()

    def copy(self):
        return self

    def pop(self, *args):
        new_dict = self.__class__(self)
        value = dict.pop(new_dict, *args)
        return value, new_dict

    def popitem(self):
        new_dict = self.__class__(self)
        value = dict.popitem(new_dict)
        return value, new_dict

    def setdefault(self, *args):
        key = args[0]
        if key not in self:
            new_dict = self.__class__(self)
            value = dict.setdefault(new_dict, *args)
            return value, new_dict
        else:
            return self[key], self

    def __delitem__(self, key):
        raise AttributeError("Item deletion syntax is not available for an immutable dict")

    def del_(self, key: str) -> "ImmutableADict":
        if key in self:
            new_dict = self.__class__(self)
            dict.__delitem__(new_dict, key)
            return new_dict
        else:
            return self

    def __setitem__(self, key, item):
        raise AttributeError("Item assignment syntax is not available for an immutable dict")

    def set(self, key: str, value: Any) -> "ImmutableDict":
        if key in self and self[key] is value:
            return self
        else:
            new_dict = self.__class__(self)
            dict.__setitem__(new_dict, key, value)
            return new_dict

    def update(self, *args, **kwds) -> "ImmutableDict":

        if len(kwds) == 0 and len(args) == 0:
            return self

        if len(args) > 0:
            if isinstance(args[0], dict):
                new_vals = args[0]
            else:
                new_vals = dict(args)
        else:
            new_vals = {}

        new_vals.update(kwds)

        for kwd, value in new_vals.items():
            if self.get(kwd, None) is not value:
                break
        else:
            return self

        new_dict = self.__class__(self)
        dict.update(new_dict, new_vals)
        return new_dict

    def __repr__(self):
        return "ImmutableDict(" + dict.__repr__(self) + ")"


class ImmutableADict(ImmutableDict):
    """
    A subclass of ``ImmutableDict`` with values being accessible as attributes
    (e.g. ``d['a']`` is equivalent to ``d.a``).
    """

    def __getattr__(self, attr: str) -> Any:
        return self[attr]

    def __setattr__(self, attr, value):
        raise AttributeError("Attribute assignment syntax is not available for an immutable dict")

    def __repr__(self):
        return "ImmutableADict(" + dict.__repr__(self) + ")"
