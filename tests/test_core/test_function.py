import ast
import copy
import sys
import inspect

from peval.core.function import Function
from peval.tools import unindent

from tests.utils import normalize_source, function_from_source, unparser


global_var = 1


def global_var_writer(x):
    global global_var
    global_var = x


def global_var_reader():
    return global_var


def make_one_var_closure():
    closure_var = [1]

    def closure():
        a = global_var
        some_local_var = 3
        closure_var[0] += 1
        return closure_var[0]

    return closure


def make_two_var_closure():
    closure_var1 = [1]
    closure_var2 = [2]

    def closure():
        some_local_var = closure_var1[0]
        closure_var2[0] += 1
        return closure_var2[0]

    return closure


def dummy_func(a, b, c=4, d=5):
    return a, b, c, d


def dummy_func_arg_groups(a, b, *args, **kwds):
    return a, b, args, kwds


def test_bind_partial_args():
    func = Function.from_object(dummy_func)

    new_func = func.bind_partial(1).eval()
    sig = inspect.signature(new_func)

    assert new_func(2, 3, 4) == (1, 2, 3, 4)
    assert "a" not in sig.parameters
    assert "b" in sig.parameters
    assert "c" in sig.parameters
    assert "d" in sig.parameters


def test_bind_partial_kwds():
    func = Function.from_object(dummy_func)

    new_func = func.bind_partial(1, d=10).eval()
    sig = inspect.signature(new_func)

    assert new_func(2, 3) == (1, 2, 3, 10)
    assert "a" not in sig.parameters
    assert "b" in sig.parameters
    assert "c" in sig.parameters
    assert "d" not in sig.parameters


def test_bind_partial_varargs():
    func = Function.from_object(dummy_func_arg_groups)

    new_func = func.bind_partial(1, 2, 3).eval()
    sig = inspect.signature(new_func)

    assert new_func(d=10) == (1, 2, (3,), {"d": 10})
    assert "a" not in sig.parameters
    assert "b" not in sig.parameters
    assert "args" not in sig.parameters
    assert "kwds" in sig.parameters


def test_bind_partial_varkwds():
    func = Function.from_object(dummy_func_arg_groups)

    new_func = func.bind_partial(1, 2, d=10).eval()
    sig = inspect.signature(new_func)

    assert new_func(3, 4) == (1, 2, (3, 4), {"d": 10})
    assert "a" not in sig.parameters
    assert "b" not in sig.parameters
    assert "args" in sig.parameters
    assert "kwds" not in sig.parameters


def test_globals_contents():
    func = Function.from_object(make_one_var_closure())

    assert "global_var" in func.globals
    assert "closure_var" not in func.globals


def test_closure_contents():
    func = Function.from_object(make_one_var_closure())

    assert "global_var" not in func.closure_vals
    assert "closure_var" in func.closure_vals


def test_copy_globals():
    """
    Checks that a restored function does not refer to the same globals dictionary,
    but a copy of it. Therefore it cannot reassign global values.
    """

    global_var_writer(10)
    assert global_var_reader() == 10
    assert global_var == 10

    reader = Function.from_object(global_var_reader).eval()
    writer = Function.from_object(global_var_writer).eval()

    writer(20)
    assert reader() == 10
    assert global_var == 10


def test_restore_simple_closure():
    closure_ref = make_one_var_closure()
    assert closure_ref() == 2

    closure = Function.from_object(closure_ref).eval()
    assert closure() == 3
    assert closure_ref() == 4


def test_restore_modified_closure():
    def remove_first_line(node):
        assert isinstance(node, ast.FunctionDef)
        node = copy.deepcopy(node)
        node.body = node.body[1:]
        return node

    closure_ref = make_two_var_closure()
    assert closure_ref() == 3

    closure = Function.from_object(closure_ref)
    closure = closure.replace(tree=remove_first_line(closure.tree)).eval()

    assert closure() == 4
    assert closure_ref() == 5


def recursive_outer(x):
    if x > 1:
        return recursive_outer(x - 1)
    else:
        return x


def make_recursive():
    def recursive_inner(x):
        if x > 2:
            return recursive_inner(x - 1)
        else:
            return x

    return recursive_inner


def test_recursive_call():
    # When evaluated inside a fake closure (to detect closure variables),
    # the function name will be included in the list of closure variables
    # (if it is used in the body of the function).
    # So if the function was not a closure to begin with,
    # the corresponding cell will be missing.
    # This tests checks that Function evaluates non-closure functions
    # without a fake closure to prevent that.

    func = Function.from_object(recursive_outer)
    func = func.replace()
    func = func.eval()
    assert func(10) == 1

    func = Function.from_object(make_recursive())
    func = func.replace()
    func = func.eval()
    assert func(10) == 2


def test_construct_from_eval():
    # Test that the function returned from Function.eval()
    # can be used to construct a new Function object.
    func = Function.from_object(dummy_func).eval()
    func2 = Function.from_object(func).eval()
    assert func2(1, 2, c=10) == (1, 2, 10, 5)


# The decorator must be in the global namespace
# otherwise the current implementation of ``from_object()`` will fail
def tag(f):
    vars(f)["_tag"] = True
    return f


def test_reapply_decorators():
    @tag
    def tagged(x):
        return x

    func = Function.from_object(tagged).eval()

    assert "_tag" in vars(func) and vars(func)["_tag"]


def test_detect_future_features():
    # Test that the presence of a future feature is detected

    src = """
        from __future__ import generator_stop
        def f():
            pass
        """

    func = function_from_source(src)
    assert func.future_features.generator_stop

    # Test that the absence of a future feature is detected

    src = """
        def f():
            pass
        """

    func = function_from_source(src)
    if sys.version_info >= (3, 7):
        assert func.future_features.generator_stop
    else:
        assert not func.future_features.generator_stop


def test_preserve_future_feature_presence():
    src = """
        from __future__ import generator_stop
        def f():
            error = lambda: next(i for i in range(3) if i==10)
            try:
                return all(error() for i in range(2))
            except RuntimeError:
                return False
        """

    func = function_from_source(src)
    new_func_obj = func.eval()
    new_func = Function.from_object(new_func_obj)

    assert new_func.future_features.generator_stop
    assert new_func_obj() == False


def test_preserve_future_feature_absence():
    src = """
        def f():
            error = lambda: next(i for i in range(3) if i==10)
            try:
                return all(error() for i in range(2))
            except RuntimeError:
                return False
        """

    func = function_from_source(src)
    new_func_obj = func.eval()
    new_func = Function.from_object(new_func_obj)

    if sys.version_info >= (3, 7):
        assert new_func.future_features.generator_stop
        assert new_func_obj() == False
    else:
        assert not new_func.future_features.generator_stop
        assert new_func_obj() == True


def test_compile_ast():
    function = Function.from_object(sample_fn)
    compiled_fn = function.eval()
    assert compiled_fn(3, -9) == sample_fn(3, -9)
    assert compiled_fn(3, -9, "z", zzz=map) == sample_fn(3, -9, "z", zzz=map)


def test_get_source():
    function = Function.from_object(sample_fn)
    source = normalize_source(function.get_source())

    if unparser() == "astunparse":
        cond = "(foo == 'bar')"
        ret = "(x + y)"
    else:
        cond = "foo == 'bar'"
        ret = "x + y"

    expected_source = unindent(
        f"""
        def sample_fn(x, y, foo='bar', **kw):
            if {cond}:
                return {ret}
            else:
                return kw['zzz']
        """
    )

    assert source == expected_source


def sample_fn(x, y, foo="bar", **kw):
    if foo == "bar":
        return x + y
    else:
        return kw["zzz"]
