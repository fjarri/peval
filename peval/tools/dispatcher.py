import ast
import types
from typing import Tuple, Callable, Optional, Generic, TypeVar, Any, Dict, Type, cast
from typing_extensions import ParamSpec, Concatenate

from .immutable import ImmutableDict

_Params = ParamSpec("_Params")
_Return = TypeVar("_Return")


class Dispatcher(Generic[_Params, _Return]):
    """
    A dispatcher that maps a call to a group of functions
    based on the type of the first argument
    (hardcoded to be an AST node at the moment).

    ``handler_obj`` can be either a function with the signature::

        def handler(*args, **kwds)

    or a class with the static methods::

        @staticmethod
        def handle_<tp>(*args, **kwds)

    where ``<tp>`` is the name of the type that this function will handle
    (e.g., ``handle_FunctionDef`` for ``ast.FunctionDef``).
    The class can also define the default handler::

        @staticmethod
        def handle(*args, **kwds)

    If it is not defined, the ``default_handler`` value will be used
    (which must be a function with the same signature as above).
    If neither ``handle`` exists or ``default_handler`` is provided,
    a ``ValueError`` is thrown.
    """

    def __init__(
        self, handler_obj: Any, default_handler: Optional[Callable[_Params, _Return]] = None
    ):
        self._handlers: Dict[Type[ast.AST], Callable[_Params, _Return]] = {}
        if isinstance(handler_obj, types.FunctionType):
            self._default_handler = cast(Callable[_Params, _Return], handler_obj)
        else:
            handler_prefix = "handle"
            if hasattr(handler_obj, handler_prefix):
                self._default_handler = cast(
                    Callable[_Params, _Return], getattr(handler_obj, handler_prefix)
                )
            elif default_handler is not None:
                self._default_handler = default_handler
            else:
                raise ValueError("Default handler was not provided")

            attr_prefix = handler_prefix + "_"
            for attr in vars(handler_obj):
                if attr.startswith(attr_prefix):
                    typename = attr[len(attr_prefix) :]
                    if hasattr(ast, typename):
                        self._handlers[getattr(ast, typename)] = getattr(handler_obj, attr)

    def __call__(
        self, dispatch_node: ast.AST, *args: _Params.args, **kwargs: _Params.kwargs
    ) -> _Return:
        handler = self._handlers.get(type(dispatch_node), self._default_handler)
        return handler(*args, **kwargs)
