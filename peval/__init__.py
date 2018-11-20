"""
High-level API
--------------

.. autofunction:: partial_eval
.. autofunction:: partial_apply


Tags
====

.. autofunction:: inline
.. autofunction:: pure


Helper functions
================

.. autofunction:: getsource
.. autofunction:: specialize_on


Low-level tools
---------------

.. autofunction:: ast_walker
.. autofunction:: ast_inspector
.. autofunction:: ast_transformer
.. autofunction:: try_peval_expression
.. autoclass:: Dispatcher
.. autoclass:: Function
    :members:
"""

from peval.tools import Dispatcher, ast_walker, ast_inspector, ast_transformer
from peval.core.expression import try_peval_expression
from peval.highlevelapi import partial_eval, partial_apply, specialize_on
from peval.tags import pure, inline
from peval.core.function import getsource, Function
