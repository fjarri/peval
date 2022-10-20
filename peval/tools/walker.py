"""
A replacement for ``ast.Visitor`` and ``ast.NodeTransformer`` from the standard library,
featuring a functional interface, explicit state passing, non-mutating AST transformation
and various minor convenience functionality.
Inspired by the ``Walker`` class from ``macropy``.
"""

import ast

from peval.tools.dispatcher import Dispatcher
from peval.tools.immutable import immutableadict


def ast_walker(handler):
    """
    A generic AST walker decorator.
    Decorates either a function or a class (if dispatching based on node type is required).
    ``handler`` will be wrapped in a :py:class:`~peval.Dispatcher` instance;
    see :py:class:`~peval.Dispatcher` for the details of the required class structure.

    Returns a callable with the signature::

        def walker(state, node, ctx=None)

    :param state: a dictionary with the state which will be passed to every handler call.
        It will be converted into a :class:`~peval.tools.immutableadict` object
        at the start of the traversal.
        Handlers can update it by returning a modified version.
    :param node: an ``ast.AST`` object to traverse.
    :param ctx: a dictionary with the global context which will be passed to every handler call.
        It will be converted into a :class:`~peval.tools.immutableadict` object
        at the start of the traversal.
    :returns: a tuple ``(state, new_node)``, where ``state`` is the same object which was passed
        as the corresponding parameter.
        Does not mutate ``node``.

    ``handler`` will be invoked for every node during the AST traversal (depth-first, pre-order).
    The ``handler`` function, if it is a function, or its static methods, if it is a class
    must have the signature::

        def handler([state, node, ctx, prepend, visit_after, visiting_after,
            skip_fields, walk_field,] **kwds)

    The names of the arguments must be exactly as written here,
    but their order is not significant (they will be passed as keywords).

    If ``handler`` is a class, the default handler is a "pass-through" function
    that does not change the node or the state.

    :param state: the (supposedly immutable) state object passed during the initial call.
    :param node: the current node
    :param ctx: the (supposedly immutable) dictionary with the global context
        passed during the initial call.
        In addition to normal dictionary methods, its values can be alternatively
        accessed as attributes (e.g. either ``ctx['value']`` or ``ctx.value``).
    :param prepend: a function ``prepend(lst)`` which, when called, prepends the list
        of ``ast.AST`` objects to whatever is returned by the handler of the closest
        statement block that includes the current node.
        These nodes are not traversed automatically.
    :param visit_after: a function of no arguments, which, when called,
        schedules to call the handler again on this node when all of its fields are traversed
        (providing that after calling it, the handler returns an ``ast.AST`` object
        and not a list or ``None``).
        During the second call this parameter is set to ``None``.
    :param visiting_after: set to ``False`` during the normal (pre-order) visit,
        and to ``True`` during the visit caused by ``visit_after()``.
    :param skip_fields: a function of no arguments, which, when called,
        orders the walker not to traverse this node's fields.
    :param walk_field: a function
        ``walk_field(state, value, block_context=False) -> (new_state, new_value)``,
        which traverses the given field value.
        If the value contains a list of statements, ``block_context`` must be set to ``True``,
        so that ``prepend`` could work correctly.
    :returns: must return a tuple ``(new_state, new_node)``, where ``new_node`` is one of:

        * ``None``, in which case the corresponding node will be removed from the parent list
          or the parent node field.
        * The passed ``node`` (unchanged).
          By default, its fields will be traversed (unless ``skip_fields()`` is called).
        * A new ``ast.AST`` object, which will replace the passed ``node`` in the AST.
          By default, its fields will not be traversed,
          and the handler must do it manually if needed
          (by calling ``walk_field()``).
        * If the current node is an element of a list,
          a list of ``ast.AST`` objects can be returned,
          which will be spliced in place of the node.
          Same as in the previous case, these new nodes
          will not be automatically traversed.
    """
    return _Walker(handler, transform=True, inspect=True)


