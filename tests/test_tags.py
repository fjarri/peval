import pytest

from peval.tags import pure, get_pure_tag, inline, get_inline_tag

from tests.utils import function_from_source


def test_pure_tag():
    @pure
    def func(x):
        return x

    assert get_pure_tag(func)


def test_inline_tag():
    @inline
    def func(x):
        return x

    assert get_inline_tag(func)


def test_inline_prohibit_nested_definitions():
    def func(x):
        return lambda y: x + y

    with pytest.raises(ValueError):
        func = inline(func)


def test_inline_prohibit_generator():
    def func(x):
        for i in range(x):
            yield i

    with pytest.raises(ValueError):
        func = inline(func)


def test_inline_prohibit_async():
    func = function_from_source(
        """
        async def func(x):
            return x
        """
    ).eval()

    with pytest.raises(ValueError):
        func = inline(func)


def test_inline_prohibit_closure():
    @inline
    def no_closure(x):
        return x

    assert get_inline_tag(no_closure)

    a = 1

    def with_closure(x):
        return x + a

    with pytest.raises(ValueError):
        with_closure = inline(with_closure)
