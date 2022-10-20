import sys
import unittest
from pathlib import Path

thisDir = Path(__file__).parent
sys.path.insert(0, str(thisDir))
sys.path.insert(1, str(thisDir.parent))

from utils import function_from_source

from peval.tags import get_inline_tag, get_pure_tag, inline, pure


class TestStringMethods(unittest.TestCase):
    def test_pure_tag(self):
        @pure
        def func(x):
            return x

        assert get_pure_tag(func)

    def test_inline_tag(self):
        @inline
        def func(x):
            return x

        assert get_inline_tag(func)

    def test_inline_prohibit_nested_definitions(self):
        def func(x):
            return lambda y: x + y

        with self.assertRaises(ValueError):
            func = inline(func)

    def test_inline_prohibit_generator(self):
        def func(x):
            for i in range(x):
                yield i

        with self.assertRaises(ValueError):
            func = inline(func)

    def test_inline_prohibit_async(self):

        func = function_from_source(
            """
            async def func(x):
                return x
            """
        ).eval()

        with self.assertRaises(ValueError):
            func = inline(func)

    def test_inline_prohibit_closure(self):
        @inline
        def no_closure(x):
            return x

        assert get_inline_tag(no_closure)

        a = 1

        def with_closure(x):
            return x + a

        with self.assertRaises(ValueError):
            with_closure = inline(with_closure)


if __name__ == "__main__":
    unittest.main()