def ast_transformer(handler):
    """
    A shortcut for :py:func:`~peval.ast_walker` with no changing state.
    Therefore:

    * the resulting walker has the signature ``def walker(node, ctx=None)``
      and returns the transformed AST tree;
    * the handler must return only the transformed node
      instead of a tuple ``(new_state, new_node)``;
    * ``walk_field`` has the signature
      ``walk_field(value, block_context=False) -> new_value``.
    """
    return _Walker(handler, transform=True)


def ast_inspector(handler):
    """
    A shortcut for :py:func:`~peval.ast_walker` which does not transform the tree,
    but only collects data.
    Therefore:

    * the resulting walker returns only the resulting state;
    * the handler must return only the new (or the unchanged given) state
      instead of a tuple ``(new_state, new_node)``;
    * ``walk_field`` has the signature
      ``walk_field(state, value, block_context=False) -> new_state``.
    """
    return _Walker(handler, inspect=True)


# The AST node fields which contain lists of statements
_BLOCK_FIELDS = ('body', 'orelse')


class _Walker:

    def __init__(self, handler, inspect=False, transform=False):

        self._transform = transform
        self._inspect = inspect
        if not (self._transform or self._inspect):
            raise ValueError("At least one of `transform` and `inspect` should be set")

        self._current_block_stack = [[]]

        # These method have different signatures depending on
        # whether transform and inspect are on,
        # so for the sake of performance we're using specialized versions of them.
        if self._transform and self._inspect:
            self._walk_field_user = self._transform_inspect_field
            def default_handler(state, node, **_):
                return state, node
        elif self._transform:
            self._walk_field_user = self._transform_field
            def default_handler(node, **_):
                return node
        elif self._inspect:
            self._walk_field_user = self._inspect_field
            def default_handler(state, **_):
                return state

        self._handler = Dispatcher(handler, default_handler=default_handler)

    def _walk_list(self, state, lst, ctx, block_context=False):
        """
        Traverses a list of AST nodes.
        If ``block_context`` is ``True``, the list contains statements
        (and therefore is a target for ``prepend()`` calls in nested handlers).
        """

        if self._transform:
            transformed = False
            new_lst = []

            if block_context:
                self._current_block_stack.append([])

        new_state = state

        for node in lst:
            new_state, new_node = self._walk_node(new_state, node, ctx, list_context=True)

            if self._transform and block_context and len(self._current_block_stack[-1]) > 0:
            # ``prepend()`` was called during ``_walk_node()``
                transformed = True
                new_lst.extend(self._current_block_stack[-1])
                self._current_block_stack[-1] = []

            if self._transform:
                if isinstance(new_node, ast.AST):
                    if new_node is not node:
                        transformed = True
                    new_lst.append(new_node)
                elif type(new_node) == list:
                    transformed = True
                    new_lst.extend(new_node)
                elif new_node is None:
                    transformed = True

        if self._transform:
            if block_context:
                self._current_block_stack.pop()

            if transformed:
                if block_context and len(new_lst) == 0:
                # If we're in the block context, we can't just return an empty list.
                # Returning a single ``pass`` instead.
                    new_lst = [ast.Pass()]
        else:
            new_lst = lst

        return new_state, new_lst

    def _walk_field(self, state, value, ctx, block_context=False):
        """
        Traverses a single AST node field.
        """
        if isinstance(value, ast.AST):
            return self._walk_node(state, value, ctx)
        elif type(value) == list:
            # In some nodes (Global and Nonlocal),
            # a list may contain plain strings instead of AST objects.
            if len(value) == 0 or (len(value) > 0 and type(value[0]) == str):
                return state, value
            else:
                return self._walk_list(state, value, ctx, block_context=block_context)
        else:
            return state, value

    # In these three functions `ctx` goes first because it makes it easier
    # to add it to the list of arguments later when `self._walk_field_user()` is called

    def _transform_field(self, ctx, value, block_context=False):
        return self._walk_field(None, value, ctx, block_context=block_context)[1]

    def _inspect_field(self, ctx, state, value, block_context=False):
        return self._walk_field(state, value, ctx, block_context=block_context)[0]

    def _transform_inspect_field(self, ctx, state, value, block_context=False):
        return self._walk_field(state, value, ctx, block_context=block_context)

    def _walk_fields(self, state, node, ctx):
        """
        Traverses all fields of an AST node.
        """
        if self._transform:
            transformed = False
            new_fields = {}

        new_state = state
        if node is None:
            return new_state, node

        for field, value in ast.iter_fields(node):

            block_context = field in _BLOCK_FIELDS and type(value) == list
            new_state, new_value = self._walk_field(
                new_state, value, ctx, block_context=block_context)

            if self._transform:
                new_fields[field] = new_value
                if new_value is not value:
                    transformed = True

        if self._transform and transformed:
            return new_state, type(node)(**new_fields)
        else:
            return new_state, node

    def _handle_node(self, state, node, ctx, list_context=False, visiting_after=False):

        def prepend(nodes):
            self._current_block_stack[-1].extend(nodes)

        to_visit_after = [False]
        def visit_after():
            to_visit_after[0] = True

        to_skip_fields = [False]
        def skip_fields():
            to_skip_fields[0] = True

        def walk_field(*args, **kwds):
            return self._walk_field_user(ctx, *args, **kwds)

        result = self._handler(
            # this argument is only used by the Dispatcher;
            # the user-defined handler gets keyword arguments
            node,
            state=state, node=node, ctx=ctx,
            prepend=prepend,
            visit_after=None if visiting_after else visit_after,
            visiting_after=visiting_after,
            skip_fields=skip_fields,
            walk_field=walk_field)

        # depending on the walker type, we expect different returns from the user-defined handler
        if self._transform and self._inspect:
            new_state, new_node = result
        elif self._transform:
            new_state, new_node = state, result
        elif self._inspect:
            new_state, new_node = result, node

        if self._transform:
            if list_context:
                expected_types = (ast.AST, list)
                expected_str = "None, AST, list"
            else:
                expected_types = (ast.AST,)
                expected_str = "None, AST"

            if new_node is not None and not isinstance(new_node, expected_types):
                raise TypeError(
                    "Expected callback return types in {context} are {expected}, got {got}".format(
                        context=("list context" if list_context else "field context"),
                        expected=expected_str,
                        got=type(new_node)))

        return new_state, new_node, to_visit_after[0], to_skip_fields[0]

    def _walk_node(self, state, node, ctx, list_context=False):
        """
        Traverses an AST node and its fields.
        """

        new_state, new_node, to_visit_after, to_skip_fields = self._handle_node(
            state, node, ctx, list_context=list_context, visiting_after=False)

        if new_node is node and not to_skip_fields:
            new_state, new_node = self._walk_fields(new_state, new_node, ctx)

        if to_visit_after:
            new_state, new_node, _, _ = self._handle_node(
                new_state, new_node, ctx, list_context=list_context, visiting_after=True)

        return new_state, new_node

    def __call__(self, *args, ctx=None):

        if self._transform and self._inspect:
            if len(args) != 2:
                raise TypeError(
                    "A walker instance takes two positional arguments ({num} given)".format(
                        num=len(args)))
            state, node = args
        elif self._transform:
            if len(args) != 1:
                raise TypeError(
                    "A transformer instance takes one positional argument ({num} given)".format(
                        num=len(args)))
            state, node = None, args[0]
        elif self._inspect:
            if len(args) != 2:
                raise TypeError(
                    "An inspector instance takes two positional arguments ({num} given)".format(
                        num=len(args)))
            state, node = args

        if ctx is not None:
            ctx = immutableadict(ctx)

        if state is not None:
            state = immutableadict(state)

        if isinstance(node, ast.AST):
            new_state, new_node = self._walk_node(state, node, ctx)
        elif isinstance(node, list):
            new_state, new_node = self._walk_list(state, node, ctx)
        else:
            raise TypeError("Cannot walk an object of type " + str(type(node)))

        if self._transform and self._inspect:
            return new_state, new_node
        elif self._transform:
            return new_node
        elif self._inspect:
            return new_state
