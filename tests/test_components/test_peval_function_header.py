from peval.tags import pure
from peval.components import peval_function_header

from tests.utils import check_component


class Dummy:
    tp1 = int


@pure
def get_type():
    return str


def dummy(x: int, y: Dummy.tp1='aaa') -> get_type():
    pass


def test_peval_function_header():
    check_component(
        peval_function_header, dummy,
        expected_source="""
            def dummy(x: int, y:__peval_temp_1='aaa') -> __peval_temp_2:
                pass
            """,
        expected_new_bindings=dict(
            __peval_temp_1=Dummy.tp1,
            __peval_temp_2=get_type()))
