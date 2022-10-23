First issues:

- Figure out the bug on 3.8 nightly (https://travis-ci.org/fjarri/peval/jobs/573315684). The current pyenv version does not have it, must be something new they introduced. Check in some time.

- Convert TODO and License to Markdown, remove TODO from github?

- in `test_callable` remove things related to inheritance from `(object)`

- why does `forward_transfer()` returns lists of one element?

- why are we calling `map_reify()` on something that is always a single element and not a container in `peval_expression()`?

- `map_accum()` should also take `**kwds` to pass to the predicate.

- Need to mark types and add comments for internal functions. Not to mention just go through the library and deconvolute it a little.

- update `function.py::FUTURE_NAMES` for Py3.7/3.8


General
-------

* STYLE: Add exports from ``core`` and ``components`` submodules to their ``__init__``'s.

* IMPROVEMENT: It seems to be common to compare two ASTs before and after some function to check if there were any changes. If it takes much time, we can make walkers set some flag if they made a change in the AST and then just propagate it. Drawbacks: propagating an additional value; changes can take place outside of walkers.

* IMPROVEMENT: It will be great to have some way to "flatten" nested functions. That will eliminate the need for complicated scope analyzer.

* Use relative imports.


Core
----

* FEATURE (core/scope): needs a thorough improvement, with the ability to detect various ways of symbol usages, ``global``/``nonlocal`` modifiers, nested scopes and so on.

* FEATURE (core/gensym): use randomized symbols (SHA or something) instead of a counter

  pros:
  - no need to walk the AST before generating symbols
  - no need to carry around the generator

  cons:
  - a tiny probability of a collision
  - non-deterministic output (harder to test)

  We can use a random seed, but then we'll have to carry the generator. Alternatively, we can use a global seed just for tests.

* IMPROVEMENT (core/expression): ``peval_call()`` is sometimes called with a known function (e.g. from evaluating an operator). In this case there is no need to try to evaluate it, or replace it with a binding when evaluation failed, and remove this binding in the parent call. We can add proper handling of such cases to ``peval_call()`` and save on some state modifications.

* DECIDE (core/callable) is it still necessary if we are limited to Py3.5+?

* FEATURE (core/reify): extend the class of literals, adding non-trivial immutable objects, e.g. tuples and slices.

  Things to note:
  * It may be undesirable to make long lists (or dicts etc) into literals; an length limit can be introduced, but it requires some option object to be propagated.
  * Probably, making complex objects literals only makes sense if all their elements are literals; e.g. ``[_peval_temp1, _peval_temp2]`` is not much better than ``_peval_temp1``.
  * We can search for a ``__peval_reify__`` magic method that will return AST for custom objects, or ``None`` if it is non-reifiable.
  * In fact, custom objects may be reified by ``ast.parse(repr(obj))`` (for classes that define ``repr()`` properly)

* FEATURE (core/walker): make ``visit_after`` call do nothing if we are actually in the visiting-after stage (so that one does not have to write ``if not visiting_after: visit_after()``). Or even make it return ``visiting_after`` value, similarly to how ``fork`` works.

* BUG (core/mangler): when encountering a nested function definition, run it through ``Function`` and check which closure variables it uses (inlcuding the function name itself).
  Then mangle only them, leaving the rest intact.

* PROBLEM (core/function): it would be nice to have the new peval'ed function to stay connected to the same globals dictionary as the original one. This way we will preserve the globals-modifying behavior, and the less changes we make to a function, the better. The problem is that during partial evaluation we will need to introduce new bindings, and we cannot just insert them into the original globals dictionary --- this may interfere with other functions. I am not sure how to solve this at the moment.

* FEATURE (core/expression): add partial evaluation of lambdas (and nested function/class definitions).
  Things to look out to:

    * Need to see which outer variables the lambda uses as closures.
      These we need to lock --- ``prune_assignments`` cannot remove them.
    * Mark it as impure and mutating by default, unless the user explicitly marks it otherwise.
    * Run its own partial evaluation for the nested function?

* FEATURE (core/expression): in Py3 ``iter()`` of a ``zip`` object returns itself, so list comprehension evaluator considers it unsafe to iterate it.
  Perhaps comprehensions need the same kind of policies as loop unroller does, to force evaluation in such cases (also in cases of various generator functions that can reference global variables and so on).

* FEATURE (core/expression): support partial evaluation of starred arguments in invocations (see commented part of ``test_function_call``).

* In ``check_peval_expression()``, sometimes we force the expected node (e.g. "-5" is parsed as "UnaryOp(op=USub(), Num(n=5))", not as "Num(n=-5)", but we enforce the latter). Is that really necessary? If Python parses it as the former, shouldn't we generate the same?

* If we're limited to Py>=3.5, ``check_peval_expression_bool()`` is not needed anymore.

* Compress bindings, eliminating all duplicates that point to the same object.

* There seems to be an inconsistency regarding on whether the argument or mutated context is passed first/returned first in functions.

* If we have an option object, a useful object would be: "assume builtins are not redefined", which will make the resulting code much more readable.


Components
----------

* BUG (components/inline): when inlining a function, we must mangle the globals too, in case it uses a different set from what the parent function uses.

* FEATURE (components/fold): skip unreachable code (e.g. ``if`` branches) right away when doing propagation. See the ``xfail``-ed test in ``test_fold``.

* BUG (components/fold): possible mutation when comparing values in ``meet_values()`` (in case of a weird ``__eq()__`` definition)

* BUG (components/prune_assignments): need to keep the variables that are used as closures in nested functions.

* DECIDE (components/prune_assignments): The single assignments removal seems rather shady, although it is certainly useful to clean up after inlining. Need to think about corner cases, and also avoiding to call ``analyze_scope`` for every statement in the processed block.

* FEATURE (components/prune_cfg): we can detect unconditional jumps in ``for`` loops as well, but in order to remove the loop, we need the loop unrolling functionality.

* BUG (components/prune_cfg): evaluating ``bool(node.test)`` is potentially (albeit unlikely) unsafe (if it is some weird object with a weird ``__bool__()`` implementation).
  Need to run it through the safe call function from the expression evaluator.

* BUG (components/prune_cfg): see several FIXME's in the code related to the processing of try-except blocks

* FEATURE (components/inline): add support for inlining functions with varargs/kwargs.
  Probably just run the function through ``partial_apply`` before inlining?

* BUG (components/inline): how does marking methods as inlineable work? Need to check and probably raise an exception.

* FEATURE: support complex inlining scenarios:
  1a. Inlining self (currently supported)
  1b. Inlining a nested function
  1c. Inlining a nesting function
  2a. Inlining a function from the same module (currently supported)
  2b. Inlining a function from the other module


(new) components/unroll
-----------------------

Conditionally unroll loops.
Possible policies:

* based on a *keyword* ``unroll`` (that is, look for a ``ast.Name(id='unroll')``);
* based on a *function* ``unroll`` (check if the iterator in a loop is the unrolling iterator);
* based on heuristics (unroll range iterators, lists, tuples or dicts with less than N entries).


(new) components/macro
----------------------

Macros are similar to inlines, but the expressions passed to the function are substituted in its body without any changes and the resulting body is used to replace the macro call.
If the function was called in an expression context, check that the body contains only one ``ast.Expr`` and substitute its value.

::

    @macro
    def mad(x, y, z):
        x * y + z

    a = mad(b[1], c + 10, d.value)
    # --->
    # a = b[1] * (c + 10) + d.value


(new) better code pick up
-------------------------

In theory, the code of functions unreachable by ``inspect.getsource()`` (either the ones defined dynamically in the interactive prompt, or constructed at runtime) can be obtained by decompiling the code object. In theory, it seems pretty straightforward, but will require a lot of coding (to handle all the numerous opcodes). There is a decompiler for Py2 (https://github.com/wibiti/uncompyle2), but it uses some weird parsing and does not even involve the ``dis`` module.

This will, in turn, allow us to create doctests, but otherwise it is tangential to the main ``peval`` functionality.


(change) tools/immutable
------------------------

There are immutable data structure libraries that may be faster, e.g.:

* https://github.com/zhemao/funktown
* https://pythonhosted.org/pysistence/
* https://github.com/tobgu/pyrsistent (currently active)

Alternatively, the embedded implementation can be optimized to reuse data instead of just making copies every time.

Also, we can change ``update()`` and ``del_()`` to ``with_()`` and ``without()`` which better reflect the immutability of data structures.

This is especially important in the light of https://www.reddit.com/r/Python/comments/42t9yw/til_dictmy_subclassed_dict_doesnt_use_dict_methods/ : subclassing from dict() and others is error-prone.


Known limitations
=================

In the process of partial evaluation, the target function needs to be discovered in the source code, parsed, optimized and re-evaluated by the interpreter.
Due to the way the discovery of function code and metadata is implemented in Python, in some scenarios ``peval`` may lack necessary information and therefore fail to restore the function correctly.
Fortunately, these scenarios are not very common, but one still needs to be aware of them.

And, of course, there is a whole group of problems arising due to the highly dynamical nature of Python.


Decorators
----------

* **Problem:** If the target function is decorated, the decorators must preserve the function metadata, in particular, closure variables, globals, and reference to the source file where it was defined.

  **Workaround:** One must either take care of the metadata manually, or use a metadata-aware decorator builder library like `wrapt <https://pypi.python.org/pypi/wrapt>`_.

* **Problem:** Consider a function decorated inside another function:

  ::

      def outer():
          arg1 = 1
          arg2 = 2

          @decorator(arg1, arg2)
          def innner():
              # code_here

          return inner

  The variables used in the decorator declaration (``arg1``, ``arg2``) are not included neither in globals nor in closure variables of ``inner``.
  When the returned ``inner`` function is partially evaluated, it is not possible to restore the values of ``arg1`` and ``arg2``, and the final evaluation will fail.

  **Workaround:** Make sure all the variables used in the decorator declarations for target functions (including the decorators themselves) belong to the global namespace.

* **Problem:** When the target function is re-evaluated, the decorators associated with it are applied to the new function.
  This may lead to unexpected behavior if the decorators have side effects, or rely on some particular function arguments (which may disappear after partial application).

  **Workaround:** Make sure that the second application of the decorators does not lead to undesired consequences, and that they can handle changes in the function signature.

* **Problem:** Consider a case when a decorator uses the same symbol as one of the function arguments:

  ::

      @foo
      def test(foo, bar):
          return foo, bar

  If we bind the ``foo`` argument to some value, this value will be added to the globals and, therefore, will replace the value used for the ``foo`` decorator.
  Consequently, the evaluation of such partially applied function will fail
  (in fact, an assertion within ``Function.bind_partial()`` will fire before that).

  **Workaround:** Avoid using the same symbols in function argument lists and in the decorator declarations applied to these functions (which is usually a good general coding practice).
