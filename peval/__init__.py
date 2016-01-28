"""
Core functions
--------------

.. autofunction:: partial_eval
.. autofunction:: partial_apply


Helper functions
----------------

.. autofunction:: getsource
.. autofunction:: specialize_on


Tags
----

.. autofunction:: inline
.. autofunction:: pure
"""

from peval.highlevelapi import partial_eval, partial_apply, specialize_on
from peval.tags import pure, inline
from peval.core.function import getsource
