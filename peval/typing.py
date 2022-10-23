import sys
import ast
from typing import Dict, Any, Tuple, Union, Type

ConstsDictT = Dict[str, Any]
PassOutputT = Tuple[ast.AST, ConstsDictT]

NodeTypeT = Type[ast.AST]
NodeTypeIsInstanceCriteriaT = Union[Tuple[NodeTypeT], NodeTypeT]

NameNodeT = Union[ast.arg, ast.Name]

ConstantNodeT = ast.Constant

ConstantOrNameNodeT = Union[ConstantNodeT, ast.Name]

ConstantT = Union[int, float, complex, str, bytes, bool]
ConsantOrASTNodeT = Union[ConstantT, ast.AST]
